# Pipeline NEAT Continuous v1

Stan na 2026-09-15. NEAT Continuous v1 jest wariantem porównawczym gotowego NEAT Discrete v2. Korzysta bez zmian z Research Protocol v1, Observation v2 (`236 × float32`), `FixedUpdate=0.01 s`, decyzji co `0.05 s`, trzech żyć, Auto Turbo, sześciu workerów i `timeScale=20`. Nie zmienia gameplayu, Unity, PPO ani historycznych konfiguracji NEAT Discrete v1/v2.

## Jedyna główna zmienna eksperymentalna

NEAT-D v2 ma trzy wyjścia `LEFT/NONE/RIGHT` i wybiera akcję przez argmax. NEAT-C ma dokładnie jedno wyjście `tanh`, które bezpośrednio jest proporcjonalnym steeringiem:

- `-1.0`: maksymalny skręt w lewo;
- `0.0`: brak skrętu;
- `+1.0`: maksymalny skręt w prawo;
- wartości pośrednie: proporcjonalna część maksymalnych `±144 degrees/s`.

Python wymaga dokładnie jednego skończonego wyjścia, odrzuca `NaN`/`Inf` i zabezpieczająco ogranicza wynik do `[-1, 1]`. Nie ma argmax, deadzone, progów kierunku ani dyskretyzacji. Worker jest uruchamiany z `ActionSpace=Continuous`; istniejący bridge PPO Continuous koduje jeden `float32`, a handshake odrzuca niezgodną przestrzeń akcji. Nie powstał drugi system sterowania po stronie Unity.

## Zamrożona konfiguracja

Źródła konfiguracji to `Training/configs/neat_continuous_v1.json` i `Training/configs/neat_continuous_v1.ini`.

| Parametr | Wartość |
| --- | --- |
| biblioteka | `neat-python==2.0.0`, Python 3.11 |
| population | 64 |
| sieć | feed-forward, 236 wejść, 1 wyjście, 0 początkowych hidden nodes |
| activation / aggregation | `tanh` / `sum` |
| initial connection | `partial_direct 0.10` |
| compatibility threshold | 2.5 |
| elitism / survival threshold | 2 / 0.20 |
| node add / delete | 0.05 / 0.02 |
| connection add / delete | 0.20 / 0.10 |
| weight mutate power / rate / replace | 0.5 / 0.5 / 0.05 |
| fitness | `finalScore / 100 - 0.5 × lifeLossCount` |
| ocena genomu | średnia dokładnie 2 epizodów na wspólnej parze TRAIN seedów |
| workers / timeScale | 6 / 20 |
| MaxDuration treningu / okresowej walidacji | 300 s / 300 s |
| warunek końca | 200 ukończonych generacji |

`partial_direct 0.10` przy `236 × 1` utworzył w rzeczywistym preflight dokładnie 24 początkowe aktywne połączenia na genom. Jest to oczekiwany efekt zachowania tej samej względnej gęstości co w NEAT-D v2.

## Preflight specjacji

Przed zamrożeniem progu wykonano tylko preferowany wariant: population 64, 1 output, `partial_direct 0.10`, `compatibility_threshold=2.5`, trzy generacje, dwa wspólne TRAIN seedy na generację, sześć workerów i diagnostyczny `MaxDuration=30 s`. VALIDATION i TEST nie były ładowane.

Historia liczby species wyniosła `3 → 3 → 3 → 4`, a liczba TRAIN transitions `131726`. Cała historia mieści się w ustalonym zakresie akceptacji 2–8, nie wystąpił collapse ani eksplozja. Próg `2.5` został zachowany; nie uruchamiano wariantów 2.0 ani 3.0 i nie strojono progu według wyniku gry. Raport znajduje się w `Training/runs/neat-continuous-v1-speciation-preflight/speciation-preflight.{json,csv}`.

## Fitness i seedy

Fitness jest identyczny jak w NEAT-D v2:

```text
episodeFitness = finalScore / 100 - 0.5 * lifeLossCount
genomeFitness  = mean(two episodeFitness values)
```

Nie ma nagrody za pickupy, collision, gładkość, amplitudę ani bezruch. Wszystkie 64 genomy w generacji otrzymują dokładnie tę samą parę różnych seedów TRAIN. Deterministyczny scheduler przechodzi przez permutowane cykle 700 seedów na podstawie `ExperimentSeed` i jest częścią checkpointu. VALIDATION nie zmienia fitnessu, a TEST jest zabroniony.

## Trzy runy po 200 generacji

Orkiestrator wykonuje sekwencyjnie, nigdy równolegle:

1. `neat-continuous-v1-200g-run1`, seed `20260925`;
2. `neat-continuous-v1-200g-run2`, seed `20260926`;
3. `neat-continuous-v1-200g-run3`, seed `20260927`.

Każdy run kończy się dopiero po 200 pełnych generacjach. Granica 5M nie zatrzymuje treningu i generacja nigdy nie jest przerywana. Pipeline zapisuje numer generacji, cumulative TRAIN transitions, training-only wall-clock, total pipeline wall-clock, fitness, species oraz topologię championa.

## Checkpoint i resume

Po każdej generacji zapisywany i natychmiast próbnie ładowany jest recovery checkpoint. Natywny checkpoint `neat-python` utrwala populację, species, generację, RNG i innovation tracker; powiązany stan JSON utrwala scheduler TRAIN, transitions, czasy, efektywną konfigurację, historię walidacji oraz best validated genome. Resume sprawdza SHA-256 i zgodność algorytmu/przestrzeni akcji.

Dla generacji 50, 100, 150 i 200 powstają milestone metadata obejmujące transitions, oba czasy, species/genome count, fitness oraz topologię. Topologia wybranych genomów zawiera genome/species ID, aktywne i wyłączone połączenia, node genes, hidden nodes, `input_count=236`, `output_count=1` i warstwy feed-forward.

## Walidacja i wybór modelu

Aktualny champion jest walidowany po pierwszej generacji oraz po przekroczeniu kolejnych progów około 500k TRAIN transitions, maksymalnie raz po pełnej generacji. Walidacja zawsze obejmuje 100 zamrożonych seedów VALIDATION i `MaxDuration=300 s`. Best model zależy wyłącznie od najwyższego mean `finalScore`; training fitness i statystyki akcji nie biorą udziału w selekcji.

Po runie materializowane są trzy modele:

- `best_interaction_matched`: najlepszy zwalidowany model dostępny do pełnej granicy generacji obejmującej około 5 000 000 TRAIN transitions;
- `best_wallclock_matched`: najlepszy zwalidowany model dostępny w budżecie total pipeline wall-clock PPO Continuous;
- `best_200_generations`: najlepszy zwalidowany model z całej historii do 200 generacji, niekoniecznie champion generacji 200.

Budżet wall-clock jest odczytywany z `result.wall_seconds` manifestów PPO-C, a nie hardcodowany:

| Run PPO-C | Total pipeline wall-clock |
| --- | ---: |
| `ppo-continuous-5m-run1` | 4477.922 s |
| `ppo-continuous-5m-run2` | 4834.049 s |
| `ppo-continuous-5m-run3` | 5052.417 s |
| średnia | **4788.129 s (79.802 min)** |

Jeżeli manifestów brakuje, użytkownik może jawnie podać `-ComputeMatchSeconds`.

Po wszystkich runach maksymalnie dziewięć selekcji (`3 × 3`) jest walidowanych na 100 seedach VALIDATION z `MaxDuration=500 s`. Klucz `genome_sha256 + config_sha256` deduplikuje identyczne genome/checkpoint; ponowne użycie wyniku jest jawnie zapisane.

## Metryki

Summary zachowuje `finalScore`, `survivalTime`, `episodeFitness`, `lifeLossCount`, collisions, obstaclesAvoided, maxLevel, Heart, Shield, Boost, Gold, Diamond, turboActivations i terminal distribution wraz z mean/median/std tam, gdzie ma to zastosowanie.

Dla Continuous zapisuje dodatkowo, na podstawie rzeczywiście wysłanych i ograniczonych decyzji:

- `mean_abs_steering` i `mean_steering`;
- `steering_std`;
- `fraction_near_zero`: `abs(steering) < 0.1`;
- `fraction_near_max`: `abs(steering) > 0.9`;
- `fraction_left`: `steering < -0.1`;
- `fraction_right`: `steering > 0.1`.

Pola mają rolę `analytics_only_not_used_for_fitness_or_selection`.

## Publiczne skrypty i artefakty

- `Training/Start-NeatContinuousOvernight.ps1`: start jednego runu albo krótkiego smoke;
- `Training/Resume-NeatContinuous.ps1`: wznowienie z pełnego stanu po generacji;
- `Training/Validate-NeatContinuous.ps1`: ręczna walidacja genomu na VALIDATION;
- `Training/Start-NeatContinuousExperiment.ps1`: preflight, trzy runy, selekcje, deduplikowane walidacje 500 s, summary i kontrolowane zamknięcie workerów.

Główny workflow obsługuje `-RebuildWorker`, `-AllowDirty`, `-SkipExisting` i `-ComputeMatchSeconds`. `-SkipExisting` akceptuje preflight tylko przy zgodnym hashu konfiguracji, a run tylko przy statusie `complete`, właściwym seedzie, Continuous, 200 generacjach, trzech kompletnych selekcjach i poprawnych hashach modeli.

Z katalogu głównego repozytorium cały eksperyment uruchamia jedno polecenie:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Training\Start-NeatContinuousExperiment.ps1 -AllowDirty -SkipExisting
```

Po pełnym przebiegu powstaną:

- `Training/runs/neat-continuous-v1-experiment-summary.json`;
- `Training/runs/neat-continuous-v1-experiment-summary.csv`;
- `Training/runs/neat-continuous-v1-experiment.log`.

## Weryfikacja implementacyjna

Preflight został opisany wyżej. Dodatkowy smoke użył pełnej populacji 64 i `MaxDuration=5 s`:

| Etap | Generacja | Cumulative TRAIN transitions | Species | Total wall-clock | Training-only |
| --- | ---: | ---: | ---: | ---: | ---: |
| start | 1 | 13844 | 4 | 14.083 s | 6.974 s |
| resume | 2 | 27674 | 5 | 27.085 s | 14.065 s |

Checkpoint generacji 1 został wznowiony do generacji 2. Stan końcowy ma `output_count=1`, cztery zużyte seedy schedulera (`index=4`), poprawny budżet PPO-C i `checkpoint_load_verified=true`. Po preflight i obu sesjach smoke nie pozostał aktywny proces Research Worker.

Pełnych `3 × 200` ani walidacji 500 s nie uruchomiono podczas implementacji.

## TEST

Pipeline preflight i treningu ładuje `train.json`; walidacja ładuje `validation.json`. Żaden z etapów treningu, smoke, selekcji, extended validation ani summary nie odczytuje `test.json`.

**TEST: UNUSED FOR TRAINING/TUNING/EVALUATION.**
