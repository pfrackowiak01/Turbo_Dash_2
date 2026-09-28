# Przebiegi wykorzystane w pracy magisterskiej

To odchudzony eksport danych, nie pełne archiwum do wznawiania treningów. Oryginały pozostają lokalnie w `Training/runs-original/` (poza Git). Zachowano wszystkie trzy przebiegi każdej serii, również słabsze wyniki i pilota NEAT-D v1. Pliki skopiowano bez zmiany zawartości; nie usuwano pojedynczych epizodów.

Eksport: **2931 plików źródłowych, 70.23 MiB**. Pełne archiwum: **1.78 GiB**. Liczby nie obejmują tego README i manifestu eksportu.

[Manifest eksportu](review_export_manifest.json) zawiera SHA-256 każdego skopiowanego pliku oraz liczbę i rozmiar pominiętych plików według katalogów. [Skrypt eksportu](../export_review_runs.py) definiuje jawne reguły doboru.

## Główne przebiegi

- [ppo-discrete-5m-run1](ppo-discrete-5m-run1/)
- [ppo-discrete-5m-run2](ppo-discrete-5m-run2/)
- [ppo-discrete-5m-run3](ppo-discrete-5m-run3/)
- [ppo-continuous-5m-run1](ppo-continuous-5m-run1/)
- [ppo-continuous-5m-run2](ppo-continuous-5m-run2/)
- [ppo-continuous-5m-run3](ppo-continuous-5m-run3/)
- [neat-discrete-5m-run1](neat-discrete-5m-run1/)
- [neat-discrete-5m-run2](neat-discrete-5m-run2/)
- [neat-discrete-5m-run3](neat-discrete-5m-run3/)
- [neat-discrete-v2-200g-run1](neat-discrete-v2-200g-run1/)
- [neat-discrete-v2-200g-run2](neat-discrete-v2-200g-run2/)
- [neat-discrete-v2-200g-run3](neat-discrete-v2-200g-run3/)
- [neat-continuous-v1-200g-run1](neat-continuous-v1-200g-run1/)
- [neat-continuous-v1-200g-run2](neat-continuous-v1-200g-run2/)
- [neat-continuous-v1-200g-run3](neat-continuous-v1-200g-run3/)

W każdym przebiegu zacznij od `manifest.json` i `config.json`. PPO: `training_summary.csv`, `validation/`, `best_model/`, `tensorboard/`. NEAT: `generation_metrics.csv`, `training_episodes.csv`, `neat_config.ini`, `validation/`, `best_model/`; w v2/C także `validation_archive/`, `validation_history.json`, `selected_models/` i `milestones/`.

## Walidacja 500 s i specjacja

- [ppo-1m-validation-500-r1](ppo-1m-validation-500-r1/)
- [ppo-4m-validation-500-r1](ppo-4m-validation-500-r1/)
- [ppo-run2-best-validation-500](ppo-run2-best-validation-500/)
- [ppo-run3-best-validation-500](ppo-run3-best-validation-500/)
- [ppo-continuous-run1-best-validation-500](ppo-continuous-run1-best-validation-500/)
- [ppo-continuous-run2-best-validation-500](ppo-continuous-run2-best-validation-500/)
- [ppo-continuous-run3-best-validation-500](ppo-continuous-run3-best-validation-500/)
- [neat-discrete-run1-best-validation-500](neat-discrete-run1-best-validation-500/)
- [neat-discrete-run2-best-validation-500](neat-discrete-run2-best-validation-500/)
- [neat-discrete-run3-best-validation-500](neat-discrete-run3-best-validation-500/)
- [neat-discrete-v2-extended-validation-500](neat-discrete-v2-extended-validation-500/)
- [neat-continuous-v1-extended-validation-500](neat-continuous-v1-extended-validation-500/)
- [neat-discrete-v2-speciation-pilot](neat-discrete-v2-speciation-pilot/)
- [neat-continuous-v1-speciation-preflight](neat-continuous-v1-speciation-preflight/)

## Zestawienia serii

- [ppo-continuous-experiment-summary](./ppo-continuous-experiment-summary.csv) ([JSON](./ppo-continuous-experiment-summary.json))
- [neat-discrete-experiment-summary](./neat-discrete-experiment-summary.csv) ([JSON](./neat-discrete-experiment-summary.json))
- [neat-discrete-v2-experiment-summary](./neat-discrete-v2-experiment-summary.csv) ([JSON](./neat-discrete-v2-experiment-summary.json))
- [neat-continuous-v1-experiment-summary](./neat-continuous-v1-experiment-summary.csv) ([JSON](./neat-continuous-v1-experiment-summary.json))

## Zakres i ograniczenia

Pominięto obszerne logi workerów, duplikaty CSV z Unity, sesje techniczne, większość pośrednich checkpointów oraz pomocnicze i nieudane próby techniczne niewykorzystane w tych seriach. Wyjątkiem są dwa checkpointy PPO wskazane w zamrożonym manifeście wyboru finalnych modeli. Genomy walidacyjne NEAT zachowano.

Historyczne manifesty nadal zawierają pierwotne ścieżki lokalne. Brakujące pliki diagnostyczne/checkpointy znajdują się wyłącznie w archiwum oryginalnym. Eksport nie służy do kontynuowania istniejących treningów; uruchamiaj nowe eksperymenty w osobnej kopii roboczej. Nie wymaga ponownego wykonania TEST.

[Wyniki końcowego TEST](../final_test/) · [Znane ograniczenia i instrukcje projektu](../../README.md)
