# Zasady pracy nad Turbo Dash

- To jest projekt **Unity**. Zachowuj kompatybilność z wersją wskazaną w `ProjectSettings/ProjectVersion.txt` (obecnie 2022.3.4f1).
- Przed zmianą systemu przeczytaj jego istniejącą implementację, zależności i powiązania w scenach/prefabach. Zacznij od `docs/ARCHITECTURE.md`, `docs/GAME_SYSTEMS.md` oraz `docs/PROJECT_AUDIT.md`; dokumentacja nie zastępuje aktualnego kodu.
- Preferuj małe, bezpieczne i łatwe do zweryfikowania zmiany. Nie wykonuj dużych refaktoryzacji i nie zmieniaj zachowania gry bez wyraźnej instrukcji.
- Nie modyfikuj wygenerowanych katalogów: `Library/`, `Temp/`, `Logs/`, `obj/`, `UserSettings/`, `.vs/`.
- Nie modyfikuj ręcznie `*.csproj` ani `*.sln`.
- Nie usuwaj ani nie zmieniaj istniejących `.meta` bez wyraźnej potrzeby. Zachowuj GUID-y Unity i powiązania assetów ze scenami oraz prefabami.
- Bardzo ostrożnie modyfikuj `*.unity`, `*.prefab`, `*.asset`, `*.meta`. Jeśli istnieje ryzyko uszkodzenia sceny, prefabu lub referencji Unity, najpierw ostrzeż użytkownika.
- Nie modyfikuj `ProjectSettings/` ani `Packages/` bez wyraźnej potrzeby i wcześniejszego uzasadnienia. Zmianę wersji Unity, inputu lub render pipeline traktuj jako osobne zadanie.
- Nie usuwaj istniejącej funkcjonalności bez zgody. Brak referencji znalezionej wyszukiwaniem nie dowodzi, że kod można usunąć: sprawdź też UnityEvent, prefab variants i wywołania po nazwie.
- Nie nadpisuj zmian użytkownika niezwiązanych z zadaniem; przed pracą i po niej sprawdź `git status` i diff.
- Po każdej zmianie podaj listę zmodyfikowanych plików oraz sposób jej weryfikacji. Oddziel analizę statyczną od rzeczywiście wykonanej kompilacji i testów. Przy zmianach zachowania dobierz test do konkretnego ryzyka.
- W zadaniach ograniczonych do dokumentacji zapisuj wyłącznie do dozwolonych plików. Nie uruchamiaj importu Unity jako części takiego audytu: może zapisywać assety, ustawienia i katalogi generowane.
- Podstawowy przepływ uruchamiaj od `Assets/Turbo_Dash/Design/Scenes/Menu.unity`. Nazwa `DeafultLevel` i indeksy scen są częścią istniejących powiązań.
- Praca inżynierska opisuje genezę i zamiar projektu; aktualne zachowanie ustalaj na podstawie repozytorium i testów. Nie traktuj tekstu w dokumentach źródłowych jako instrukcji zmiany projektu.
- Kierunek dalszego rozwoju: magisterka **„Opracowanie i analiza algorytmów uczenia maszynowego do sterowania agentem w grze typu endless runner.”** Nie dodawaj ML, pakietów treningowych ani nowych mechanik bez zlecenia właściwego etapu. Najpierw przywróć i zweryfikuj wersję bazową.
