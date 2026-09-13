# Turbo Dash

Turbo Dash to mobilna gra 3D typu endless runner: gracz unika przeszkód wewnątrz tunelu i na jego zewnętrznej powierzchni, zbiera klejnoty oraz aktywuje turbo. Wrażenie biegu powstaje przez przesuwanie tub w stronę gracza i obracanie otoczenia. Zaimplementowano sterowanie żyroskopem oraz dotykiem/strzałkami.

Projekt powstał na potrzeby pracy inżynierskiej Pawła Frąckowiaka **„Projekt i implementacja gry mobilnej typu endless runner z wykorzystaniem sterowania żyroskopowego”** (2024). Obecnie jest przywracany do rozwoju jako podstawa magisterki **„Opracowanie i analiza algorytmów uczenia maszynowego do sterowania agentem w grze typu endless runner.”** Projekt ma wersjonowane środowisko badawcze, baseline RuleBasedV1 oraz wieloprocesowy pipeline PPO discrete oparty na standalone workerach Unity i Stable-Baselines3.

## Stan projektu

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
6. Sprawdź pauzę, kontynuację, restart i powrót do menu. Znane problemy tych ścieżek oznaczają, że instrukcja nie jest gwarancją bezbłędnego uruchomienia. [Plan weryfikacji](docs/PROJECT_AUDIT.md#plan-weryfikacji-po-audycie) określa następny etap.

W edytorze istnieją skróty diagnostyczne: `Escape`/`Space` — pauza; `Q`/`W` — modyfikacja wyniku; `T/B/S/H/G/P/L/O` — turbo, boost, tarcza, życie, moneta, diament, poziom i 1000 żyć. Zmieniają przebieg gry; zbieranie walut zapisuje też `PlayerPrefs`.

Aktywna kolejność Build Settings: **0 Menu → 1 DeafultLevel → 2 Shop → 3 Customization**. Strzałki w tej liście oznaczają kolejność indeksów, nie obowiązkową kolejność odwiedzania. Zachowano oryginalną pisownię `DeafultLevel`. Wyłączony wpis `SampleScene` wskazuje na nieistniejący plik.

## Struktura i systemy

| Katalog | Zawartość |
| --- | --- |
| `Assets/Turbo_Dash/Code/` | 30 skryptów: stan gry, sterowanie, generowanie tunelu, kolizje, kamera, UI, audio, zapis i efekty |
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
