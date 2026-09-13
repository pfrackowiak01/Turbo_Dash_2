# Pipeline treningowy PPO discrete

Stan na 2026-09-13. Pipeline wykorzystuje zamrożony [Research Protocol v1](RESEARCH_PROTOCOL_V1.md), Observation v2 (`236 × float32`) i reward v1. Nie zawiera ML-Agents, NEAT ani eksperymentu PPO continuous.

## Architektura

```text
Start-PpoDiscreteOvernight.ps1
  └─ Python 3.11 / stable-baselines3 2.9.0
       ├─ TCP listener 127.0.0.1 : losowy port ─ Unity Worker 0
       ├─ TCP listener 127.0.0.1 : losowy port ─ Unity Worker 1
       ├─ ...
       └─ TurboDashVecEnv ─ PPO ─ checkpointy / TensorBoard / validation
```

Python jest właścicielem procesów i seedów. Każdy worker jest osobnym Windows x86_64 playerem, ładuje wyłącznie `DeafultLevel`, otrzymuje jeden konkretny seed przez bridge i zapisuje własny log oraz CSV. Worker nie odczytuje `ResearchSeedCatalog.DefaultDirectory` i nie wybiera TRAIN, VALIDATION ani TEST.

`ResearchWorkerBuild.BuildWindows64` przekazuje do `BuildPipeline.BuildPlayer` własną tablicę scen zawierającą tylko `Assets/Turbo_Dash/Design/Scenes/DeafultLevel.unity` i tworzy Windows x86_64 player Release (`BuildOptions.None`). Nie zapisuje ani nie modyfikuje zwykłych Build Settings. Skrypt budujący kopiuje `Assets`, `Packages` i `ProjectSettings` do `D:\Temp\TurboDash-ResearchWorker-BuildCache`; import i `Library` pozostają poza repozytorium.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Setup-Venv.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Build-ResearchWorker.ps1
```

Pierwsze polecenie wymaga 64-bitowego Pythona 3.11, tworzy `Training/.venv`, instaluje `Training/requirements.txt` i zapisuje faktyczny freeze do `Training/requirements-lock.txt`. Zweryfikowane wersje to Python 3.11.9, Stable-Baselines3 2.9.0, Gymnasium 1.2.3, NumPy 2.4.6, PyTorch 2.14.0 CPU i TensorBoard 2.21.0.

## Worker i transport

Python uruchamia player z `-batchmode -nographics`. Ten wariant przeszedł bridge tests, parity, benchmark i smoke 100k. UI jest ukryte przez istniejący Research Mode, lecz `UIGame`, `ImmortalityEffect`, collidery oraz pozostała logika gameplayu pozostają aktywne.

Parity Editor–standalone używa pięciu pierwszych seedów TRAIN, RuleBasedV1, timeScale 20 i horyzontu 30 s. Taki horyzont obejmuje około 3000 decyzji po każdej stronie i sprawdza zgodność runtime przed rozgałęzieniem długich trajektorii. Oryginalne systemy działające w `Update` obok `FixedUpdate` powodują, że wielominutowe przejścia nie są ściśle powtarzalne; nie należy traktować pojedynczej długiej pary jako testu bitowej deterministyczności. Zmierzone wyniki i zbadane rozbieżności opisuje [PPO_SMOKE_TEST.md](PPO_SMOKE_TEST.md).

Parametry workera:

| Argument | Znaczenie |
| --- | --- |
| `--research-worker` | aktywuje bootstrap workera zamiast zwykłej gry |
| `--worker-id <n>` | nieujemny identyfikator sprawdzany w handshake |
| `--bridge-host <host>` | host listenera, standardowo `127.0.0.1` |
| `--bridge-port <port>` | port przydzielony przez Python |
| `--time-scale <x>` | dodatni Unity `timeScale`, standardowo 20 |
| `--action-space Discrete` | przestrzeń akcji; wire format jest gotowy na późniejsze `Continuous` |
| `--unity-csv <path>` | unikalny plik podsumowań danego workera |
| `--max-duration <s>` | domyślnie protokołowe 300 s; krótsza wartość służy testom bridge |

Unity log dostaje osobną ścieżkę przez standardowy argument `-logFile`. `TCP_NODELAY` jest włączony po obu stronach.

Transport v1 jest binarny, little-endian i nie serializuje JSON przy 20 Hz. Każda wiadomość ma `int32 payloadLength`, a potem payload zaczynający się od `uint8 messageType`. Limit ramki wynosi 1 MiB.

| Typ | Kierunek | Payload |
| --- | --- | --- |
| `HELLO` | Unity → Python | wersja transportu i Research Protocol, schema/rozmiar observation, action space, fixed timestep, decision interval, worker id |
| `HELLO_ACCEPTED` / `ERROR` | Python → Unity | akceptacja albo opis niezgodności i natychmiastowe przerwanie |
| `RESET` | Python → Unity | dodatni `int32 seed` |
| `RESET_RESULT` | Unity → Python | początkowe `236 × float32` |
| `STEP` | Python → Unity | discrete `int32`: `0 LEFT`, `1 NONE`, `2 RIGHT` |
| `STEP_RESULT` | Unity → Python | reward, terminated, truncated, physics tick count, observation i metryki epizodu |
| `CLOSE` / `CLOSE_ACCEPTED` | Python ↔ Unity | kontrolowane zamknięcie procesu |

Handshake sprawdza dokładnie: transport 1, Research Protocol 1, Observation schema 2, długość 236, wskazaną przestrzeń akcji, `fixedDeltaTime=0.01`, decision interval `0.05` i worker id. Niezgodność kończy start przed pierwszym resetem.

`STEP` odpowiada jednej decyzji `DecisionScheduler`. Akcja jest utrzymywana przez pięć ticków fizyki. Na następnej granicy Unity zwraca obserwację oraz `LastDecisionReward` obliczony przez istniejący `PilotRewardCalculator`. Python nie ma kopii wzoru rewardu. Jeżeli epizod kończy się między granicami, `ResearchMode.Complete` najpierw domyka częściowy interwał, a bridge wysyła tę nagrodę razem z końcową obserwacją.

## VecEnv i wynik epizodu

`TurboDashVecEnv` dziedziczy po SB3 `VecEnv`. `step_async` wysyła akcję do wszystkich workerów, a `step_wait` odbiera wszystkie wyniki, więc symulacja zachodzi równolegle bez `SubprocVecEnv`.

Przestrzenie PPO Pilot v1:

- observation: `Box(-1, 1, shape=(236,), dtype=float32)`;
- action: `Discrete(3)`;
- brak normalizacji observation i reward;
- `device=cpu`.

`LivesExhausted` daje `terminated=true, truncated=false`. `MaxDuration` i opcjonalny `MaxScore` dają `terminated=false, truncated=true`. Dla SB3 `done = terminated or truncated`. Przy `done` wrapper kopiuje końcowy wektor do `info["terminal_observation"]`; truncation dodaje `info["TimeLimit.truncated"]=true`. Dopiero potem wybiera następny TRAIN seed, wysyła `RESET` i zwraca początkową obserwację nowego epizodu.

Utrata workera przerywa cały run. Orkiestrator zamyka pozostałe procesy i zapisuje błąd w manifeście; nie zastępuje procesu w środku rolloutu. Poprawne zakończenie wymaga `CLOSE_ACCEPTED` i kodu procesu 0.

## Seedy

Python bezpośrednio waliduje wersjonowane `train.json` i `validation.json`:

- trening, smoke i benchmark: wyłącznie 700 seedów TRAIN;
- okresowa i ręczna walidacja: zawsze wszystkie 100 seedów VALIDATION;
- **TEST: UNUSED FOR TRAINING/TUNING/EVALUATION**.

`TrainingSeedScheduler` losuje pełną permutację 700 wartości własnym RNG. Po rozdaniu całej puli tworzy kolejną permutację. Stan zawiera pulę, kolejność, indeks, numer cyklu i stan generatora NumPy; jest zapisywany obok każdego checkpointu i odtwarzany przy resume.

## PPO Pilot v1

Źródłem konfiguracji jest `Training/configs/ppo_pilot_v1.json`:

| Parametr | Wartość |
| --- | --- |
| algorytm / policy | PPO / MlpPolicy |
| sieć | `pi=[256,256]`, `vf=[256,256]`, Tanh |
| learning rate | `3e-4` |
| gamma / GAE lambda | `0.9995` / `0.95` |
| clip / entropy / value | `0.2` / `0.01` / `0.5` |
| max grad norm | `0.5` |
| n_steps / batch / epochs | `1024` / `512` / `10` |
| RNG seed | `20260913` |
| konfiguracja bazowa | 4 workery, timeScale 20, CPU |

Benchmark tego komputera uzasadnił sześć workerów, dlatego skrypt overnight nadpisuje bazowe `workers=4` zmierzoną rekomendacją `6`. Pełny run domyślnie ma 5 000 000 przejść. Checkpoint powstaje co 250 000 przejść, a deterministyczna walidacja 100 seedów co 500 000. `best_model/model.zip` jest zastępowany wyłącznie po poprawie średniego `finalScore` VALIDATION.

## Run, manifest i logi

Każdy run ma nowy `Training/runs/<run-id>/`:

```text
manifest.json
config.json
training_summary.csv
tensorboard/
checkpoints/
best_model/
validation/
worker_logs/
unity_episode_csv/
```

Manifest zapisuje commit i pełny `git status --porcelain`, stan dirty, wersje kontraktu, timing, reward, interpreter, wersje pakietów, pełny `pip freeze`, konfigurację PPO, workers/timeScale/RNG oraz SHA-256 plików TRAIN i VALIDATION. TEST ma status UNUSED. Overnight domyślnie odmawia startu na dirty working tree przed utworzeniem katalogu runu. `-AllowDirty` jest świadomym wyjątkiem, przechowywanym w manifeście jako `git.dirty=true`.

TensorBoard zawiera metryki rolloutów i PPO, w tym loss, entropy, explained variance, approximate KL i clip fraction. `training_summary.csv` łączy przepustowość, terminalne metryki epizodów i agregaty walidacji. Unity CSV są diagnostyczne; głównym źródłem przebiegu treningu jest Python.

## Polecenia

Pełny overnight 5M z rekomendowanymi sześcioma workerami:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-PpoDiscreteOvernight.ps1
```

Skrypt sprawdza `.venv`, buduje brakujący worker, sprawdza stałe protokołu i dirty tree, a Python waliduje wyłącznie TRAIN/VALIDATION. `try/finally` zamyka wszystkie workery po sukcesie lub błędzie.

Resume do docelowego 5M, bez zerowania licznika:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Resume-PpoDiscrete.ps1 `
  -Checkpoint .\Training\runs\<run-id>\checkpoints\ppo_2500000.zip `
  -SchedulerState .\Training\runs\<run-id>\checkpoints\seed_scheduler_2500000.json `
  -TargetTimesteps 5000000
```

Checkpoint SB3 zawiera policy, optimizer i `num_timesteps`; plik schedulera odtwarza kolejkę TRAIN. Resume zapisuje nowy manifest z `parent_checkpoint` i kontynuuje licznik.

Walidacja wszystkich 100 seedów VALIDATION:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Validate-PpoDiscrete.ps1 `
  -Model .\Training\runs\<run-id>\best_model\model.zip
```

TensorBoard dla wszystkich runów:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-TensorBoard.ps1
```

Testy developerskie uruchamiane z katalogu `Training`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m turbodash.bridge_verify
.\.venv\Scripts\python.exe -m turbodash.benchmark --counts 1 2 4 6 --time-scale 20
```

Wyniki rzeczywistych testów i smoke znajdują się w [PPO_SMOKE_TEST.md](PPO_SMOKE_TEST.md).
