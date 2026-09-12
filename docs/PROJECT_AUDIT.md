# Audyt projektu Turbo Dash

Data: **2026-09-10**. Baza: commit `5eb7e19`, Unity **2022.3.4f1**. Zakres: pliki w Assets, manifest/lockfile Packages, ProjectSettings, powiązania GUID i UnityEvent, kod C# oraz dostarczona praca inżynierska. Projekt ma 97 skryptów C#, 17 scen i 52 prefaby. [Inwentarz](REPOSITORY_INVENTORY.md) obejmuje każdy skrypt i scenę.

## Metoda i ograniczenia

Przeprowadzono analizę statyczną. Sprawdzono deklaracje i użycia klas, metody, konfiguracje ScriptableObject, hierarchie managerów, skrypty i zdarzenia scen, zależności prefabów oraz mapowanie GUID z `.meta`. Przy rozwiązywaniu zależności pakietowych pomocniczo odczytano istniejący `Library/PackageCache`, pomijając katalogi `Samples~` i inne katalogi zakończone `~`, które nie są aktywnymi importami. Brak referencji tekstowej jest przesłanką, nie pełnym dowodem nieużywania.

Nie uruchomiono Unity, importu, kompilacji, testów Play/Edit Mode ani builda. Zapobiega to zapisom poza zakresem dokumentacji zleconym w tym etapie. Nie potwierdzono działania gry na tym komputerze ani kompletności narzędzi Android. Historyczne logi workerów importu nie zastępują wyniku bieżącej kompilacji; komunikaty o `-noUpm` w procesach pomocniczych nie zostały potraktowane jako dowód awarii Package Managera.

**Potwierdzone statycznie** oznacza konkretną konstrukcję kodu/danych. **Ryzyko / do weryfikacji** oznacza, że skutek zależy od kolejności zdarzeń, importu lub runtime. **Usterka utajona** dotyczy gałęzi niewłączonej przy obecnej konfiguracji.

| Priorytet | Znaczenie |
| --- | --- |
| CRITICAL | Potwierdzona blokada podstawowego uruchomienia/kompilacji lub katastrofalna utrata danych |
| HIGH | Poważny błąd podstawowego przepływu lub wiarygodna potencjalna blokada uruchomienia |
| MEDIUM | Ryzyko rozwoju, jakości, konfiguracji lub wydajności; ograniczona/warunkowa usterka |
| LOW | Porządek, czytelność, ślady prototypów i nieaktywne problemy o małym wpływie |

Nie przypisano CRITICAL bez potwierdzenia kompilacją lub uruchomieniem. Poniższe propozycje rozwiązań **nie zostały wdrożone**.

## Najważniejsze ustalenia

### A01 — HIGH — Nierozwiązane referencje assembly Heathen UX

**Lokalizacja:** `Assets/_Heathen Engineering/Assets/UX/HeathenEngineering.UX.asmdef:4`.

**Opis:** referencje `58d42c70423577947911995925414405` i `75469ad4d38634e559750d17036d5f7c` nie mają odpowiedników w Assets ani aktywnych metadanych zainstalowanych pakietów. Trzeci GUID wskazuje poprawnie na Unity.TextMeshPro. Pod tym asmdef są zasoby ikon, bez skryptów C#.

**Wpływ:** ryzyko błędów importu/rozwiązywania assembly, potencjalnie blokujących przygotowanie kompilacji. Pusty zakres asmdef wymaga sprawdzenia zachowania edytora; sam skan nie potwierdza blokady builda.

**Sugerowane rozwiązanie:** podczas Restore sprawdzić Console i Inspector asmdef na czystym imporcie właściwej wersji. Ustalić pochodzenie brakujących zależności i czy assembly jest potrzebne. Dopiero na podstawie wyniku przywrócić wymagane zależności lub świadomie uporządkować pozostałość po paczce.

### A02 — HIGH — Inicjalizacja zależy od sceny i hierarchii singletonów

**Lokalizacja:** `Code/Scripts/SaveAndLoadManager.cs`, `Code/Managers/GameManager.cs:21`, `Code/Managers/TimeManager.cs:36`, `Code/Systems/AudioSystem.cs:15`, `Design/Scenes/Menu.unity`, `Design/Scenes/DeafultLevel.unity` (ścieżki od `Assets/Turbo_Dash/`).

**Opis:** SaveAndLoadManager występuje wyłącznie w Menu. Gameplay bez przejścia przez Menu dereferencjonuje brakujący singleton m.in. w EnvironmentMovement, UIGame i GameManager. Managery/audio/zapis są dziećmi kontenerów i próbują wywoływać DontDestroyOnLoad na sobie. Dodatkowo `Code/Managers/Managers.cs:5` deklaruje `Systems`, a `Code/Systems/Systems.cs:5` deklaruje `Managers`; oba skrypty są przypięte do kontenerów.

**Wpływ:** bezpośredni start gameplayu nie zapewnia wymaganych usług. Trwałość usług zależy od poprawnego importu i działania kontenerów. Zamiana nazw nie jest duplikatem klasy C#; stanowi ryzyko mapowania skryptów i istotną pułapkę utrzymaniową. Nie potwierdzono runtime błędu „Missing Script”.

**Sugerowane rozwiązanie:** najpierw odtworzyć start od Menu, skontrolować klasy w Inspectorze i hierarchię DontDestroyOnLoad. Potem uzgodnić jedno miejsce inicjalizacji i jednoznacznego właściciela czasu życia usług. Uporządkowanie nazw musi zachować GUID-y i przypięcia. Dokumentacja Unity 2022.3 opisuje wymaganie zgodności nazwy klasy/pliku oraz ogranicza DontDestroyOnLoad do korzeni i ich komponentów. [Skrypty](https://docs.unity3d.com/2022.3/Documentation/Manual/CreatingAndUsingScripts.html), [DontDestroyOnLoad](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Object.DontDestroyOnLoad.html).

### A03 — HIGH — Restart i ponowne wejście z menu używają starego stanu sceny

**Lokalizacja:** `Code/AnimationScripts/LevelLoader.cs:18`, `Code/Managers/GameManager.cs` (`StartGame`, `RestartGame`, `Update`), `Code/Managers/AnimationManager.cs:33`, `Code/Managers/TimeManager.cs`.

**Opis:** PlayButtonClicked zaczyna opóźnione ładowanie, następnie przy istniejącym GameManager wywołuje RestartGame. StartGame przed reloadem wywołuje Presets, a ono bez sprawdzenia null wyszukuje CameraFollow. Po powrocie do Menu takiego obiektu nie ma. Trwałe GameManager/TimeManager nie wykonują ponownie Start po każdej zmianie sceny. StartGame ustawia flagę gamePaused, ale nie timeScale, nie resetuje isNewHighScore/showLevelUP. Powrót z pauzy ustawia timeScale=1 bez ujednolicenia stanu i może pozwolić GameManager naliczać wynik w menu. Skybox również jest przypisywany przed reloadem zamiast po nim.

**Wpływ:** wyjątek przy ponownym Play z menu, sprzeczność ekranu startowego ze światem poruszającym się w tle, zależność retry od poprzedniej pauzy/spowolnienia, przenikanie stanu między podejściami. Skutek zależy od poprawnego przetrwania singletonów z A02; kod ryzykownej ścieżki jest potwierdzony.

**Sugerowane rozwiązanie:** jeden kontrolowany przepływ restartu: ustalenie stanu sesji, jedno ładowanie, ponowne związanie obiektów po załadowaniu, inicjalizacja prezentacji i spójny stan czasu. Zweryfikować oddzielnie retry z pauzy, retry po śmierci i Menu→Play po wcześniejszej grze.

### A04 — HIGH — Nowe rekordy nie zapisują się do PlayerPrefs

**Lokalizacja:** `Code/Scripts/SaveAndLoadManager.cs:42` (`SaveHighScore`) i `:63` (`SaveHighSpeed`), `Code/UIScripts/UIMenu.cs:14`.

**Opis:** kod najpierw podmienia HighScore/HighSpeed w assetcie, a potem ponownie sprawdza `newValue > HighScore/HighSpeed` przed SetInt/SetFloat. Dla nowego rekordu wartości są już równe. Dla wartości niższej warunek również pozostaje fałszywy. Ponadto nie znaleziono wywołania LoadHighSpeeds. Błąd warunku jest potwierdzony statycznie; brak wywołań to wynik wyszukiwania kodu oraz zdarzeń serializowanych.

**Wpływ:** nowy rekord jest widoczny w pamięci sesji, lecz nie trafia do trwałego klucza. Powrót do menu z LoadHighScores może odtworzyć starszą wartość. Również rekord prędkości nie ma kompletnej ścieżki odczytu.

**Sugerowane rozwiązanie:** sprawdzić poprawę względem starej wartości raz, a następnie zapisać obie reprezentacje; uzgodnić punkt odczytu i zapisu. Test powinien obejmować rekord wyższy/niższy, przejście do menu i nowy proces aplikacji, z zachowaniem dotychczasowych danych użytkownika.

### A05 — HIGH — Wiele równoległych odliczań kontynuacji

**Lokalizacja:** `Code/UIScripts/UIGame.cs:113`, `:247`, `:289`; `Code/AnimationScripts/LevelLoader.cs:64`.

**Opis:** Update uruchamia WaitAndExecute co klatkę końca gry. Każda coroutine zeruje ten sam elapsedTime i następnie go powiększa. Flaga chanceToContinue zmienia się dopiero po ShowEndButtons. ContinueGameButton nie kończy odliczeń ani bezpośrednio nie zużywa szansy. Ustawiony waitTime=2 używa czasu skalowanego; przy gameOver=0.4 pojedynczy poprawny timer trwałby około 5 sekund rzeczywistych, co odpowiada opisowi z PDF, ale obecne coroutine zaburzają ten wynik.

**Wpływ:** nieprzewidywalny countdown zależny od liczby klatek, powielone zadania i zmiany UI po wznowieniu gry; reguła jednej kontynuacji nie jest realizowana jednoznacznie.

**Sugerowane rozwiązanie:** rozpoczynać jedno odliczanie przy wejściu w stan GameOver, jawnie je anulować przy Continue/Retry/wyjściu i zużyć szansę przy kontynuacji. Wybrać zegar zgodny z zamierzonym czasem realnym i sprawdzić zachowanie przy różnych FPS.

### A06 — HIGH — Menu pozwala wybrać niezaimplementowany multiplayer

**Lokalizacja:** `Code/UIScripts/UIMenu.cs:26`, `Code/Scripts/EnvironmentMovement.cs:28`, `Design/ScriptableObjects/GameModes/Multiplayer.asset`.

**Opis:** menu cyklicznie przechodzi przez wszystkie trzy indeksy i ignoruje `Unlocked`. Multiplayer ma unlocked=0, a kod sterowania obsługuje tylko indeksy 0 i 1. Brak pakietu/kodu sieciowego.

**Wpływ:** dostępny z menu wybór prowadzi do rozgrywki bez obsługi sterowania.

**Sugerowane rozwiązanie:** po uzgodnieniu zachowania UI respektować dostępność trybów i jasno oznaczyć element przygotowawczy; wdrożenie multiplayera nie jest częścią przywracania podstawowej gry.

## Pozostałe problemy i dług techniczny

### A07 — MEDIUM — Konflikt dwóch kontrolerów globalnego shadera

**Lokalizacja:** `Code/Shaders/BendControllerRadial.cs:48`, `Design/Scenes/DeafultLevel.unity` (Main Camera oraz Environment/Bend Shader Controller).

**Opis:** dwa aktywne komponenty zapisują te same globalne parametry. Mają różne curveOrigin/referenceDirection, zScale=0.6/1 i flatMargin=0/30. Oba wykonują się także w Edit Mode.

**Wpływ:** wynik renderowania zależy od ostatniego zapisującego komponentu; wyłączenie jednego zeruje część stanu drugiego. Colliderów nie wygina shader, więc geometria renderowana i fizyczna mogą się różnić.

**Sugerowane rozwiązanie:** po porównaniu obrazu z działającą wersją ustalić jednego właściciela parametrów lub jawny zakres materiałów. Nie usuwać komponentu bez sprawdzenia wyglądu i referencji.

### A08 — MEDIUM — Niekompletne referencje assetów i przykładów

**Lokalizacja:** `Design/Scenes/DeafultLevel.unity:6063`, `Design/Prefabs/Obstacles/Cube.prefab:141`, `Design/Prefabs/Structures/Tube.prefab:2230`, `Assets/Readme.asset`, dema w Addons/Sci-Fi UI/Heathen.

**Opis:** nierozwiązane kontrolery Animator: Main Camera (`330f37698237509488b62ab578d37545`) i Cube (`1ba1a912283f06642a3911d6c41b5233`). Tube ma dwa brakujące GUID-y tekstur w polach tubeInsideTexture/tubeOutsideTexture, których kod nie używa. Kontroler na osobnym Camera Follow rozwiązuje się poprawnie. W demach są także nierozwiązane stare referencje skryptów/UI, a w Readme.asset brak skryptu/zasobu. Łącznie skan badanych tekstowych typów znalazł 18 nierozwiązanych różnych GUID-ów, w tym A01.

**Wpływ:** brakujące animacje lub warnings; możliwe Missing Script w demach. Nie dowodzi to braku właściwej animacji shake ani awarii materiałów tunelu, które pochodzą z Theme.

**Sugerowane rozwiązanie:** sprawdzić każdą referencję w Inspectorze, odzyskać potrzebne zasoby z właściwymi GUID-ami. Pola nieużywane i dema porządkować dopiero po odrębnym ustaleniu zakresu.

### A09 — MEDIUM — UI i renderer są częścią logiki gameplayu

**Lokalizacja:** `Code/UIScripts/UIGame.cs` (331 linii), `Code/Managers/GameManager.cs` (511 linii), `Code/AnimationScripts/ImmortalityEffect.cs:18`.

**Opis:** GameManager łączy stan, konfigurację, generację, ekonomię, efekty i przejścia. UIGame łączy prezentację z zegarem kontynuacji, pomiarem prędkości i zużyciem turbo. Komponent renderera wyłącza logiczną nieśmiertelność.

**Wpływ:** mocne sprzężenia, trudne testowanie, ryzyko zmiany zasad przy wyłączeniu UI/grafiki. Utrudnia to przyszłe treningi bez renderowania i wiele równoległych środowisk.

**Sugerowane rozwiązanie:** po utrwaleniu zachowania wydzielać małe odpowiedzialności oraz zdarzenia stanu; jako pierwsze rozważyć stan sesji, bonusy i pomiar postępu. Nie zaczynać od dużej refaktoryzacji całego GameManager.

### A10 — MEDIUM — Niespójny cykl turbo i nieśmiertelności

**Lokalizacja:** `Code/UIScripts/UIGame.cs:196`, `:272`, `:323`; `Code/Managers/GameManager.cs` (`TurboEffect`, `TurnOffTurboEffect`); `Code/AnimationScripts/ImmortalityEffect.cs`.

**Opis:** turbo nadal pasywnie ładuje slider w czasie jego opróżniania. ResetTurboParameters może uruchamiać kolejne coroutine. Efekty widoczności są przełączane, a nie ustawiane według stanu. Ponowne przyznanie nieśmiertelności nie odnawia timera już aktywnego komponentu.

**Wpływ:** zmienny czas trwania, rozjazd efektów z flagami, niespodziewane skrócenie/nałożenie bonusu.

**Sugerowane rozwiązanie:** najpierw ustalić zamierzone reguły ładowania podczas turbo i ponownego przyznawania ochrony; potem jeden właściciel czasu/zasobu i jawne ustawianie efektów. Zachowanie porównać z wersją bazową.

### A11 — MEDIUM — Wynik i prędkość HUD nie są pomiarami dystansu

**Lokalizacja:** `Code/Managers/GameManager.cs` (`Update`, `FixScore`, `TurboEffect`), `Code/UIScripts/UIGame.cs:169`, `Code/Scripts/TubeMovement.cs:11`.

**Opis:** wynik nalicza się z czasu i mnożników, ma skoki przy portalach, a HUD liczy jego pochodną jako m/s. Turbo podwaja przyrost wyniku, lecz nie zmienia bezpośrednio prędkości tub.

**Wpływ:** rekord prędkości może odzwierciedlać korektę wyniku zamiast ruchu. W przyszłej magisterce błędne założenie o jednostkach prowadziłoby do niewłaściwych metryk i funkcji nagrody.

**Sugerowane rozwiązanie:** opisać i zachować istniejącą punktację jako osobny pomiar; później zdefiniować fizyczny dystans, czas przeżycia, liczbę kolizji i zasady oceny agenta. Zmiana istniejącej punktacji wymaga osobnej decyzji.

### A12 — MEDIUM — Błąd filtra trudności Outside ukryty przez dane

**Lokalizacja:** `Code/Managers/GameManager.cs` (`UpdateObjectListToSpawnByLevel`), `Design/ScriptableObjects/{Walls,Obstacles,Gems}/`.

**Opis:** filtr zawsze porównuje z gameInsideDifficulty. Aktualnie wszystkie 14 danych spawnów ma difficulty=Any, więc dobór trudności nie filtruje żadnego z nich; wzrost trudności działa przez prędkość, prawdopodobieństwo i tekstury.

**Wpływ:** przyszłe obiekty przypisane do konkretnej trudności Outside mogą znikać z list albo pojawiać się na złym etapie. Obecne dane nie realizują selekcji konkretnych przeszkód według Easy/Medium/Hard.

**Sugerowane rozwiązanie:** zastosować trudność właściwą dla lokacji i zweryfikować macierz Inside/Outside × Easy/Medium/Hard/Any; balans aktualnych assetów potraktować jako osobną zmianę gameplayu.

### A13 — MEDIUM — Losowość i granice losowania

**Lokalizacja:** `Code/Scripts/RandomArrangement.cs:12`, `Code/Scripts/TubeManager.cs:45`, `Code/Managers/GameManager.cs` (`SpawnObject`), `Code/Scripts/EnvironmentManager.cs`.

**Opis:** int Random.Range ma górną granicę wyłączną: rotacje pomijają 315°, szansa klejnotu wynosi 1/2 zamiast komentarzowych 1/3, a procent przeszkód liczony jest na 99 wartościach. Nie ma własnego seeda, zapisu stanu RNG ani walidacji przejezdności. Generator zeruje timer zamiast przenosić nadmiar czasu; tempo spawnów zmienia się podczas biegu.

**Wpływ:** balans różny od komentarzy, niepowtarzalne próby i potencjalne szczeliny/nakładanie segmentów wymagające obserwacji. Nie stwierdzono statycznie, że generowany układ musi być niemożliwy do przejścia.

**Sugerowane rozwiązanie:** najpierw zapisać rzeczywiste reguły jako bazę. Następnie osobno uzgodnić poprawki balansu, sterowanie ziarnem, pomiar położenia segmentów i walidację układów.

### A14 — MEDIUM — Ryzyka inputu i cache singletona audio

**Lokalizacja:** `Code/Scripts/EnvironmentMovement.cs`, `Code/Managers/GameManager.cs:103` i `ResetGyroscopeRotation`.

**Opis:** brak sprawdzenia SystemInfo.supportsGyroscope, brak filtrowania dotyku nad UI, brak implementacji kierunku z myszy i przeliczenia szerokości po zmianie rozmiaru. `audioSystem = AudioSystem.Instance` w inicjalizatorze pola może zapamiętać null; w GameManager nie ma późniejszego przypisania.

**Wpływ:** mylące testy w edytorze, obrót przy klikaniu HUD, możliwe wyjątki bonusów zależne od inicjalizacji. Start od Menu zmniejsza ryzyko audio, lecz nie stanowi jawnej gwarancji kolejności konstrukcji i inicjalizacji pól.

**Sugerowane rozwiązanie:** jawnie wiązać audio po inicjalizacji usług; przetestować input na sprzęcie, ustalić obsługę braku sensora oraz interakcji z UI. Oddzielenie źródła wejścia od obrotu będzie użyteczne w późniejszym etapie ML.

### A15 — MEDIUM — Ruch przeszkód może kumulować pozycję

**Lokalizacja:** `Code/AnimationScripts/ObstacleMovement.cs:54`, `:66`.

**Opis:** nowa pozycja to startPosition plus wektor zawierający bieżące współrzędne pozostałych osi. Jeśli te składowe startPosition są niezerowe, są dodawane ponownie w każdym kroku. To usterka utajona; w sprawdzonym SideToSideCube Y/Z mają wartość 0.

**Wpływ:** nowe lub przesunięte warianty prefabów mogą dryfować zamiast oscylować.

**Sugerowane rozwiązanie:** liczyć offset oscylacji względem jednej pozycji bazowej. Sprawdzić wariant z niezerowym offsetem i jednoczesnym ruchem w obu osiach.

### A16 — MEDIUM — Koszty pracy co klatkę i generowania obiektów

**Lokalizacja:** `Code/Managers/AnimationManager.cs:49`, `Code/UIScripts/LoadLootPanel.cs:34`, `Code/UIScripts/UIGame.cs:96`, `Code/Scripts/EnvironmentManager.cs`, `Code/Scripts/TubeMovement.cs`, `Code/Managers/GameManager.cs` (`AssignMaterialByTag`).

**Opis:** wyszukiwanie obiektu kamery po tagu co klatkę, odczyty PlayerPrefs i formatowanie HUD co klatkę, częste Instantiate/Destroy, logowanie każdego segmentu/kolizji oraz korzystanie z Renderer.material. Nie zmierzono kosztów ani wycieku pamięci.

**Wpływ:** potencjalne skoki CPU/GC i większe zużycie zasobów na urządzeniu mobilnym; nadmiar pracy podczas przyszłych treningów.

**Sugerowane rozwiązanie:** profilować dłuższy bieg na docelowym sprzęcie. Potem ograniczyć zbędne odświeżanie, ponownie wiązać cache przy zmianie sceny, zweryfikować czas życia materiałów i rozważyć pooling tylko tam, gdzie pomiar uzasadni koszt zmiany.

### A17 — MEDIUM — Historyczna warstwa renderowania i aktualizacja Unity

**Lokalizacja:** `Code/Shaders/BendyDiffuseRadial.shader`, `Addons/#NVJOB Alpha Flashing UI/Example Scenes/Standard Assets/`, `Packages/manifest.json`, `ProjectSettings/GraphicsSettings.asset`.

**Opis:** gra używa surface shadera Built-in i Post Processing, a dema zawierają stare efekty OnRenderImage, DepthOfFieldDeprecated i BloomAndFlares. ImageEffects.cs ma metody oznaczone Obsolete. Wystąpienie Random.seed znajduje się w **zakomentowanej** metodzie; podobnie część starych kontroli SystemInfo jest zakomentowana. Nie uznano ich za aktywne błędy kompilacji. Legacy Input działa w konfiguracji 2022.3; sama jego obecność nie oznacza błędu API.

**Wpływ:** duży zakres regresji przy jednoczesnej zmianie Unity, pakietów, inputu i render pipeline. OnRenderImage nie jest obsługiwane przez SRP. [Unity 2022.3: OnRenderImage](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/MonoBehaviour.OnRenderImage.html).

**Sugerowane rozwiązanie:** przywrócić wersję zapisaną w repozytorium, zebrać rzeczywiste warnings i zachować punkt porównawczy. Aktualizować osobno i małymi krokami; migrować rzeczywiście używane rozwiązania po sprawdzeniu zależności, bez automatycznego usuwania paczek demonstracyjnych.

### A18 — MEDIUM — Konfiguracja Android i pakiety nie zostały odtworzone buildem

**Lokalizacja:** `ProjectSettings/ProjectSettings.asset:165`, `:254`, `:850`; `Packages/manifest.json`, `Packages/packages-lock.json`, `Assets/Plugins/Android/mainTemplate.gradle.DISABLED`.

**Opis:** target SDK=33, min=26, ARMv7+ARM64 i Mono są historycznym zestawem ustawień. Moduły builda, toolchain i poprawność kombinacji backend/architektury nie zostały potwierdzone. W manifeście jest wiele narzędzi i funkcji mobile, dla których nie znaleziono własnych integracji gameplayowych. Nie znaleziono dowodu błędu rozwiązywania pakietów w samym lockfile.

**Wpływ:** możliwa blokada builda mimo działającego Play Mode; większy zakres zależności do odtworzenia. Gotowość do publikacji w sklepie nie była przedmiotem audytu.

**Sugerowane rozwiązanie:** wykonać build kontrolny na oryginalnej wersji i sprawdzić wymagane moduły/architektury/backend na podstawie komunikatów Unity. Nie aktualizować SDK ani nie usuwać pakietów w ciemno.

### A19 — MEDIUM — Dane konfiguracyjne są zarazem stanem sesji

**Lokalizacja:** `Code/ScriptableObjects/GameMode.cs`, `Code/Scripts/SaveAndLoadManager.cs`, `Design/ScriptableObjects/Theme/CustomTheme.asset`, `Design/ScriptableObjects/Walls/StaticWall1.asset`, `StaticWall2.asset`.

**Opis:** GameMode zawiera mutowane rekordy i niewykorzystywane pola statystyk, a zapis jest związany z pozycją w tablicy 0–2. CustomTheme ma stare pola tubeInside/tubeOutside, puste materiały i nie jest podpięty. StaticWall1/2 mają pole `name`, podczas gdy klasa oczekuje `wallName`; pozostałe nazwy przeszkód/ścian są często puste. Funkcje GetName nie sterują obecnym spawnem.

**Wpływ:** pułapki przy rozszerzaniu trybów/motywów i rozbieżności między assetami a kodem; odczyt/edycja ScriptableObject w Play Mode wymaga uwagi, nie zastępuje trwałego zapisu w buildzie.

**Sugerowane rozwiązanie:** oddzielić konfigurację od wyników dopiero po naprawieniu zapisu; sprawdzać spójność indeksów i danych oraz migrację pól. Nie podłączać niedokończonego motywu bez kompletnych materiałów.

### A20 — MEDIUM — Brak automatycznej weryfikacji oraz granicy epizodu

**Lokalizacja:** repozytorium, `Code/Managers/GameManager.cs`, `Code/UIScripts/UIGame.cs`, `Code/Scripts/EnvironmentManager.cs`.

**Opis:** Test Framework jest pakietem, ale w repozytorium nie ma własnych testów ani CI. Restart ładuje scenę, globalne singletony i PlayerPrefs łączą kolejne podejścia, Random nie ma kontrolowanego seeda, a stan bonusów częściowo żyje w UI.

**Wpływ:** trudne wykrywanie regresji; obecna wersja nie jest gotowym środowiskiem do powtarzalnych eksperymentów ML ani wielu instancji środowiska w jednej scenie.

**Sugerowane rozwiązanie:** po Restore wprowadzać testy konkretnych błędów (rekord, pojedyncza kontynuacja, restart, lokacja), następnie uzgodnić reset epizodu, losowość i metryki. Nie instalować narzędzi ML na etapie audytu.

### A21 — LOW — Potencjalnie nieużywany kod, duplikacja i nazwy

**Lokalizacja:** `Code/Scripts/PlayerMovement.cs`; `Code/UIScripts/UIGame.cs` (baseSpeed/maxSpeed/turboSpeed); `Code/Scripts/TubeManager.cs` (tubeInsideTexture/tubeOutsideTexture); `Code/Managers/GameManager.cs` (spaceLevel/restartDelay); `Code/Systems/AudioSystem.cs` (ToggleSFX/ToggleMusic); `Code/AnimationScripts/LevelLoader.cs` (SkillTree/Leaderboard); `Code/ScriptableObjects/GameMode.cs` (statystyki); `Addons/Gems Ultimate Pack/Scripts/AnimationScript.cs` i `Code/AnimationScripts/GemAnimationScript.cs`.

**Opis:** PlayerMovement nie ma przypięcia ani znalezionego tworzenia komponentu; niektóre pola/metody mają tylko deklaracje lub lokalne przypisania. GemAnimationScript powiela znaczną część AnimationScript. Powtarza się kod singletonów. Są literówki `Interfaceses`, `parrent`, `DeafultLevel`; część komentarzy C# nie jest poprawnym UTF-8.

**Wpływ:** mylący obraz architektury i wyższy koszt utrzymania, ale brak podstaw do automatycznego usuwania. Prototyp PlayerMovement wykonuje AddForce w Update, lecz nie jest aktywnym mechanizmem ruchu gry.

**Sugerowane rozwiązanie:** potwierdzić referencje w Inspectorze i UnityEvent, oznaczyć pochodzenie prototypów; później ograniczać duplikację małymi zmianami. Nazwy związane z serializacją i kodowanie poprawiać świadomie, zachowując GUID-y i polskie komentarze.

### A22 — LOW — Utajony błąd floating i granice sprzątania VFX

**Lokalizacja:** `Code/AnimationScripts/GemAnimationScript.cs:55`, odpowiednik `AnimationScript.cs`, `Code/AnimationScripts/DestroyParticleSystem.cs:31`, `Design/Prefabs/VisualEffects/`.

**Opis:** floating używa Translate bez deltaTime, a drugi zwrot przypisuje `+floatSpeed` zamiast zmiany znaku. We wszystkich sprawdzonych prefabach klejnotów gry isFloating=0. VFX usuwa się po czasie emisji systemu, bez uwzględnienia pozostałego życia cząsteczek. Prefaby zbierania dziedziczą sprzątanie po Explosion, więc nie są automatycznie „efektami bez usuwania”.

**Wpływ:** błąd po włączeniu opcji floating; możliwe ucinanie efektów wymagające obserwacji.

**Sugerowane rozwiązanie:** naprawić floating dopiero z testem włączonej opcji; porównać czas widoczności efektów i ewentualnie sprzątać po zakończeniu cząsteczek.

### A23 — LOW — Niepełna mapa scen i martwe punkty nawigacji

**Lokalizacja:** `ProjectSettings/EditorBuildSettings.asset:9`, `Code/AnimationScripts/LevelLoader.cs:14`.

**Opis:** SampleScene nie istnieje, ale jej wpis jest wyłączony. Indeksy 4/5 nie mają scen; metoda SkillTree nie ma znalezionego przycisku. Shop/Customization są szkicami ekranów.

**Wpływ:** mylący obraz zakresu funkcji; przyszłe podłączenie SkillTree spowoduje próbę załadowania nieistniejącego indeksu. Wyłączony SampleScene sam w sobie nie blokuje normalnego startu builda.

**Sugerowane rozwiązanie:** uporządkować nawigację przy zleceniu rozwoju UI i zachować zgodność aktywnych indeksów. Nie opisywać planów z PDF jako obecnych funkcji.

## Wyniki pozytywne i rzeczy niepotwierdzone

- Wszystkie cztery aktywne ścieżki scen builda istnieją, a indeksy podstawowych przejść odpowiadają kolejności builda.
- W Assets nie znaleziono brakujących `.meta`, osieroconych `.meta` ani zduplikowanych GUID-ów. Pominięte kopie w Samples~ pakietów nie są konfliktem aktywnych assetów.
- GUID-y własnych skryptów przypiętych do czterech scen gry i prefabów rozwiązują się do istniejących plików; nie przesądza to o udanym imporcie klasy.
- DefaultTheme ma 4 materiały Inside i 3 Outside wymagane przez kod; przypisane tablice trybów mają indeksy 0,1,2. Puste gameThemeName korzysta z istniejącego fallbacku Default, więc nie jest samo w sobie brakiem motywu.
- Nie znaleziono śledzonych przez Git katalogów generowanych ani plików csproj/sln. `.gitignore` obejmuje główne katalogi Unity i IDE.
- Nie potwierdzono błędów kompilatora C#, awarii pakietów, wycieku pamięci ani wartości FPS. Nie uznano zakomentowanego API i pustych importów za dowód awarii.

## Plan weryfikacji po audycie

Poniższe czynności są planem kolejnego etapu, **nie wynikiem wykonanych testów**.

1. Odtworzyć import w Unity 2022.3.4f1, zanotować pełną Console, zależności asmdef, warnings o kontenerach i brakujące zasoby. Nie bazować na starym Library ani samym dotnet build wygenerowanego projektu.
2. Uruchomić Menu → TouchControl → gameplay → ekran instrukcji → start. Sprawdzić instancje usług i timeScale; osobno udokumentować oczekiwany brak inicjalizacji przy starcie DeafultLevel bez Menu.
3. Sprawdzić pauza/wznowienie, retry z pauzy i po śmierci, GameOver→Continue→ponowny GameOver, Menu→Play po poprzedniej grze; kontrolować jeden timer i brak starych referencji.
4. Zebrać bonusy, sprawdzić limit żyć, jednorazową tarczę, ochronę czasową, turbo, FOV, dźwięki i posprzątanie VFX. Przejechać co najmniej pełny cykl Inside→Outside→Inside i skontrolować ciągłość segmentów.
5. Zweryfikować rekordy i waluty po powrocie do menu oraz ponownym uruchomieniu aplikacji, bez kasowania istniejących PlayerPrefs użytkownika. Do automatyzacji używać izolowanych danych testowych.
6. Wykonać kontrolny build Android, test żyroskopu/dotyku na urządzeniu i pomiar Profilerem. Dopiero później uznać wersję bazową za przywróconą.

## Recommended Roadmap

### Phase 1 - Restore

- Odtworzyć oryginalne Unity i zależności; rozstrzygnąć A01/A02 na podstawie Console i hierarchii.
- Odzyskać potrzebne brakujące zasoby, naprawić inicjalizację i powtórne uruchomienie (A03), zapis (A04), kontynuację (A05) oraz dostępność trybów (A06).
- Zweryfikować podstawowy przepływ, build Android i wejście na urządzeniu. Zachować oznaczony punkt odniesienia z listą znanych ograniczeń oraz opisem zasad gry.

### Phase 2 - Stabilize

- Ujednolicić stan czasu i bonusów, rozstrzygnąć konflikt shaderów, dodać testy dla wykrytych usterek.
- Zweryfikować generację, statystyki i konfiguracje. Rozdzielić rzeczywistą punktację od interpretacji metrycznej bez nieuzgodnionej zmiany balansu.
- Zebrać i usuwać rzeczywiście występujące warnings/deprecated API. Profilować, a następnie poprawiać potwierdzone koszty. Zmiany Unity/pakietów wykonywać jako osobny, weryfikowalny zakres.

### Phase 3 - Refactor

- Stopniowo rozdzielić stan sesji, wejście, generowanie, pomiary, zapis i prezentację.
- Zapewnić powtarzalny reset i możliwość podania kontrolowanego wejścia bez telefonu; przygotować kontrolę RNG i logowanie parametrów próby.
- Ograniczać singletony i zależności od nazw/tagów tam, gdzie poprawi to testowalność. Zachować istniejące sterowanie człowieka jako punkt porównawczy.

### Phase 4 - Improve

- Rozpocząć osobno uzgodniony etap magisterki **„Opracowanie i analiza algorytmów uczenia maszynowego do sterowania agentem w grze typu endless runner.”**
- Ustalić pytania badawcze, obserwacje, akcje, nagrody, warunki końca epizodu oraz metryki. Nie utożsamiać obecnego wyniku z fizycznym dystansem.
- Dopiero wtedy wybrać algorytmy i narzędzia zgodne z ustaloną wersją Unity, przygotować bazowe sterowanie porównawcze oraz powtarzalne scenariusze treningu i ewaluacji.
- Nowe funkcje, ulepszenia UI i mechaniki rozwijać po ustaleniu ich wpływu na porównywalność eksperymentów; multiplayer i sklep nie są warunkiem badania sterowania agentem.
