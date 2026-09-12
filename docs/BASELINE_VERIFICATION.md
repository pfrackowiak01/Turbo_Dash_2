# Weryfikacja wersji bazowej i Research Mode

Data końcowej weryfikacji: **2026-09-13**. Edytor: **Unity 2022.3.4f1** (`35713cd46cd7`). Wszystkie przebiegi wykonano w osobnej kopii projektu w katalogu systemowym TEMP, aby nie ingerować w otwartą sesję Unity. Kopia zawierała `Assets/`, `Packages/` i `ProjectSettings/`; wygenerowane `Library/`, logi i CSV pozostały poza repozytorium.

Testy są programowymi scenariuszami Play Mode uruchamianymi przez edytor w trybie batch. Używają rzeczywistej sceny, komponentów, generatora i fizyki. Nie zastępują ręcznego testu obrazu, dźwięku ani wejścia na urządzeniu.

## Wynik końcowy

| Zestaw | Zakres | PASS | FAIL | Proces Unity |
| --- | --- | ---: | ---: | --- |
| Bazowa wersja przed zmianami | Commit `13e831b`, Menu → TouchControl → gameplay, portal, kolizje, bonusy, Game Over, Retry | 23 | 0 | kod 0 |
| Regresja normalnej gry | Aktualny kod po wdrożeniu Research Mode; ten sam scenariusz | 23 | 0 | kod 0 |
| Pełny Research Mode | Bezpośredni gameplay, sterowanie, obserwacje, RNG, metryki, terminale, reset i CSV | 172 | 0 | kod 0 |
| Publiczny launcher `ResearchMenu.RunBatch` | JSON → scena → Play Mode → 3 epizody → CSV → automatyczne wyjście | 9 punktów kontrolnych | 0 | kod 0 |

Logi obu końcowych zestawów nie zawierały `error CS` ani wyjątków. Unity zgłasza nadal zastane ostrzeżenie o pustym `HeathenEngineering.UX.asmdef` oraz ostrzeżenia, że część istniejących wywołań `DontDestroyOnLoad` dotyczy obiektów niebędących rootami. Nie blokowały one badanych przepływów i nie były przedmiotem tej zmiany.

## Baseline: zwykła gra

Końcowa regresja przeszła następujące sprawdzenia:

- otwarcie `Menu.unity` i wybór TouchControl przez handler Menu;
- przejście z Menu do `DeafultLevel.unity` oraz stan instrukcji: pauza, 3 życia;
- Start przez handler przycisku, wznowienie czasu i naliczanie score Inside;
- LEFT, NONE i RIGHT przez tę samą mapę flag wejścia, której używa klawiatura/dotyk;
- progi level 2 i 3 oraz prędkości 55 i 60;
- zamówienie portalu po przekroczeniu 2800;
- rzeczywiste wygenerowanie prefabu portalu, jego ruch z generatorem i kontakt fizyczny z graczem;
- `FixScore`, wejście Outside oraz level 4;
- fizyczna kolizja Wall, utrata życia i chwilowa ochrona;
- fizyczne zebranie Heart, Shield i Boost;
- pochłonięcie kolizji Obstacle przez Shield;
- ręczna aktywacja turbo, immortality oraz późniejsza kolizja fatalna;
- Game Over z 0 żyć i `Time.timeScale = 0,4`;
- Retry do świeżego stanu instrukcji z trzema życiami i zachowanymi usługami.

Sterowanie zostało podane programowo do istniejącej mapy wejścia, a przyciski wywołano przez ich publiczne handlery. Nie wykonano fizycznego kliknięcia UI ani naciśnięcia klawisza przez system operacyjny. Dotyk i żyroskop wymagają testu na urządzeniu; ten przebieg potwierdza mapowanie i wynikający z niego obrót świata.

## Pełny Research Mode

Końcowy przebieg na aktualnym kodzie zakończył się **172 PASS / 0 FAIL** i objął 13 resetów bez przeładowania sceny. CSV miał jeden nagłówek i 13 wierszy zakończonych epizodów.

Sprawdzono między innymi:

- bootstrap `BeforeSceneLoad`, bez Menu i z jedną instancją wymaganych usług;
- wyłączenie prezentacji Canvas przy zachowaniu logiki turbo i ochrony;
- jednoznaczny reset score, levelu, Inside, trzech żyć, efektów, charge, prędkości, czasu, rotacji, metryk i pięciu nowych tub;
- stabilne liczby singletonów przy wszystkich resetach;
- taki sam układ 35 tub dla seeda 777 mimo 2190 dodatkowych wywołań wizualnego `UnityEngine.Random`;
- inny układ dla innego seeda;
- zgodność discrete/continuous i znaku LEFT/NONE/RIGHT Inside oraz Outside;
- geometrię kołową, zakres przez granicę 0/360, pełny okrąg, rozłączne zakresy słupa i jawne odrzucenie przepełnienia schematu;
- wszystkie 14 używanych assetów Wall/Obstacle/Gem osobno w Inside i Outside, w tym prefab `Gold 3` z 40 colliderami bonusów;
- rzeczywiste kontakty fizyczne Wall, Obstacle, Heart, Shield, Boost, Gold, Diamond oraz odpowiadające im metryki i zdarzenia;
- brak zapisu badawczych walut do PlayerPrefs;
- automatyczne włączenie turbo po pełnym charge, mnożnik score oraz zakończenie drain;
- portal, `FixScore`, cykl Inside/Outside do level 16 i limit prędkości 80;
- definicje encountered/avoided/segmentsPassed oraz jednokrotne naliczanie;
- śmierć po wykorzystaniu trzech żyć z wcześniej zebranym Heart;
- terminale `LivesExhausted`, `MaxDuration` i `MaxScore`;
- format CSV, kropkę dziesiętną, quoting i puste pola przygotowane na trening;
- trzy automatycznie następujące epizody oraz brak zdarzenia `sceneLoaded` między nimi.

Cztery końcowe testy adapterów wymagane po ostatniej zmianie również przeszły:

- `Submitted continuous controller drives real FixedUpdate rotation and CSV identity`;
- `Submitted action is cleared on episode reset`;
- `Submitted discrete controller drives real FixedUpdate rotation and CSV identity`;
- `No sceneLoaded event between research episodes`.

## Publiczny launcher RunBatch

Launcher zweryfikowano niezależnie od `TurboDashResearchProbe.Run`. Unity uruchomiono z:

```text
-executeMethod TurboDash.Research.Editor.ResearchMenu.RunBatch
-turboResearchConfig <config.json>
```

JSON określał 3 epizody, seedy 7001, 7002 i 7003, limit czasu 0,25 s oraz ścieżkę CSV w TEMP. Dziewięć punktów kontrolnych zakończyło się powodzeniem:

1. metoda publiczna została wykonana i log potwierdził otwarcie `Assets/Turbo_Dash/Design/Scenes/DeafultLevel.unity`;
2. scena została załadowana, a Play Mode uruchomił `ResearchMode`;
3. ścieżka wyjściowego CSV została zalogowana;
4. generator utworzył tuby dla wszystkich epizodów;
5. CSV został utworzony;
6. zawierał nagłówek i dokładnie 3 wiersze danych;
7. identyfikatory wynosiły 1,2,3, a seedy 7001,7002,7003;
8. wszystkie epizody zakończyły się `MaxDuration` i miały `NoAction / Discrete`;
9. proces Unity zakończył się automatycznie kodem 0, bez błędów kompilacji i wyjątków.

## Powtórzenie testów

[Invoke-UnityVerification.ps1](../Tools/Verification/Invoke-UnityVerification.ps1) tworzy nową izolowaną kopię. Przykłady:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/Verification/Invoke-UnityVerification.ps1 -Mode Baseline -Revision 13e831b
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/Verification/Invoke-UnityVerification.ps1 -Mode Baseline
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/Verification/Invoke-UnityVerification.ps1 -Mode Research
```

`TurboDashBaselineProbe.cs` i `TurboDashResearchProbe.cs` są kopiowane wyłącznie do tymczasowego `Assets`; nie trafiają do źródeł runtime gry. Przebieg `Research` w skrypcie uruchamia rozbudowany harness. Publiczny launcher należy okresowo sprawdzać osobnym wywołaniem `ResearchMenu.RunBatch` zgodnie z [instrukcją środowiska](ML_RESEARCH_ENVIRONMENT.md#1-architektura-researchmode).

## Zakres nieweryfikowany

- fizyczne wejście dotykowe i żyroskop na urządzeniu;
- build Android i standalone player badawczy;
- jakość wizualna, dźwięk i UX pełnej ręcznej sesji;
- długotrwałe profilowanie tysięcy epizodów, stabilność bitowa na różnych maszynach i wysokie `Time.timeScale`;
- uczenie i ocena Rule-based, PPO lub NEAT;
- finalne seedy, limity, częstotliwość decyzji oraz reward/fitness.

Szczegóły implementacji, obserwacji, RNG, metryk i rozbieżności balansu zawiera [ML_RESEARCH_ENVIRONMENT.md](ML_RESEARCH_ENVIRONMENT.md).
