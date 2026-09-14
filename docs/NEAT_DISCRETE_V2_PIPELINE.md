# Pipeline NEAT Discrete v2

Stan na 2026-09-14. NEAT Discrete v2 korzysta bez zmian z Research Protocol v1, Observation v2 (`236 × float32`), akcji `LEFT/NONE/RIGHT`, fizyki `FixedUpdate=0.01`, decyzji co `0.05 s`, trzech żyć, istniejącego fitnessu, sześciu workerów i `timeScale=20`. Nie zmienia gameplayu ani pipeline'ów PPO i nie dodaje NEAT Continuous.

## V1 i przyczyna v2

NEAT Discrete v1 był eksperymentem interaction-matched kończonym po około 5 000 000 przejść TRAIN. Używał `full_direct`, czyli 708 połączeń wejście–wyjście (`236 × 3`), oraz `compatibility_threshold=3.0`.

Faktyczne wyniki trzech runów v1:

| Run | Generacje | TRAIN transitions | Species min / mean / max / final |
| --- | ---: | ---: | --- |
| `neat-discrete-5m-run1` | 61 | 5 000 215 | 1 / 1 / 1 / 1 |
| `neat-discrete-5m-run2` | 63 | 5 008 235 | 1 / 1 / 1 / 1 |
| `neat-discrete-5m-run3` | 58 | 5 066 882 | 1 / 1 / 1 / 1 |

Pipeline był technicznie poprawny, lecz specjacja nie wpływała praktycznie na ewolucję. Pliki `neat_discrete_v1.json` i `.ini` pozostają niezmienioną konfiguracją historyczną.

## Pilot specjacji

Zainstalowany `neat-python==2.0.0` jawnie obsługuje `full_direct`, `partial_direct <fraction>` i `fs_neat_nohidden`. Dla `partial_direct 0.10` biblioteka losuje 10% z 708 możliwych bezpośrednich połączeń, czyli 71 połączeń na genom początkowy.

Najpierw wykonano bezkosztowy preflight początkowej populacji 64 genomów. Pokazał on:

| Initial connection | t=0.25 | t=0.5 | t=1.0 | t=1.5 | t=2.0 | t=2.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_direct` | 64 | 64 | 9 | 4 | 1 | 1 |
| `partial_direct 0.10` | 64 | 64 | 64 | 64 | 34 | 5 |
| `partial_direct 0.25` | 64 | 64 | 64 | 64 | 14 | 3 |
| `fs_neat_nohidden` | 64 | 64 | 62 | 58 | 57 | 7 |

Progi tworzące natychmiast 34–64 species zostały odrzucone bez kosztownego runtime. Pięć kandydatów uruchomiono następnie na tych samych parach seedów TRAIN: population 64, 2 epizody na genom, 3 generacje, 6 workerów, `timeScale=20`, diagnostyczny `MaxDuration=30`. Nie użyto VALIDATION do strojenia.

| Wariant | Historia species | TRAIN transitions | Końcowa średnia liczba aktywnych połączeń | Unikalne topologie | Pomocniczy fitness mean / max |
| --- | --- | ---: | ---: | ---: | ---: |
| `full_direct`, t=1.0 | 9→11→12→13 | 142 376 | 699.3 | 60 | 2.421 / 5.689 |
| `full_direct`, t=1.5 | 4→4→4→4 | 143 190 | 695.3 | 64 | 2.579 / 5.133 |
| `partial_direct 0.10`, t=2.5 | 5→5→6→6 | 129 445 | 70.4 | 41 | 2.569 / 5.335 |
| `partial_direct 0.25`, t=2.5 | 3→3→3→3 | 129 212 | 174.6 | 57 | 2.196 / 7.551 |
| `fs_neat_nohidden`, t=2.5 | 7→7→7→7 | 115 513 | 3.2 | 28 | 2.340 / 7.195 |

Wybrano `partial_direct 0.10` i `compatibility_threshold=2.5`. Uzasadnienie jest strukturalne:

- stabilne 5–6 species leży w preferowanym zakresie 3–8;
- brak wzrostu podobnego do `full_direct/1.0` i brak collapse do jednej species;
- około dziesięciokrotnie mniej połączeń początkowych niż w v1 pozostawia przestrzeń dla rozwoju topologii;
- widoczna jest różnorodność topologii i pojawiają się węzły ukryte;
- pomocniczy fitness nie wskazuje kompletnej niezdolności do uczenia względem pełnego startu;
- `fs_neat_nohidden` jest znacznie bardziej skrajny (3 połączenia) i krótki pilot nie uzasadnia ryzyka wolniejszego rozruchu pełnego eksperymentu.

Pełny raport pilota jest zapisywany jako `Training/runs/neat-discrete-v2-speciation-pilot/speciation-pilot.{json,csv}`. Najdłuższy wariant zużył 143 190 przejść, poniżej limitu 300–500k.

## Zamrożona konfiguracja v2

Źródła konfiguracji to `Training/configs/neat_discrete_v2.json` i `.ini`.

| Parametr | Wartość |
| --- | --- |
| biblioteka | `neat-python==2.0.0`, Python 3.11 |
| population | 64 |
| sieć | feed-forward, 236 wejść, 3 wyjścia, 0 początkowych hidden nodes |
| initial connection | `partial_direct 0.10` |
| activation / aggregation | `tanh` / `sum` |
| compatibility threshold | 2.5 |
| elitism / survival threshold | 2 / 0.20 |
| node add / delete | 0.05 / 0.02 |
| connection add / delete | 0.20 / 0.10 |
| weight mutate power / rate / replace | 0.5 / 0.5 / 0.05 |
| fitness | `finalScore / 100 - 0.5 × lifeLossCount` |
| ocena genomu | średnia dokładnie 2 epizodów na wspólnej parze TRAIN seedów |
| workers / timeScale | 6 / 20 |
| MaxDuration treningu / okresowej walidacji | 300 s / 300 s |
| główny warunek końca | 200 ukończonych generacji |

Akcja jest unikalnym `argmax` trzech wyjść; każdy dokładny remis daje `NONE`. Scheduler przechodzi deterministycznie przez przetasowane cykle wszystkich 700 seedów TRAIN. Generacja nigdy nie jest przerywana.

## Jeden run i pomiary czasu

Jeden run trwa do `generation == 200`, niezależnie od liczby przejść. Przez cały czas zapisuje:

- cumulative TRAIN transitions, liczone wyłącznie z odebranych `STEP_RESULT` treningu;
- elapsed total wall-clock, obejmujący trening, start/stop workerów, walidacje, checkpointy i orkiestrację runu;
- elapsed training-only wall-clock, mierzony wyłącznie wokół ewaluacji i reprodukcji generacji;
- species count, fitness i topologię championa każdej generacji.

Resume dodaje czas nowego procesu do wartości utrwalonej w ostatnim pełnym checkpoincie. Czas pracy utraconej po ostatnim checkpoincie nie jest zaliczany, tak jak niedokończona generacja i jej przejścia.

## Checkpointy i resume

Pełny recovery checkpoint powstaje po każdej generacji. Zawiera natywną populację/species/config/RNG/innovation tracker oraz sparowany stan schedulera, transitions, czasy, historię walidacji i best model.

Dla generacji 50, 100, 150 i 200 powstają dodatkowe wskaźniki `milestones/generation-NNN.json`. Metadane każdego checkpointu obejmują:

- generation i cumulative TRAIN transitions;
- total oraz training-only wall-clock;
- species count i genome count;
- najlepszy fitness generacji i najlepszy fitness dotychczas;
- ID aktualnego championa oraz pełne metryki jego topologii;
- informację, czy checkpoint jest milestone'em.

Po każdym zapisie trainer natychmiast ładuje checkpoint i sprawdza generację oraz klucze populacji. Resume weryfikuje SHA-256 checkpointu, konfiguracji, best genome i wszystkich archiwów walidacji.

## Walidacja 300 s i archiwum modeli

Champion jest walidowany na wszystkich 100 seedach VALIDATION:

1. po pierwszej ukończonej generacji;
2. po przekroczeniu kolejnych progów około 500 000 TRAIN transitions;
3. maksymalnie raz po generacji.

Każda walidacja archiwizuje genom, konfigurację, summary, hashe, generation, transitions, oba czasy i topologię. `best_model` jest aktualizowany wyłącznie przy ściśle większym mean `finalScore @ 300 s`; training fitness nie uczestniczy w wyborze.

## Trzy budżety

Po generacji 200 ten sam run materializuje trzy modele:

### Interaction matched

`best_interaction_matched` to najlepszy według mean `finalScore @ 300 s` model dostępny do pierwszego pełnego punktu walidacyjnego obejmującego granicę 5 000 000 TRAIN transitions. Jeżeli generacja przekroczy granicę, zapisywana jest rzeczywista liczba przejść tego pełnego punktu; nie przerywa się generacji.

### Wall-clock matched

`best_wallclock_matched` to najlepszy zwalidowany model dostępny przed przekroczeniem budżetu total pipeline wall-clock PPO-D. Pipeline odczytuje `result.wall_seconds` z manifestów:

- `ppo-discrete-5m-run1`: 5667.745 s;
- `ppo-discrete-5m-run2`: 5758.277 s;
- `ppo-discrete-5m-run3`: 6235.511 s.

Średnia wynosi `5887.178 s`, czyli `98.120 min`. Manifest zapisuje wartości źródłowe i jawnie oznacza podstawę jako total pipeline wall-clock. Gdy manifestów brakuje, wymagany jest parametr `-ComputeMatchSeconds`.

### Extended 200 generations

`best_200_generations` to najlepszy według mean `finalScore @ 300 s` genom spośród całej historii walidacji do generacji 200. Nie zakłada się, że champion generacji 200 jest najlepszy.

Każda selekcja zapisuje generation, genome/species ID, transitions, oba czasy, metryki 300 s, hashe oraz topologię.

## Extended validation i deduplikacja

Po trzech runach orkiestrator planuje 9 selekcji (`3 runy × 3 budżety`). Klucz deduplikacji to `genome_sha256 + config_sha256`. Jeśli dwa budżety wskazują ten sam model, wykonywana jest jedna walidacja na 100 seedach VALIDATION z `MaxDuration=500`, a drugi wpis wskazuje wykorzystany summary i ma `reused=true`.

Summary JSON i CSV zawierają dla każdego budżetu mean/median/std `finalScore`, `survivalTime`, `lifeLossCount`, collisions, obstaclesAvoided, maxLevel, Heart, Shield, Boost, Gold, Diamond, turboActivations oraz terminal distribution.

Metryki topologii obejmują aktywne i wyłączone połączenia, liczbę node genes, łączną liczbę wejść+węzłów, hidden nodes, input/output count, species/genome ID oraz liczbę warstw feed-forward zwracaną przez narzędzia grafowe biblioteki.

## Orkiestrator i artefakty

`Start-NeatDiscreteV2Experiment.ps1` wykonuje sekwencyjnie:

1. `neat-discrete-v2-200g-run1`, seed `20260922`;
2. `neat-discrete-v2-200g-run2`, seed `20260923`;
3. `neat-discrete-v2-200g-run3`, seed `20260924`;
4. wybór trzech budżetów w każdym runie;
5. deduplikowane walidacje 500 s;
6. końcowe `Training/runs/neat-discrete-v2-experiment-summary.json`, `.csv` i `.log`;
7. kontrolowane zamknięcie workerów po każdym etapie.

`-SkipExisting` uznaje run tylko po sprawdzeniu manifestu, 200 generacji, seedów, statusu TEST i hashy trzech modeli. `-RebuildWorker` wymusza świeży standalone build, a `-AllowDirty` jawnie dopuszcza bieżący stan repozytorium.

## Weryfikacja implementacyjna

Wykonany smoke użył pełnej population 64, dwóch TRAIN seedów na genom, sześciu workerów i diagnostycznego `MaxDuration=5`:

| Etap | Generacja | Cumulative transitions | Species | Total wall-clock | Training-only |
| --- | ---: | ---: | ---: | ---: | ---: |
| start | 1 | 14 110 | 5 | 14.017 s | 7.241 s |
| resume | 2 | 28 397 | 5 | 27.549 s | 14.944 s |

Powstało 256 epizodów (`64 × 2 × 2`), checkpointy generacji 1 i 2 przeszły load check, scheduler po resume wskazuje cztery zużyte seedy, a workery zostały zamknięte. Smoke nie wykonywał kosztownej walidacji 100-seed.

Pełne `3 × 200` oraz walidacje 500 s nie zostały uruchomione podczas implementacji.

## TEST

Pipeline ładuje tylko `train.json` oraz `validation.json`. `test.json` nie jest odczytywany przez pilot, trening, wybór modeli, smoke, resume, extended validation ani summary.

**TEST: UNUSED FOR TRAINING/TUNING/EVALUATION.**
