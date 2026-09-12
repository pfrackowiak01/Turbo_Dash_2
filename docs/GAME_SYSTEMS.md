# Wykryte systemy gry

Stan: 2026-09-10. Opis na podstawie kodu, scen, prefabów i konfiguracji. Nie wykonano testów runtime. Ścieżki klas odnoszą się do `Assets/Turbo_Dash/Code/`; pełny inwentarz jest w [REPOSITORY_INVENTORY.md](REPOSITORY_INVENTORY.md), a priorytety usterek w [PROJECT_AUDIT.md](PROJECT_AUDIT.md).

## 1. Gracz, ruch i input

**Cel:** omijanie przeszkód na obwodzie tunelu. **Klasy:** `EnvironmentMovement`, `PlayerCollision`, `GameManager`, `SaveAndLoadManager`, `GameMode`. `PlayerMovement` jest osobnym, prawdopodobnie wcześniejszym prototypem; jego GUID nie występuje w zbadanych scenach, prefabach ani assetach.

W używanej scenie porusza się otoczenie. `EnvironmentMovement` obraca Transform `Environment` wokół Z, a `PlayerCollision.Update` ustawia gracza na `(0,-4,0)` lub `(0,6.5,0)` zależnie od Inside/Outside. Utrata wszystkich żyć wyłącza renderer gracza i komponent sterowania otoczeniem.

| Tryb | Implementacja |
| --- | --- |
| `Gyroscope`, indeks 0 | `Quaternion.Inverse(initialRotation) * Input.gyro.attitude`; składowa Z przemnożona przez Rad2Deg, ograniczana do ±22 i przemnożona przez rotationSpeed oraz deltaTime |
| `TouchControl`, indeks 1 | Lewa/prawa połowa ekranu z `Input.touches` i strzałki klawiatury; oba kierunki lub brak wejścia dają zero |
| `Multiplayer`, indeks 2 | Asset opisowy istnieje, `unlocked=0`; brak obsługującej go gałęzi wejścia i implementacji sieci |

Kalibracja (`GameManager.ResetGyroscopeRotation`) włącza żyroskop i zapisuje orientację. Wykonuje się na starcie GameManager oraz po użyciu odpowiednich przycisków `LevelLoader`. Domyślna prędkość obrotu to 12; wejście manualne używa jej dwukrotnie, co daje 144 stopnie/s przed przemnożeniem przez deltaTime. Dla Outside znak obrotu zostaje odwrócony.

**Komunikacja:** wybrany asset z SaveAndLoadManager → input → `GameManager.rotationAmount` → obrót świata. Pauza kontrolowana jest flagą GameManager i skalą czasu.

**Problemy:** brak sprawdzenia dostępności żyroskopu i filtracji dotyku nad UI; składowa kwaternionu nie jest kątem Eulera; szerokość ekranu jest zapamiętywana tylko raz. Warunek myszy otacza pętlę po dotykach, więc sam klik myszą nie daje kierunku. Wybranie nieobsługiwanego trybu multiplayer jest możliwe przez menu. Dokładność mapowania żyroskopu wymaga pomiaru na telefonie.

## 2. Tunel i generowanie poziomów

**Cel:** nieskończona trasa o ograniczonej liczbie aktualnie istniejących segmentów. **Klasy:** `EnvironmentManager`, `TubeManager`, `TubeMovement`, `GameManager`, `RandomArrangement`, `ISpawnable`, `Wall`, `Obstacle`, `Gem`, `Theme`.

`EnvironmentManager.Start` tworzy pięć tub. Długość segmentu to 60, strefa usuwania to Z < -60, a nowe tuby powstają przy Z=240. Prędkość początkowa wynosi 50 jednostek/s; awanse dodają 5 aż do dodatkowych 30. Interwał generacji jest liczony jako 60/prędkość, a warunek w FixedUpdate używa korekty -0.01 s. Po zmianie lokacji wszystkie aktywne obiekty z tagiem Tube są usuwane i otoczenie jest odtwarzane.

Pierwsze trzy tuby są bezpieczne, po zmianie lokacji dwie. Następne zawierają portal albo wylosowaną przeszkodę/ścianę oraz opcjonalny klejnot. Progi wyboru przeszkody to 30/40/50/60 zależnie od levelu; `Random.Range(1,100)` daje 99 wyników, więc nie są to dokładnie takie procenty. `Random.Range(1,3)==1` daje 50%, choć komentarz mówi o 33%. Rotacja prefabu wybierana jest spośród 0,45,90,135,180,225,270 stopni; 315 stopni jest wykluczone przez `Random.Range(0,7)`.

**Komunikacja:** GameManager filtruje dane → TubeManager wybiera zawartość → Instantiate prefabu → jego skrypty Start/FixedUpdate → PlayerCollision reaguje na tagi. Prefaby przeszkód mają również zagnieżdżone elementy pomocnicze, w tym wyłączone tuby; nie należy traktować wszystkich zależności prefabów jako aktywnych generatorów.

**Problemy:** brak własnego ziarna i resetu generatora losowości; czasowe zamiast przestrzennego dokładanie segmentów może wymagać kontroli szczelin przy zmianie prędkości. Licznik bezpiecznych tub jest globalny i konsumowany w Start wielu instancji. Brak kontroli przejezdności wygenerowanego układu. Regularne Instantiate/Destroy, logowanie i materiały wymagają profilowania przed optymalizacją.

## 3. Progresja, wynik i portale

**Cel:** rosnąca trudność i naprzemienne etapy Inside/Outside. **Klasy:** `GameManager`, `PlayerCollision`, `EnvironmentManager`, `TubeManager`, `UIGame`.

Wynik to akumulowany czas: `deltaTime * 23 * (gameLevel + 10) / 10`, podwajany podczas turbo. Na poziomie 1 daje 25.3 jednostki wyniku/s, chociaż tuby przesuwają się z prędkością 50 jednostek/s. HUD opisuje wynik jako metry, a jego przyrost jako m/s; nie jest to pomiar geometrii świata. `FixScore` może dodatkowo skokowo podnieść wynik przy portalu.

Po przekroczeniu progów 1000 i 2000 wykonywany jest `GameLevelUp`. Progi 2800 i 3800 zapowiadają portal; generator tworzy końcowy segment i blokuje dalsze spawny do zmiany lokacji. Trigger portalu wyłącza zapowiedź, koryguje wynik, zmienia lokację, awansuje poziom i wywołuje audio/shake. Outside nie jest osobną sceną; bazowy cykl odpowiada urozmaiceniu co czwartego poziomu opisanemu w pracy.

**Komunikacja:** wynik → progi GameManager → flaga portalu → generator → kolizja → zmiana lokacji i list spawnów → przebudowa otoczenia i HUD.

**Problemy:** filtr `UpdateObjectListToSpawnByLevel` zawsze używa `gameInsideDifficulty`, nawet Outside. Wszystkie aktualnie przypisane dane mają `Any`, więc problem jest ukryty. Pola `spaceLevel` i część parametrów nie sterują algorytmem, który zakłada cykl czterech poziomów. Wynik nie powinien zostać bez analizy przyjęty jako fizyczny dystans/nagroda w przyszłych badaniach.

## 4. Przeszkody i kolizje

**Cel:** obrażenia, unikanie ścian i ruchomych przeszkód. **Klasy:** `PlayerCollision`, `ObstacleMovement`, `RandomArrangement`, dane Wall/Obstacle i prefaby.

`OnTriggerEnter` rozróżnia tagi Wall, Obstacle, Portal i pięć rodzajów bonusu. Nie znaleziono przeciwników z AI, pościgu, NavMeshAgent ani zachowań decyzyjnych. Ruchome przeszkody to animowane obiekty sceny, nie autonomiczni przeciwnicy.

`ObstacleMovement.FixedUpdate` opcjonalnie liczy sinusoidalną pozycję poziomą/pionową i obrót. SideToSideCube włącza ruch boczny (zasięg 3.25, prędkość 4); piły obracają się, m.in. z parametrem 200. Bazowy Cube ma wszystkie ruchy wyłączone; warianty nadpisują te wartości.

**Komunikacja:** collidery/tagi → PlayerCollision → GameManager, EnvironmentMovement, AudioSystem, AnimationManager i efekty cząsteczkowe.

**Problemy:** przy niezerowych współrzędnych początkowych ruch sinusoidalny dodaje je ponownie do bieżącej pozycji na pozostałych osiach i może powodować dryf; w sprawdzonym SideToSideCube te osie zaczynają się od zera. `DestroyDetectedObject` nie usuwa obiektu bez rodzica, a dla złożonych przeszkód opiera wybór usuwanego obiektu na tagu rodzica. Zmiana hierarchii może więc zmienić zachowanie kolizji.

## 5. Życia, tarcza, nieśmiertelność i turbo

**Cel:** przeżywalność i czasowe bonusy. **Klasy:** `GameManager`, `PlayerCollision`, `ImmortalityEffect`, `UIGame`, `FollowPlayer`, `AnimationManager`, `AudioSystem` i dane Gem.

| Zdarzenie | Działanie |
| --- | --- |
| Start | 3 życia, brak tarczy i nieśmiertelności |
| Heart | +1 życie do maksimum 3, pop-up i SFX |
| Shield | Jednorazowa ochrona; renderer wskazany tagiem jest przełączany |
| Boost | +0.4 wartości slidera turbo, ograniczenie do 1 |
| Gold / Diamond | +1 waluty na trigger, zapis pod kluczem Coins/Diamonds; warianty Gold są układami wielu klejnotów |
| Trafienie podczas turbo/nieśmiertelności | Brak utraty życia |
| Trafienie z tarczą | Usunięcie trafionego obiektu według hierarchii, utrata tarczy, efekt |
| Trafienie z więcej niż jednym życiem | -1 życie, eksplozja, usunięcie przeszkody i nieśmiertelność |
| Ostatnie życie | GameOver, ukrycie gracza, spowolnienie 0.4 i próba zapisu rekordu |

Turbo ładuje się w `UIGame.Update` o 0.01/s czasu gry. Aktywacja startuje coroutine odejmującą 0.01 co 0.1 s czasu gry, uruchamia FOV 40→90, zmianę offsetu kamery, efekty i odporność na kolizje. Jednocześnie pasywne ładowanie pozostaje aktywne. Zatem deklarowanego czasu turbo nie należy wyliczać z samego tempa opróżniania; zmieniają go równoległe ładowanie, bonusy i skala czasu. Turbo bezpośrednio podwaja wynik, nie prędkość tub; wcześniejsze awanse mogą ją zwiększyć pośrednio.

`ImmortalityEffect.Update` steruje rendererem, ale także wyzerowuje `playerImmortality`: po 3 s lub 11 s przy turbo. Ponowne wywołanie bonusu, gdy efekt już trwa, nie resetuje automatycznie jego timera. Samo turbo nadal chroni, bo kolizje sprawdzają oddzielną flagę `turboEffectEnable`.

**Problemy:** mechanika zależna od UI i renderera; równoległe ładowanie/zużycie, brak zabezpieczenia przed ponowną aktywacją turbo oraz przełączanie widoczności zamiast ustawienia docelowego stanu. To ważne przed wyłączaniem grafiki na potrzeby ML.

## 6. Stan gry, czas i kontynuacja

**Cel:** start, gra, pauza, przegrana, retry i jednorazowa kontynuacja. **Klasy:** `GameManager`, `TimeManager`, `LevelLoader`, `UIGame`.

Stan to flagi `gameStart`, `gamePaused`, `gameHasEnded` oraz `Time.timeScale`. `TimeManager.Start` ustawia 1, potem pauzę 0. Przycisk startu wyłącza gameStart i przełącza pauzę. GameOver zmienia skalę na 0.4. Continue daje jedno życie, wyłącza gameHasEnded, ustawia skalę 1 i włącza nieśmiertelność. Nie zawiera reklamy ani płatności.

**Komunikacja:** UnityEvent przycisku → LevelLoader → TimeManager/GameManager → flagi odczytywane przez UI i komponenty świata.

**Problemy:** `UIGame` rozpoczyna coroutine kontynuacji w każdej klatce GameOver, dopóki `chanceToContinue` pozostaje true. Wszystkie instancje zerują i zmieniają wspólny elapsedTime. Limit szansy ustawiany jest dopiero w ShowEndButtons, nie przy kliknięciu Continue. StartGame nie zeruje wszystkich flag (np. isNewHighScore/showLevelUP), nie ustawia spójnie skali czasu, a trwały TimeManager nie powtarza Start przy reloadzie sceny. Zdarzenia trzeba sprawdzić osobno dla pierwszego startu, restartu z pauzy, retry po śmierci i powrotu z menu.

## 7. UI i nawigacja między scenami

**Cel:** wybór trybu, HUD, ekrany stanu, przejścia i widok walut. **Klasy:** `UIMenu`, `UIGame`, `LoadLootPanel`, `LevelLoader`; TMP, uGUI, EventSystem i Animator.

Menu pokazuje rekord oraz nazwę trybu. HUD pokazuje wynik, pochodną wyniku jako prędkość, poziom, waluty, życia, tarczę i turbo. Prefab LootPanel jest użyty w Menu, Shop i Customization. `LevelLoader.LoadLevel` ustawia trigger crossfade, czeka `WaitForSeconds(1)` i wywołuje `SceneManager.LoadScene(index)`.

Aktywne sceny to Menu=0, DeafultLevel=1, Shop=2, Customization=3. Przyciski menu rzeczywiście wskazują istniejące metody Play/Shop/Customization i zmiany trybu. W scenach Shop/Customization znaleziono powrót do menu, bez operacji zakupu ani wyboru skina. W LevelLoader pozostają indeksy SkillTree=4 i Leaderboard=5, bez odpowiadających im scen; SkillTreeButtonClicked nie ma znalezionego powiązania w scenach/prefabach.

**Problemy:** ładowanie po liczbach wiąże zachowanie z Build Settings. WaitForSeconds i Animator crossfade używają czasu skalowanego; przy zerowym timeScale przejście może stanąć. PlayButtonClicked łączy coroutine ładowania z natychmiastowym RestartGame, jeśli GameManager istnieje. Ten restart przed zmianą sceny wyszukuje kamerę gameplayową, której w menu nie ma. Pełny opis skutków w audycie.

## 8. Kamera, rendering i efekty

**Cel:** perspektywa gracza, odczucie turbo/kolizji, wygląd zakrzywionego tunelu. **Klasy:** `FollowPlayer`, `AnimationManager`, `BendControllerRadial`, `GemAnimationScript`, `DestroyParticleSystem`, `ImmortalityEffect`; `Theme`, custom surface shader i Post Processing.

Kamera jest dzieckiem obiektu Camera Follow. FollowPlayer zmienia pozycję lokalną i FOV, AnimationManager steruje animatorem rodzica (`shake`, `shakeTurbo`). Osobny Animator na Main Camera ma nierozwiązane odwołanie do kontrolera — to nie jest ten sam kontroler co działające powiązanie Camera Follow.

Dwa aktywne BendControllerRadial zapisują te same globalne parametry z różnymi referencjami, skalą Z i flatMargin. Custom shader deformuje wierzchołki wizualnie; w kodzie nie ma analogicznej deformacji colliderów. Zbierane bonusy tworzą warianty prefabu Explosion, z którego dziedziczą sprzątanie przez DestroyParticleSystem.

**Problemy:** konflikt globalnych parametrów shadera zależny od kolejności Update; brak gwarancji poprawnego rebindowania kamery po reloadzie; floating klejnotów ma błąd znaku i zależność od FPS, ale jest wyłączony w obecnych prefabach gry. Usunięcie efektu według czasu emisji może uciąć żyjące jeszcze cząsteczki. Migracja render pipeline wymaga osobnej analizy shaderów i postprocessingu.

## 9. Audio i wibracje

**Cel:** muzyka menu/gry oraz informacja o kliknięciach, kolizjach i bonusach. **Klasy:** `AudioSystem`, wywołujące go GameManager, PlayerCollision, LevelLoader, UIMenu i UIGame.

AudioSystem ma osobne źródła SFX i muzyki. Menu startuje z głośnością 1, gameplay z 0.3. Dźwięki odtwarzane są przez PlayOneShot; obie sceny zawierają konfigurację AudioSystem. Powrót do menu przełącza muzykę. Eksplozja gracza wywołuje `Handheld.Vibrate`.

**Problemy:** GameManager zapisuje `AudioSystem.Instance` w inicjalizatorze pola i nie odświeża tej referencji — jeśli singleton wtedy jeszcze nie istnieje, efekty mogą rzucić wyjątek. Obiekty audio są dziećmi kontenera singletonowego. Metody ToggleSFX/ToggleMusic istnieją, lecz nie znaleziono ich użycia w kodzie ani zdarzeniach scen/prefabów; brak zapisu ustawień głośności.

## 10. Zapis, rekordy, konfiguracja i ekonomia

**Cel:** pamiętanie walut oraz rekordów per tryb. **Klasy:** `SaveAndLoadManager`, `GameManager`, `GameMode`, `UIMenu`, `UIGame`, `LoadLootPanel`.

| Dane | Klucze / przepływ |
| --- | --- |
| Waluty globalne | `Coins`, `Diamonds`; odczyt podczas StartGame, zapis po zebraniu, osobny LootPanel odczytuje co klatkę |
| Rekord wyniku | `gyroscopeHighScore`, `touchControlHighScore`, `multiplayerHighScore`; próba zapisu przy GameOver, odczyt w UIMenu.Start |
| Rekord prędkości | `gyroscopeHighSpeed`, `touchControlHighSpeed`, `multiplayerHighSpeed`; próba zapisu przez UIGame; metoda odczytu istnieje, brak znalezionych wywołań |
| Wybór trybu | Referencja do assetu w trwałym SaveAndLoadManager; brak zapisu wyboru do PlayerPrefs |
| Motyw | GameManager wybiera nazwę lub fallback Default; CustomTheme nie jest podpięty do allThemes i ma niepełne/stare dane |

**Problemy:** oba zapisy rekordów porównują nową wartość z rekordem już zaktualizowanym w pamięci, przez co nie wykonują SetInt/SetFloat. Tablica trybów i klucze zakładają dokładnie indeksy 0–2. Konfiguracja assetów miesza się z rekordami runtime. Nie ma zapisu całej rozgrywki, checkpointu, wersjonowania danych ani synchronizacji online. Kolekcjonowanie walut nie dowodzi istnienia ekonomii zakupów; sklep nie ma jej implementacji.

## Funkcje, których nie potwierdzono

Nie znaleziono wdrożonych systemów ML/treningu, sieciowego multiplayera, reklam, zakupów, drzewka umiejętności, osiągnięć ani rankingu online. Brak też odrębnego systemu przeciwników AI. Są nazwy, pola lub plany części z nich — nie należy opisywać ich jako działających funkcji. Zestaw skryptów demonstracyjnych w Addons nie jest dodatkową implementacją gameplayu Turbo Dash.
