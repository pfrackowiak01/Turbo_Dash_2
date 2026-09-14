# Pipeline NEAT Discrete

Stan na 2026-09-14. Pipeline implementuje wyłącznie wariant **NEAT Discrete** dla zamrożonego Research Protocol v1 i Observation v2 (`236 × float32`). Korzysta z istniejącego standalone Research Workera, TCP bridge'a, fizyki, gameplayu, rewardu oraz podziału seedów. Nie zmienia pipeline'ów PPO i nie zawiera wariantu NEAT Continuous.

## Środowisko i model

Pipeline wymaga 64-bitowego Pythona 3.11 oraz przypiętego `neat-python==2.0.0`. Ta wersja jest zapisana jednocześnie w `Training/requirements.txt`, `Training/requirements-lock.txt`, konfiguracji runu i manifeście. Instalacja środowiska pozostaje wspólna:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Setup-Venv.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Build-ResearchWorker.ps1
```

Każdy genom jest zamieniany przez `neat.nn.FeedForwardNetwork.create` na deterministyczną sieć feed-forward:

- 236 wejść w kolejności Observation v2;
- 3 wyjścia w kolejności `LEFT`, `NONE`, `RIGHT`;
- aktywacja `tanh`, agregacja `sum`;
- akcja jest unikalnym `argmax`; dowolny dokładny remis wartości maksymalnej daje `NONE`;
- brak stanu rekurencyjnego i brak losowania podczas inferencji.

Fitness pojedynczego epizodu jest obliczany wyłącznie z końcowego podsumowania bridge'a:

```text
fitness = finalScore / 100 - 0.5 * lifeLossCount
```

Fitness genomu to średnia dokładnie dwóch takich epizodów. Reward PPO nie jest dodawany do fitness i nie ma żadnych bonusów pomocniczych.

## Zamrożona konfiguracja

Źródła ustawień to `Training/configs/neat_discrete_v1.json` i `Training/configs/neat_discrete_v1.ini`.

| Parametr | Wartość |
| --- | --- |
| population | 64 |
| initial connection | `full_direct` |
| feed-forward / hidden nodes | `true` / 0 |
| activation / aggregation | `tanh` / `sum` |
| fitness criterion | `max` |
| elitism / survival threshold | 2 / 0.20 |
| compatibility threshold | 3.0 |
| node add / delete | 0.05 / 0.02 |
| connection add / delete | 0.20 / 0.10 |
| weight init | Gaussian, mean 0, stdev 1 |
| weight mutate power / rate / replace rate | 0.5 / 0.5 / 0.05 |
| bias mutate power / rate / replace rate | 0.5 / 0.7 / 0.1 |
| workers / timeScale | 6 / 20 |
| treningowy MaxDuration | 300 s |
| epizody na genom | 2 |
| domyślny budżet | 5 000 000 przejść treningowych |

Parametry są ustawieniem pojedynczego planowanego eksperymentu, a nie wynikiem przeszukiwania hiperparametrów.

## Generacja, seedy i budżet

Na początku każdej generacji `TrainingSeedScheduler` wybiera dwie kolejne wartości z deterministycznie przetasowanego cyklu wszystkich 700 seedów TRAIN. Ta sama para jest używana dla każdego genomu danej generacji. Po wyczerpaniu pełnej puli powstaje następna deterministyczna permutacja. Wspólny dobór seedów ogranicza wpływ różnicy trudności epizodów na porównanie genomów.

Jedno odebrane `STEP_RESULT` liczy się jako jedno przejście treningowe. Epizody VALIDATION nie wchodzą do budżetu. Trening sprawdza budżet wyłącznie po zakończeniu całej generacji: nigdy nie ucina generacji i dlatego wynik może nieznacznie przekroczyć 5M. Manifest raportuje docelowy budżet, faktyczną liczbę przejść i overshoot.

Zadania `(genom, seed)` są rozdzielane dynamicznie między sześć workerów. Sieć feed-forward jest bezstanowa, więc kolejność ukończenia workerów nie wpływa na fitness ani ewolucję. Utrata workera przerywa run; pozostałe procesy są zamykane w `finally`.

Pipeline nigdy nie otwiera `test.json`. **TEST: UNUSED FOR TRAINING/TUNING/EVALUATION.**

## Walidacja i wybór best

Champion ukończonej generacji jest oceniany deterministycznie na wszystkich 100 seedach VALIDATION z `MaxDuration=300`:

1. po pierwszej pełnej generacji;
2. po pierwszej generacji kończącej się na lub za każdym kolejnym progiem 500 000 przejść treningowych;
3. najwyżej raz po jednej generacji, również gdy długa generacja przekroczy więcej niż jeden próg.

Przed walidacją sześć workerów treningowych jest zamykanych. Walidator uruchamia sześć własnych workerów, zamyka je po 100 epizodach, a kolejna generacja dostaje nową sesję workerów. Jednocześnie nie działa więc więcej niż sześć procesów.

`best_model/genome.pkl` jest zastępowany wyłącznie wtedy, gdy champion osiągnie ściśle większy mean `finalScore` na 100 seedach VALIDATION. Fitness treningowy, survival time ani wynik pojedynczego seedu nie są dodatkowymi kryteriami. `selection.json` zapisuje generację, licznik przejść, hash genomu i konfiguracji oraz pełne podsumowanie walidacji.

## Checkpoint i resume

Checkpoint powstaje po każdej pełnej generacji, po ewentualnej walidacji. Składa się z:

- natywnego `neat-checkpoint-<generation>`: populacja, species set, numer generacji, konfiguracja, stan globalnego RNG Pythona oraz innovation tracker;
- `neat-checkpoint-<generation>.state.json`: licznik przejść, kolejny próg walidacji, liczba walidacji, pełny stan `TrainingSeedScheduler`, efektywna konfiguracja, hashe i metadane best;
- `neat-checkpoint-<generation>.best.pkl`: kopia najlepszego genomu wybranego na VALIDATION, jeśli wybór już nastąpił;
- `checkpoints/latest.json`: wskaźnik na najnowszą sparowaną parę.

Po zapisie trainer natychmiast ładuje natywny checkpoint i sprawdza generację oraz klucze populacji. Resume weryfikuje SHA-256 checkpointu, konfiguracji i kopii best, odtwarza scheduler, populację/species/generację, innovation tracker i dokładny stan RNG, a następnie dopisuje kolejne metryki do tego samego runu. Pierwsza nowa ewaluacja po `neat-checkpoint-1` jest więc generacją 2.

Przykład wznowienia:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\Training\Resume-NeatDiscrete.ps1 `
  -State .\Training\runs\<run-id>\checkpoints\neat-checkpoint-42.state.json `
  -AllowDirty
```

## Artefakty

Pojedynczy run zapisuje:

```text
Training/runs/<run-id>/
  manifest.json
  config.json
  neat_config.ini
  generation_metrics.csv
  training_episodes.csv
  checkpoints/
  best_model/{genome.pkl,config.ini,selection.json}
  validation/generation-XXXXXX/{episodes.csv,summary.json,worker_logs/,unity_episode_csv/}
  training_sessions/<session-id>/{worker_logs/,unity_episode_csv/}
```

Manifest obejmuje commit i dirty status, Python/pip freeze, dokładną wersję `neat-python`, stałe protokołu, konfigurację, SHA-256 TRAIN i VALIDATION, postęp, czas ścienny i status TEST. Unity CSV jest diagnostyczny; `training_episodes.csv`, `generation_metrics.csv` i manifest są głównymi artefaktami orkiestratora.

## Smoke test

Smoke ma osobne zabezpieczenia: population najwyżej 8, 1–2 krótkie generacje, budżet najwyżej 50 000 oraz treningowy MaxDuration najwyżej 60 s. Nie wykonuje kosztownej walidacji 100-seed i nie może być pomylony z pełnym eksperymentem.

Zweryfikowany przebieg użył population 8, `MaxDuration=30`, budżetu 30 000 i jednej generacji na wywołanie. Pierwsze wywołanie zakończyło generację 1 przy 5 337 przejściach. Resume z zapisanego stanu zakończył generację 2 przy 10 137 łącznych przejściach. Oba checkpointy przeszły natychmiastowy load check, a workery zamknęły się poprawnie.

## Eksperyment 3-run

`Start-NeatDiscreteExperiment.ps1` bez interakcji wykonuje sekwencyjnie:

1. `neat-discrete-5m-run1`, seed `20260919`;
2. `neat-discrete-5m-run2`, seed `20260920`;
3. `neat-discrete-5m-run3`, seed `20260921`;
4. osobną walidację best każdego runu na 100 VALIDATION z `MaxDuration=500`;
5. `Training/runs/neat-discrete-experiment-summary.json`, `.csv` i `.log`.

Błąd dowolnego etapu zatrzymuje sekwencję. `-SkipExisting` pomija tylko artefakty, których status, algorytm, action space, seed, budżet, wersja biblioteki, hash modelu i status TEST przechodzą kontrolę. Końcowym zwycięzcą jest wyłącznie run o największym mean `finalScore` z walidacji 500 s; wszystkie trzy modele pozostają zachowane.

Pełny eksperyment uruchamia jedno polecenie:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\Training\Start-NeatDiscreteExperiment.ps1 -AllowDirty
```

Polecenie należy uruchomić dopiero po świadomej akceptacji kosztu 3 × 5M. Implementacyjny smoke opisany wyżej nie uruchomił żadnego pełnego runu ani końcowej walidacji 500 s.
