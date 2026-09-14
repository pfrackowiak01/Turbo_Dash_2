# Pipeline PPO Continuous

Stan na 2026-09-14. PPO Continuous korzysta z tego samego Research Protocol v1, Observation v2 (`236 × float32`), reward v1, podziału seedów, workera standalone, TCP bridge’a, częstotliwości decyzji 20 Hz i fizyki co `0,01 s`, co PPO Discrete.

## Jedyna zmienna eksperymentalna

PPO-C różni się od PPO-D wyłącznie przestrzenią akcji:

```text
Box(low=-1.0, high=1.0, shape=(1,), dtype=float32)
-1.0 = maksymalny LEFT
 0.0 = NONE
+1.0 = maksymalny RIGHT
```

Wartości pośrednie proporcjonalnie skalują skręt. Publiczna konwencja continuous jest na granicy bridge’a mapowana na istniejący `SteeringAction`; nie powstał drugi system sterowania. Akcja jest sprawdzana pod kątem NaN/Infinity i ograniczana do `[-1,1]` po obu stronach transportu. Maksymalna prędkość obrotu pozostaje taka sama jak dla PPO-D: `12 × 12 = 144 degrees/s`. Nie zmieniono `EnvironmentMovement` ani fizyki.

Handshake wymaga zgodności action space. Python oczekujący Continuous odrzuca Unity Worker zgłaszający Discrete (i odwrotnie) przed pierwszym resetem.

## Konfiguracja i porównywalność

Źródłem ustawień jest `Training/configs/ppo_continuous_v1.json`. Parametry PPO Pilot v1 pozostają bez zmian: `MlpPolicy`, osobne sieci `pi=[256,256]` i `vf=[256,256]` z Tanh, learning rate `3e-4`, gamma `0.9995`, GAE lambda `0.95`, clip `0.2`, entropy `0.01`, value coefficient `0.5`, max gradient norm `0.5`, `n_steps=1024`, batch `512`, 10 epok i CPU. Pełny run używa 6 workerów, `timeScale=20`, 5 000 000 transitions, checkpointu co 250 000 i walidacji co 500 000.

Trening i smoke pobierają wyłącznie seedy TRAIN. Automatyczna i ręczna walidacja pobiera dokładnie 100 seedów VALIDATION. **TEST pozostaje UNUSED dla treningu, strojenia, smoke, orkiestracji i wyboru modelu.**

## Pojedynczy run i walidacja

Pełny pojedynczy run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-PpoContinuousOvernight.ps1 `
  -RunId ppo-continuous-5m-run1 -ExperimentSeed 20260916
```

Skrypt przyjmuje `RunId`, `Timesteps`, `Workers`, `TimeScale`, `ExperimentSeed`, `AllowDirty` i `RebuildWorker`. Trainer jest wspólny dla PPO-D/PPO-C; typ akcji wynika z konfiguracji, jest przekazywany do procesu Unity i potwierdzany w handshake’u. Checkpoint końcowy jest ponownie ładowany, a manifest zapisuje wynik tej kontroli.

Walidacja dowolnego modelu PPO-C na wszystkich 100 seedach VALIDATION:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Validate-PpoContinuous.ps1 `
  -Model .\Training\runs\<run-id>\best_model\model.zip `
  -RunId <validation-run-id> -Workers 6 -TimeScale 20 -MaxDuration 500
```

`MaxDuration` może wynosić 300 albo 500 s (dopuszczalna jest też inna dodatnia wartość diagnostyczna). Każda okresowa walidacja treningowa używa 300 s. `best_model/model.zip` jest zastępowany tylko po uzyskaniu większego mean `finalScore` na pełnych 100 seedach VALIDATION. `best_model/selection.json` zapisuje timestep, źródłowy checkpoint i pełny wynik walidacji 300 s.

## Automatyczny eksperyment 3-run

Użytkownik uruchamia cały eksperyment jednym poleceniem:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-PpoContinuousExperiment.ps1
```

Skrypt bez interakcji wykonuje sekwencyjnie:

1. `ppo-continuous-5m-run1`, seed `20260916`, 5M;
2. `ppo-continuous-5m-run2`, seed `20260917`, 5M;
3. `ppo-continuous-5m-run3`, seed `20260918`, 5M;
4. best model każdego runu na 100 seedach VALIDATION i `MaxDuration=500` pod nazwami `ppo-continuous-run1-best-validation-500`, `ppo-continuous-run2-best-validation-500`, `ppo-continuous-run3-best-validation-500`;
5. końcowe `Training/runs/ppo-continuous-experiment-summary.json` i `.csv`.

Błąd dowolnego etapu natychmiast zatrzymuje sekwencję. Każdy trainer/walidator jest właścicielem swoich workerów i zamyka je w `finally`. Log startu, końca i całkowitego czasu ściennego trafia do `Training/runs/ppo-continuous-experiment.log`. Opcjonalne `-SkipExisting` pomija tylko artefakt, którego manifest lub summary potwierdza właściwy action space, seed, budżet, liczbę seedów oraz MaxDuration; nie uznaje samej obecności katalogu za zakończenie.

Końcowy zwycięzca to run z największym mean `finalScore` w walidacji 500 s. Pozostałe modele nie są usuwane. JSON zachowuje pełne statystyki wymaganych metryk, a CSV podaje średnie i sumy metryk licznikowych. Żaden etap nie otwiera `test.json`.

## Katalogi wyników

Każdy trening ma standardowy układ `Training/runs/<run-id>/` z manifestem, konfiguracją, TensorBoardem, checkpointami, best modelem, walidacjami 300 s i logami workerów. Ręczne i końcowe walidacje zapisują `Training/runs/<validation-run-id>/validation/all-100/{episodes.csv,summary.json}`. Trzy modele best pozostają w katalogach run1–run3, niezależnie od wyboru końcowego zwycięzcy.
