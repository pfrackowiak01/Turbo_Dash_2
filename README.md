# Turbo Dash

Turbo Dash to mobilna gra 3D typu endless runner: gracz unika przeszkód wewnątrz tunelu i na jego zewnętrznej powierzchni, zbiera klejnoty oraz aktywuje turbo. Wrażenie biegu powstaje przez przesuwanie tub w stronę gracza i obracanie otoczenia. Zaimplementowano sterowanie żyroskopem oraz dotykiem/strzałkami.

Projekt powstał na potrzeby pracy inżynierskiej Pawła Frąckowiaka **„Projekt i implementacja gry mobilnej typu endless runner z wykorzystaniem sterowania żyroskopowego”** (2024). Następnie został rozszerzony o środowisko badawcze do pracy magisterskiej **„Opracowanie i analiza algorytmów uczenia maszynowego do sterowania agentem w grze typu endless runner.”** Repozytorium łączy grę Unity, kod eksperymentów w Pythonie oraz zapisane wyniki końcowego porównania metod **RuleBasedV1, PPO-D, PPO-C, NEAT-D i NEAT-C**. Oznaczenia D i C odnoszą się odpowiednio do dyskretnej i ciągłej przestrzeni akcji.

## Przewodnik po części badawczej

Do zapoznania się z kodem, tabelami i wykresami wystarczy przeglądarka repozytorium — nie trzeba instalować Unity ani ponownie uruchamiać eksperymentów.

| Od czego zacząć | Materiał |
| --- | --- |
| Wyniki porównania pięciu metod | [Raport końcowego TEST](Training/final_test/FINAL_TEST_REPORT.md) i [wykresy](Training/final_test/plots/) |
| Warunki eksperymentu i sposób analizy | [Protokół końcowego TEST](docs/FINAL_TEST_PROTOCOL.md) oraz [zamrożona konfiguracja JSON](Training/final_test/final_test_protocol.json) |
| Które modele wybrano i dlaczego | [Manifest wyboru modeli](Training/final_test/final_model_selection.json): przebiegi, checkpointy, wyniki VALIDATION i SHA-256 |
| Jak Unity współpracuje z Pythonem | [Środowisko badawcze](docs/ML_RESEARCH_ENVIRONMENT.md) i [kontrakt Research Protocol v1](docs/RESEARCH_PROTOCOL_V1.md) |
| Treningi, konfiguracje i skrypty | [Mapa katalogu Training](#katalog-training) i [przewodnik po algorytmach](#algorytmy-konfiguracje-i-skrypty) |
| Dane i przebiegi | [Wyniki FINAL TEST](#wyniki-końcowego-test) oraz [dostępność artefaktów treningowych](#przebiegi-i-dostępność-artefaktów) |
| Weryfikacja oprogramowania | [Testy i diagnostyka](#testy-i-diagnostyka) |
| Uruchomienie zwykłej gry | [Wymagania Unity](#unity-i-wymagania) i [instrukcja uruchomienia](#jak-uruchomić) |

## Stan projektu

Treningi i wybór reprezentantów metod zostały zakończone. Zapisany końcowy TEST obejmuje **3000 epizodów: 5 metod × 200 seedów × 3 powtórzenia**, z progiem zakończenia `MaxDuration=500 s`. Źródłem stanu wykonania jest [manifest TEST](Training/final_test/final_test_run_manifest.json), a wyników — [raport](Training/final_test/FINAL_TEST_REPORT.md) i [surowy CSV](Training/final_test/raw/final_test_episodes.csv). Raport nie wskazuje jednoznacznego zwycięzcy; najwyższą średnią uzyskało PPO-D, bez istotnego rozdzielenia od NEAT-C w zastosowanej analizie.

Dokumentacja powstawała etapami. Starsze opisy architektury i audytu dotyczą wersji bazowej, a dokumenty pipeline'ów opisują stan z dnia ich opracowania. Wpisy typu „TEST nieużyty” w dokumentacji przygotowawczej nie oznaczają, że końcowy eksperyment nie został później wykonany. Przy interpretacji wyników należy korzystać z manifestów i artefaktów danego etapu.

### Ograniczenia istotne przy lekturze wyników

- Finalny RuleBasedV1 jest wykonywany przez [adapter Pythona](Training/turbodash/final_rule_based.py). [Zapisany test różnicowy C#–Python](Training/final_test/rulebased_parity_verification.json) ma status **FAIL: 11 999 z 12 000 zgodnych akcji**. Nie należy deklarować pełnej równoważności portu z oryginalnym kontrolerem C#.
- Deterministyczny wybór akcji nie gwarantuje identycznych długich trajektorii Unity. Rozrzut powtórzeń dokumentuje [tabela niedeterministyczności](Training/final_test/analysis/nondeterminism_summary.csv).
- `MaxDuration` jest progiem sprawdzanym w `LateUpdate`, a nie ścisłym odcięciem dokładnie w 500 s. Zapisane czasy epizodów `MaxDuration` sięgają około 506,67 s; [kod zakończenia epizodu](Assets/Turbo_Dash/Code/Research/ResearchMode.cs) i [dane źródłowe](Training/final_test/raw/final_test_episodes.csv) pozwalają sprawdzić tę różnicę.
- `finalScore` jest punktacją gry, nie fizycznym dystansem. Główna analiza porównuje średnie z trzech powtórzeń na seed, czyli 200 sparowanych obserwacji na metodę. Brak istotnej różnicy nie jest dowodem równoważności metod.

## Katalog Training

[Training/](Training/) zawiera Pythonową część środowiska, konfiguracje, skrypty PowerShell oraz opublikowane artefakty końcowej ewaluacji. Symulacja i mechanika gry pozostają w Unity; Python uruchamia workery, przekazuje akcje przez lokalny TCP, prowadzi uczenie, walidację i zapis wyników.

| Katalog lub plik | Zawartość |
| --- | --- |
| [Training/turbodash/](Training/turbodash/) | Implementacja treningu, inferencji, komunikacji, selekcji modeli i analizy |
| [Training/configs/](Training/configs/) | Konfiguracje PPO oraz konfiguracje pipeline'ów i ewolucji NEAT |
| [Training/tests/](Training/tests/) | Automatyczne testy Pythonowe protokołu, konfiguracji, adapterów, checkpointów i analizy |
| [Training/final_test/](Training/final_test/) | Raport, protokół, manifesty, surowe dane, statystyki i wykresy końcowego porównania |
| `Training/runs/` — lokalnie, poza Git | Pełne przebiegi: checkpointy, genomy, logi TensorBoard, walidacje i manifesty treningów |
| [requirements.txt](Training/requirements.txt) / [requirements-lock.txt](Training/requirements-lock.txt) | Wymagania oraz zapis wersji zależności; historyczne środowiska konkretnych przebiegów opisują ich manifesty |
| [Skrypty PowerShell](Training/) | Przygotowanie środowiska, build workera, treningi, walidacja, resume i diagnostyka |
| [plot_w5_neat_species.py](Training/plot_w5_neat_species.py) | Generator wykresu liczby gatunków NEAT-D v1/v2 |

### Najważniejsze moduły implementacji

| Obszar | Kod |
| --- | --- |
| Unity: epizod, obserwacje i reward | [ResearchMode](Assets/Turbo_Dash/Code/Research/ResearchMode.cs), [ObservationProvider](Assets/Turbo_Dash/Code/Research/ObservationProvider.cs), [ResearchProtocolV1](Assets/Turbo_Dash/Code/Research/ResearchProtocolV1.cs) |
| Unity: baseline i komunikacja | [RuleBasedController](Assets/Turbo_Dash/Code/Research/RuleBasedController.cs), [ResearchWorkerBridge](Assets/Turbo_Dash/Code/Research/ResearchWorkerBridge.cs) |
| Python: workery i środowisko SB3 | [worker.py](Training/turbodash/worker.py), [transport.py](Training/turbodash/transport.py), [protocol.py](Training/turbodash/protocol.py), [vec_env.py](Training/turbodash/vec_env.py) |
| PPO: uczenie i checkpointy | [train.py](Training/turbodash/train.py), [callbacks.py](Training/turbodash/callbacks.py) |
| NEAT: ewolucja i ocena populacji | [neat_v2_train.py](Training/turbodash/neat_v2_train.py), [neat_evaluation.py](Training/turbodash/neat_evaluation.py), [neat_checkpoint.py](Training/turbodash/neat_checkpoint.py) |
| NEAT: wybór modeli i walidacja 500 s | [neat_v2_selection.py](Training/turbodash/neat_v2_selection.py), [neat_v2_finalize.py](Training/turbodash/neat_v2_finalize.py), [neat_continuous_finalize.py](Training/turbodash/neat_continuous_finalize.py) |
| Wspólna walidacja i seedy | [validation.py](Training/turbodash/validation.py), [seeds.py](Training/turbodash/seeds.py), [katalogi TRAIN / VALIDATION / TEST](Assets/Turbo_Dash/Research/Seeds/) |
| Końcowa ewaluacja i statystyka | [final_test_runner.py](Training/turbodash/final_test_runner.py), [final_test_analysis.py](Training/turbodash/final_test_analysis.py) |

## Algorytmy, konfiguracje i skrypty

PPO korzysta ze Stable-Baselines3, NEAT z neat-python. Wszystkie porównywane metody otrzymują Observation v2 (`236 × float32`); decyzja zapada co 0,05 s przy kroku fizyki 0,01 s. Szczegóły wejść, akcji i nagrody opisuje [Research Protocol v1](docs/RESEARCH_PROTOCOL_V1.md).

| Metoda | Dokumentacja | Konfiguracja | Skrypt treningu |
| --- | --- | --- | --- |
| RuleBasedV1 | [Pilot i reguły kontrolera](docs/RULE_BASED_PILOT.md) | [Parametry w kodzie C#](Assets/Turbo_Dash/Code/Research/RuleBasedController.cs) | Bez treningu; [adapter inferencji](Training/turbodash/final_rule_based.py) |
| PPO-D | [Pipeline PPO discrete](docs/PPO_TRAINING_PIPELINE.md) | [ppo_pilot_v1.json](Training/configs/ppo_pilot_v1.json) | [Start-PpoDiscreteOvernight.ps1](Training/Start-PpoDiscreteOvernight.ps1) |
| PPO-C | [Pipeline PPO continuous](docs/PPO_CONTINUOUS_PIPELINE.md) | [ppo_continuous_v1.json](Training/configs/ppo_continuous_v1.json) | [Start-PpoContinuousExperiment.ps1](Training/Start-PpoContinuousExperiment.ps1) |
| NEAT-D v1 — pilot | [Pierwsza konfiguracja NEAT-D](docs/NEAT_DISCRETE_PIPELINE.md) | [Pipeline JSON](Training/configs/neat_discrete_v1.json), [NEAT INI](Training/configs/neat_discrete_v1.ini) | [Start-NeatDiscreteExperiment.ps1](Training/Start-NeatDiscreteExperiment.ps1) |
| NEAT-D v2 — wariant finalny | [Specjacja i budżety v2](docs/NEAT_DISCRETE_V2_PIPELINE.md) | [Pipeline JSON](Training/configs/neat_discrete_v2.json), [NEAT INI](Training/configs/neat_discrete_v2.ini) | [Start-NeatDiscreteV2Experiment.ps1](Training/Start-NeatDiscreteV2Experiment.ps1) |
| NEAT-C | [Pipeline NEAT continuous](docs/NEAT_CONTINUOUS_PIPELINE.md) | [Pipeline JSON](Training/configs/neat_continuous_v1.json), [NEAT INI](Training/configs/neat_continuous_v1.ini) | [Start-NeatContinuousExperiment.ps1](Training/Start-NeatContinuousExperiment.ps1) |

Skrypty pomocnicze:

- Walidacja: [PPO-D](Training/Validate-PpoDiscrete.ps1), [PPO-C](Training/Validate-PpoContinuous.ps1), [NEAT-D](Training/Validate-NeatDiscrete.ps1), [NEAT-C](Training/Validate-NeatContinuous.ps1).
- Wznowienie: [PPO](Training/Resume-PpoDiscrete.ps1), [NEAT-D v1](Training/Resume-NeatDiscrete.ps1), [NEAT-D v2](Training/Resume-NeatDiscreteV2.ps1), [NEAT-C](Training/Resume-NeatContinuous.ps1). Warunki i argumenty opisują odpowiednie dokumenty pipeline'ów.
- Przygotowanie: [Setup-Venv.ps1](Training/Setup-Venv.ps1), [Build-ResearchWorker.ps1](Training/Build-ResearchWorker.ps1), [kod builda Unity](Assets/Turbo_Dash/Code/Research/Editor/ResearchWorkerBuild.cs).

Konfiguracja bazowa może być nadpisana argumentami skryptu. Do opisu wykonanego eksperymentu służą jego efektywny `config.json` i `manifest.json`, nie tylko plik w `configs/`. Przykładowo bazowe PPO-D ma cztery workery, a właściwe przebiegi treningowe korzystały z sześciu.

## Przebiegi i dostępność artefaktów

**Pełny katalog `Training/runs/` nie jest publikowany w Git** — wyklucza go [.gitignore](.gitignore). Samo sklonowanie repozytorium nie dostarcza wag PPO, genomów NEAT ani plików zdarzeń TensorBoard. Odwołania do tych lokalnych ścieżek w manifestach identyfikują artefakty eksperymentu; nie są linkami do dostępnych plików. Ponowne wykonanie inferencji zamrożonych modeli wymaga tych artefaktów oraz builda workera Unity.

Identyfikatory serii pozwalające odnaleźć przebiegi w lokalnym archiwum:

| Seria | Katalogi lokalne w `Training/runs/` | Zakres |
| --- | --- | --- |
| PPO-D | `ppo-discrete-5m-run{1,2,3}` | Trzy przebiegi; cel 5 mln przejść każdy |
| PPO-C | `ppo-continuous-5m-run{1,2,3}` | Trzy przebiegi; cel 5 mln przejść każdy |
| NEAT-D v1 | `neat-discrete-5m-run{1,2,3}` | Pilot kończony po około 5 mln przejść |
| NEAT-D v2 | `neat-discrete-v2-200g-run{1,2,3}` | Trzy przebiegi po 200 generacji |
| NEAT-C | `neat-continuous-v1-200g-run{1,2,3}` | Trzy przebiegi po 200 generacji |

Zapis `{1,2,3}` oznacza trzy osobne katalogi z odpowiednim numerem przebiegu.

W katalogu przebiegu należy szukać `manifest.json`, `config.json`, `checkpoints/`, `best_model/` i wyników walidacji. PPO zapisuje ponadto `training_summary.csv` i `tensorboard/`; NEAT — `neat_config.ini`, `generation_metrics.csv`, `training_episodes.csv`, a w pipeline v2/C także `validation_archive/` i `selected_models/`. Strukturę opisują dokumenty [PPO](docs/PPO_TRAINING_PIPELINE.md) i [NEAT v2](docs/NEAT_DISCRETE_V2_PIPELINE.md).

Materiały dostępne bez lokalnego archiwum:

- [Manifest finalnego wyboru](Training/final_test/final_model_selection.json) — identyfikatory wybranych przebiegów/modeli, porównanie kandydatów na VALIDATION 500 s i hashe.
- [W5 — liczba gatunków NEAT-D v1/v2](docs/figures/W5_neat_species.md) — opis zestawienia sześciu przebiegów; [PNG](docs/figures/W5_neat_species.png), [PDF](docs/figures/W5_neat_species.pdf), [SVG](docs/figures/W5_neat_species.svg), [punkty CSV](docs/figures/W5_neat_species.csv), [metadane i hashe źródeł](docs/figures/W5_neat_species.json).
- [Schemat Unity–Python](docs/figures/unity_python_architecture.png) — pomocnicza ilustracja architektury; szczegóły implementacji opisuje [dokumentacja środowiska](docs/ML_RESEARCH_ENVIRONMENT.md).
- [Wyniki końcowego TEST](Training/final_test/) — surowe epizody, agregaty, statystyki i wykresy.

### TensorBoard

Przy dostępnych lokalnych logach i przygotowanym środowisku Pythona, z katalogu głównego repozytorium:

```powershell
.\Training\Start-TensorBoard.ps1
```

Panel jest dostępny pod `http://localhost:6006`; [skrypt](Training/Start-TensorBoard.ps1) czyta `Training/runs/` i nie uruchamia treningu. Bez lokalnych event files nie pokaże historycznych krzywych. Metryki `rollout/ep_rew_mean` i `rollout/ep_len_mean` opisują trening — nie zastępują wyników VALIDATION.

## Wyniki końcowego TEST

| Materiał | Bezpośredni odnośnik |
| --- | --- |
| Raport do czytania | [FINAL_TEST_REPORT.md](Training/final_test/FINAL_TEST_REPORT.md) |
| Wyniki maszynowo czytelne | [final_test_results.json](Training/final_test/final_test_results.json) |
| Surowe 3000 epizodów | [final_test_episodes.csv](Training/final_test/raw/final_test_episodes.csv) |
| Agregacja po seedach | [final_test_per_seed.csv](Training/final_test/final_test_per_seed.csv) |
| Podsumowanie metod | [final_test_method_summary.csv](Training/final_test/final_test_method_summary.csv) |
| Porównania par i korekta Holma | [final_test_pairwise_statistics.csv](Training/final_test/final_test_pairwise_statistics.csv) |
| Metryki strategii i akcji | [Strategie](Training/final_test/final_test_strategy_metrics.csv), [telemetria akcji](Training/final_test/final_test_action_analytics.csv) |
| VALIDATION a TEST | [final_test_generalization.csv](Training/final_test/final_test_generalization.csv) |
| Analizy dodatkowe | [Friedman](Training/final_test/analysis/final_test_omnibus.json), [przeżycie](Training/final_test/analysis/survival_summary.csv), [rozrzut powtórzeń i ICC](Training/final_test/analysis/nondeterminism_summary.csv), [pozostałe analizy](Training/final_test/analysis/) |
| Ślad wykonania | [Manifest](Training/final_test/final_test_run_manifest.json), [harmonogram](Training/final_test/test_schedule.json), [zapis postępu](Training/final_test/final_test_progress.json) |
| Plan i implementacja | [Protokół](docs/FINAL_TEST_PROTOCOL.md), [runner](Training/turbodash/final_test_runner.py), [kod obliczeń i wykresów](Training/turbodash/final_test_analysis.py) |

Wybrane wykresy: [rozkład finalScore](Training/final_test/plots/01_finalScore_violin_box.png), [ECDF](Training/final_test/plots/02_finalScore_ecdf.png), [Kaplan–Meier](Training/final_test/plots/04_survival_kaplan_meier.png), [przedziały różnic między metodami](Training/final_test/plots/06_pairwise_finalScore_difference_forest.png), [profile akcji dyskretnych](Training/final_test/plots/10_discrete_action_profiles.png), [sterowanie ciągłe](Training/final_test/plots/11_continuous_steering_profiles.png). Wszystkie 15 wykresów znajduje się w [plots/](Training/final_test/plots/).

[Start-FinalTestExperiment.ps1](Training/Start-FinalTestExperiment.ps1) jest skryptem wykonania eksperymentu, **nie przeglądarką wyników ani zwykłym testem jednostkowym**. Do przeglądu zakończonego badania należy korzystać z powyższych plików; nie ma potrzeby ponownego uruchamiania TEST.

## Testy i diagnostyka

| Rodzaj weryfikacji | Materiały |
| --- | --- |
| Testy Pythonowe | [Wszystkie testy](Training/tests/); m.in. [protokół](Training/tests/test_protocol.py), [VecEnv](Training/tests/test_vec_env.py), [seedy](Training/tests/test_seeds.py), [walidacja](Training/tests/test_validation.py), [checkpointy NEAT](Training/tests/test_neat_checkpoint.py), [kontrakt i analiza finalnego eksperymentu](Training/tests/test_final_test.py) |
| Historyczna weryfikacja gry i Research Mode | [BASELINE_VERIFICATION.md](docs/BASELINE_VERIFICATION.md) — opis wykonanych scenariuszy Play Mode, zakres i ograniczenia |
| Bridge, standalone, benchmark i smoke PPO | [PPO_SMOKE_TEST.md](docs/PPO_SMOKE_TEST.md), [bridge_verify.py](Training/turbodash/bridge_verify.py), [Run-StandaloneParity.ps1](Training/Run-StandaloneParity.ps1) |
| Zgodność RuleBased C#–Python | [Verify-RuleBasedParity.ps1](Training/Verify-RuleBasedParity.ps1), [syntetyczny korpus C#](Assets/Turbo_Dash/Code/Research/Editor/RuleBasedParityCorpus.cs), [porównanie Python](Training/turbodash/rulebased_parity.py), [zapisany raport FAIL](Training/final_test/rulebased_parity_verification.json) |

Testy oprogramowania nie są epizodami końcowego TEST. Raport historycznej weryfikacji Unity nie jest deklaracją, że wszystkie opisane scenariusze stanowią aktualnie dostępny zestaw `unittest`.

Przy już zainstalowanych zależnościach testy Pythonowe można uruchomić z katalogu głównego repozytorium:

```powershell
Push-Location Training
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
} finally {
    Pop-Location
}
```

Instrukcje przygotowania Pythona 3.11 i workera są w [dokumentacji PPO](docs/PPO_TRAINING_PIPELINE.md). [Setup-Venv.ps1](Training/Setup-Venv.ps1) tworzy środowisko, instaluje zależności i **aktualizuje `requirements-lock.txt`**; nie jest wymagany do samego przeglądania repozytorium. Skrypty treningu, walidacji i diagnostyki standalone uruchamiają procesy Unity i tworzą artefakty — przed wykonaniem należy sprawdzić ich parametry.

## Historia wersji bazowej

Audyt z 2026-09-10 obejmuje kod, konfigurację, referencje scen/prefabów i porównanie z dostarczoną pracą inżynierską. Sam audyt był analizą statyczną. Dnia 2026-09-13 wykonano w Unity 2022.3.4f1 osobne testy Play Mode: bazowy i końcowy przepływ normalnej gry, pełny Research Mode oraz jego publiczny launcher przeszły bez błędów. Zakres i ograniczenia opisuje [raport weryfikacji](docs/BASELINE_VERIFICATION.md), a historyczne problemy — [audyt](docs/PROJECT_AUDIT.md).

## Unity i wymagania

- **Unity 2022.3.4f1**, rewizja `35713cd46cd7`, zgodnie z [ProjectVersion.txt](ProjectSettings/ProjectVersion.txt). Ta sama wersja występuje w pracy inżynierskiej, s. 34.
- Unity Hub do dodania projektu i odpowiedni edytor; edytor C# z obsługą Unity, np. używany pierwotnie Visual Studio 2022.
- Dostęp do rejestru pakietów Unity podczas pierwszego odtworzenia zależności. Źródłami wersji są `Packages/manifest.json` i `Packages/packages-lock.json`.
- Dla testu telefonu: Android i żyroskop dla trybu `Gyroscope`. Do budowania potrzebny jest moduł Android Build Support wraz z SDK/NDK/OpenJDK odpowiednimi dla tej wersji Unity.
- Zapisana konfiguracja Android: min SDK **26**, target SDK **33**, architektury **ARMv7 + ARM64**, backend **Mono**. Są to zastane ustawienia wymagające weryfikacji builda, a nie deklaracja gotowości do publikacji.
- Projekt korzysta z **Built-in Render Pipeline**, Post Processing **3.2.2**, TextMesh Pro **3.0.6**, uGUI **1.0.0** i starego `UnityEngine.Input` (`activeInputHandler: 0`). Nie przełączaj render pipeline ani systemu wejścia podczas odtwarzania wersji bazowej.

## Jak uruchomić

1. Dodaj w Unity Hub katalog zawierający `Assets/`, `Packages/` i `ProjectSettings/`. Wybierz **2022.3.4f1**.
2. Pozwól Unity zaimportować zasoby i odtworzyć pakiety. Najpierw sprawdź Console i Package Manager. Szczególną uwagę zwróć na nierozwiązane zależności `HeathenEngineering.UX.asmdef` oraz komponenty `Managers`/`Systems` opisane w audycie.
3. Otwórz **`Assets/Turbo_Dash/Design/Scenes/Menu.unity`**. To scena startowa builda. Bezpośrednie uruchomienie `DeafultLevel` pomija utworzenie `SaveAndLoadManager` z menu.
4. Wejdź w Play Mode. Do testów na komputerze wybierz **TouchControl** przyciskami zmiany trybu, rozpocznij grę i zatwierdź ekran instrukcji. Steruj strzałkami lewo/prawo. Samo kliknięcie lewej/prawej połowy okna myszą nie jest zaimplementowanym odpowiednikiem dotyku.
5. Na telefonie sprawdź osobno dotyk oraz `Gyroscope`; przycisk startu i przycisk kalibracji zapamiętują orientację odniesienia. Nie wybieraj `Multiplayer` do testowania podstawowej rozgrywki — obecna implementacja nie obsługuje sterowania ani sieci dla tego indeksu.
6. Sprawdź pauzę, kontynuację, restart i powrót do menu. Zakres wykonanej regresji opisuje [weryfikacja wersji bazowej](docs/BASELINE_VERIFICATION.md); nie zastępuje ona testów na docelowym telefonie.

W edytorze istnieją skróty diagnostyczne: `Escape`/`Space` — pauza; `Q`/`W` — modyfikacja wyniku; `T/B/S/H/G/P/L/O` — turbo, boost, tarcza, życie, moneta, diament, poziom i 1000 żyć. Zmieniają przebieg gry; zbieranie walut zapisuje też `PlayerPrefs`.

Aktywna kolejność Build Settings: **0 Menu → 1 DeafultLevel → 2 Shop → 3 Customization**. Strzałki w tej liście oznaczają kolejność indeksów, nie obowiązkową kolejność odwiedzania. Zachowano oryginalną pisownię `DeafultLevel`. Wyłączony wpis `SampleScene` wskazuje na nieistniejący plik.

## Struktura i systemy

| Katalog | Zawartość |
| --- | --- |
| [Assets/Turbo_Dash/Code/](Assets/Turbo_Dash/Code/) | Kod gry: stan, sterowanie, generowanie tunelu, kolizje, kamera, UI, audio, zapis i efekty |
| [Assets/Turbo_Dash/Code/Research/](Assets/Turbo_Dash/Code/Research/) | Research Mode, obserwacje, reward, kontrolery, metryki, bridge i narzędzia edytorowe |
| [Training/](Training/) | Kod Pythonowy, konfiguracje, skrypty eksperymentów, testy oraz wyniki FINAL TEST |
| `Assets/Turbo_Dash/Design/` | 4 sceny gry, prefaby, dane ScriptableObject |
| `Assets/Turbo_Dash/Art/` | Animacje, materiały, modele, dźwięki, tekstury i grafiki UI |
| `Assets/Turbo_Dash/Addons/` | Importowane paczki, przykłady UI, klejnoty i stare Image Effects |
| Pozostałe katalogi `Assets/` | TextMesh Pro, Sci-Fi UI, ikony Heathen, Adaptive Performance, ustawienia powiadomień i Android |
| `Packages/` | Manifest i blokada wersji zależności |
| `ProjectSettings/` | Wersja edytora, sceny builda, tagi, fizyka, input, grafika i ustawienia platform |
| `docs/` | Dokumentacja bieżącego stanu, inwentarz oraz audyt |

Kluczowe klasy to `GameManager`, `SaveAndLoadManager`, `EnvironmentMovement`, `EnvironmentManager`, `TubeManager`, `TubeMovement`, `PlayerCollision`, `TimeManager`, `UIGame` i `LevelLoader`. Dane konfiguracji reprezentują `GameMode`, `Theme`, `Wall`, `Obstacle` i `Gem`.

Wykryte systemy obejmują poziomy trudności i portale, trzy życia, tarczę, nieśmiertelność, ładowanie turbo, waluty, lokalne rekordy, kamerę z efektami oraz muzykę/SFX. `Shop` i `Customization` są szkicami ekranów. Nie znaleziono działającego multiplayera, AI przeciwników, reklam, zakupów ani rankingów online.

Dokumentacja: [architektura](docs/ARCHITECTURE.md), [systemy gry](docs/GAME_SYSTEMS.md), [audyt i roadmap](docs/PROJECT_AUDIT.md), [pełny inwentarz](docs/REPOSITORY_INVENTORY.md), [weryfikacja runtime](docs/BASELINE_VERIFICATION.md), [środowisko badawcze](docs/ML_RESEARCH_ENVIRONMENT.md), [Research Protocol v1](docs/RESEARCH_PROTOCOL_V1.md), [pilot RuleBasedV1](docs/RULE_BASED_PILOT.md), [pipeline PPO](docs/PPO_TRAINING_PIPELINE.md), [smoke PPO 100k](docs/PPO_SMOKE_TEST.md), [zasady pracy agentów](AGENTS.md).
