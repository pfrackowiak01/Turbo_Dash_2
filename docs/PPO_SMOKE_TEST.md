# Weryfikacja pipeline PPO discrete

Data: **2026-09-13**. Commit bazowy: `13f98a3c42b41a23792a00cad1957b1c711abb85`. Testy zmian wykonywano świadomie z `allow-dirty`; manifest zachował pełną listę zmian. Unity: **2022.3.4f1**. Finalny worker: Windows x86_64 **Release**. Python: **3.11.9**. SB3: **2.9.0**. Wszystkie runy używały tylko TRAIN albo VALIDATION.

**TEST: UNUSED FOR TRAINING/TUNING/EVALUATION.** Żaden seed TEST nie został załadowany przez bridge, benchmark, smoke, trening ani walidację.

## Zestawy testów

| Zestaw | Wynik | Zakres |
| --- | ---: | --- |
| Python unit tests | 6/6 PASS | framing, handshake mismatch, mapowanie akcji, pełna permutacja i resume schedulera, blokada TEST, terminal observation/auto-reset |
| Baseline regression | 23/23 PASS | normalna gra od Menu, sterowanie, portal, kolizje, bonusy, Turbo, Game Over, Retry |
| Research Mode regression | 230/230 PASS | reset, RNG, adaptery, observations, reward, terminale, CSV, brak przeładowania sceny |
| Standalone bridge Release | 22/22 PASS | realny TCP, reset/step, 236 float32, pięć ticków, reward terminalny, terminated/truncated, graceful close, disconnect, cztery procesy |
| Standalone build Release | PASS | Windows x86_64, wyłącznie `DeafultLevel`, bez zmiany Build Settings |
| Editor–standalone parity | 5/5 PASS | RuleBasedV1, timeScale 20, `-batchmode -nographics`, horyzont 30 s |
| Benchmark 1/2/4/6 | 4/4 PASS | co najmniej 4000 przejść na wariant, wszystkie procesy zamknięte poprawnie |
| PPO 100k smoke Release | PASS | 104448 przejść, 160 aktualizacji, walidacja 100/100, checkpoint i TensorBoard |
| Resume Release | PASS | `104448 → 110592`, scheduler odtworzony, wagi dalej aktualizowane, nowy checkpoint i TensorBoard |
| Validation-only script | PASS | publiczny skrypt, deterministyczna policy, wszystkie 100 seedów VALIDATION |
| One-command overnight entry | PASS | publiczny skrypt wykonał kontrolny rollout 6144 i zamknął 6 workerów |
| Dirty-tree guard | PASS | start bez `allow-dirty` odmówił przed utworzeniem katalogu runu |
| Six-worker close preflight | PASS | 6144 przejścia, wymagane `CLOSE_ACCEPTED` i exit code 0 |

Bridge był uruchamiany z `-batchmode -nographics`. Pierwszy nieterminalny `STEP` zwiększył licznik fizyki dokładnie z 0 do 5. MaxDuration zwrócił truncation, LivesExhausted zwrócił termination, a suma rewardów kroków była zgodna z `PilotRewardCalculator.EpisodeReward`, również dla ostatniego częściowego interwału. W finalnym przejściu powtórzenie seeda `1104732` z samymi akcjami NONE dało score `302.9090/302.9613` i identyczny czas `12.00018 s`, mieszcząc się w tolerancji runtime. Test mismatch użył rzeczywistego procesu: Python odebrał jego `HELLO`, wykrył celowo niezgodny worker id i odesłał `ERROR` przed pierwszym resetem.

Jedna wcześniejsza próba tego testu miała różnicę `15.006` score i `1.590 s`, przy tym samym terminalu, liczbie utrat życia, poziomie i liczbie ominiętych przeszkód. Ponowienie na niezmienionym buildzie przeszło dotychczasowy próg, dlatego tolerancji nie rozszerzono. Jest to dodatkowy dowód ograniczenia długiego horyzontu opisanego niżej.

## Standalone parity

Porównano publiczny `TurboDash.Research.Editor.ResearchMenu.RunBatch` z finalnym Windows standalone Release uruchomionym przez `-batchmode -nographics`: RuleBasedV1, timeScale 20, pierwsze pięć seedów TRAIN. Test ma jawny horyzont 30 s, czyli około 600 decyzji na seed i około 3000 decyzji po każdej stronie.

Wynik: **5/5 PASS**. Wszystkie pary miały identyczne: seed, `lifeLossCount`, `collisionsTotal`, `maxLevel` i `terminalReason=MaxDuration`. Różnica `survivalTime` wyniosła maksymalnie `0.020 s`, score `0.368`, a `obstaclesAvoided` najwyżej 1. Raport stosuje tolerancje: `0.15 s` czasu, 1% score i ±1 kolizji/uniknięć; życie, poziom i terminal muszą być równe.

Horyzont został ograniczony po zbadaniu dwóch pełnych, wielominutowych porównań. Długie trajektorie nie są powtarzalne nawet między dwoma uruchomieniami tego samego trybu: dla seeda `1209461` sam Editor uzyskał `72.27 s`, a w powtórzeniu `126.31 s`; standalone uzyskał odpowiednio `91.41 s` i `72.24 s`. W grze pozostały systemy działające w `Update` obok logiki `FixedUpdate`; mała różnica kolejności aktualizacji może przekroczyć próg decyzji RuleBasedV1 i po wielu zdarzeniach prowadzić inną gałęzią trajektorii. Nie zmieniano z tego powodu zamrożonego gameplayu ani Research Protocol v1. Parity potwierdza zgodność krótkiego kroku i początkowej trajektorii, ale nie gwarantuje bitowej ani długohoryzontowej deterministyczności Unity.

Artefakty finalnego porównania: `Training/runs/parity-release-bounded-final/`.

## Benchmark workerów Release

Każdy wariant wykonał co najmniej 4000 przejść na TRAIN, timeScale 20, `-batchmode -nographics`. CPU to suma czasu procesora workerów podzielona przez czas ścienny; 100% odpowiada jednemu logicznemu rdzeniowi. RSS obejmuje tylko procesy Unity.

| Workery | Transitions/s | CPU workerów | Peak RSS | Stabilność |
| ---: | ---: | ---: | ---: | --- |
| 1 | 398.13 | 290.82% | 177.26 MiB | PASS |
| 2 | 790.28 | 372.61% | 351.77 MiB | PASS |
| 4 | 1509.77 | 521.93% | 696.87 MiB | PASS |
| 6 | 2021.43 | 584.82% | 1034.29 MiB | PASS |

Sześć workerów dało **33.9%** więcej przejść niż cztery, zużywając około 1.01 GiB RSS i kończąc wszystkie procesy kodem 0. Dla badanego i5-12400 / 16 GB rekomendacją jest **6 workerów**. Bazowy plik PPO Pilot v1 zachowuje specyfikacyjne `workers=4`, natomiast skrypt overnight domyślnie przekazuje zmierzoną rekomendację 6. Artefakt: `Training/runs/benchmark-release-final/benchmark.json`.

## PPO discrete 100k smoke Release

Run: `Training/runs/ppo-smoke-100k-release-final` (artefakty lokalne, ignorowane przez Git).

| Parametr / wynik | Wartość |
| --- | ---: |
| Workery / timeScale | 6 / 20 |
| Żądane / wykonane przejścia | 100000 / 104448 |
| Rollouty / aktualizacje PPO | 17 / 160 |
| Czas ścienny z walidacją | 173.04 s |
| Średnia przepustowość z walidacją | 603.62 transitions/s |
| Epizody TRAIN zakończone podczas smoke | 187 |
| Walidacja | 100/100 seedów VALIDATION |
| Final validation mean / median / std score | 2035.586 / 885.651 / 5123.278 |
| Final validation mean / median survival | 54.401 / 40.104 s |
| Terminale walidacji | LivesExhausted 96, MaxDuration 4 |

SB3 domknął pełny rollout `n_steps × workers`, dlatego licznik końcowy wynosi 104448. Hash policy zmienił się z `9c999212...` na `51657317...`. Wszystkie raportowane observations, rewards i PPO losses były skończone. Końcowe metryki obejmowały `approx_kl=0.009367`, `clip_fraction=0.100`, `entropy_loss=-0.957`, `explained_variance=0.857` i `value_loss=0.0606`.

Checkpoint został zapisany i ponownie wczytany z zachowanym `num_timesteps=104448`:

```text
Training/runs/ppo-smoke-100k-release-final/checkpoints/ppo_final_104448.zip
Training/runs/ppo-smoke-100k-release-final/checkpoints/seed_scheduler_final_104448.json
```

Najlepszy model po walidacji:

```text
Training/runs/ppo-smoke-100k-release-final/best_model/model.zip
```

TensorBoard:

```text
Training/runs/ppo-smoke-100k-release-final/tensorboard/PPO_Pilot_v1_1/
```

Skan sześciu logów treningowych i czterech walidacyjnych nie znalazł błędów bridge’a, rozłączeń ani NaN/Inf. Wszystkie procesy potwierdziły `CLOSE_ACCEPTED` i zakończyły się kodem 0. Smoke potwierdza działanie infrastruktury; nie jest eksperymentem jakości i nie ma obowiązku pobicia RuleBasedV1.

Finalny test resume odtworzył model, optimizer, `num_timesteps` oraz stan schedulera z powyższej pary plików. Jeden rollout zwiększył licznik do 110592, zmienił hash polityki z `51657317...` na `74427b12...`, zapisał i wczytał nowy checkpoint oraz utworzył dane TensorBoard w `Training/runs/ppo-resume-release-verify/`.

Publiczny `Validate-PpoDiscrete.ps1` również ocenił wszystkie 100 seedów i zamknął workery poprawnie (`Training/runs/validation-release-final/`). Publiczny `Start-PpoDiscreteOvernight.ps1` przeszedł próbę wejścia z kontrolnym budżetem 6144: zaktualizował wagi, zapisał i wczytał checkpoint, utworzył TensorBoard i zakończył sześć procesów (`Training/runs/overnight-entry-release-final/`). Docelowego treningu 5M nie wykonywano w ramach smoke.

## Polecenia po smoke

Overnight 5M:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-PpoDiscreteOvernight.ps1
```

Resume z checkpointu smoke do 5M:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Resume-PpoDiscrete.ps1 `
  -Checkpoint .\Training\runs\ppo-smoke-100k-release-final\checkpoints\ppo_final_104448.zip `
  -SchedulerState .\Training\runs\ppo-smoke-100k-release-final\checkpoints\seed_scheduler_final_104448.json `
  -TargetTimesteps 5000000 -Workers 6
```

Validation-only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Validate-PpoDiscrete.ps1 `
  -Model .\Training\runs\ppo-smoke-100k-release-final\best_model\model.zip
```
