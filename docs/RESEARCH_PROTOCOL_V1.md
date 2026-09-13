# Turbo Dash Research Protocol v1

Status: **zamrożony po implementacji i weryfikacji pilotażowej**. Ten dokument jest źródłem prawdy dla eksperymentów deklarujących `protocolVersion = 1`. Środowisko używa Unity **2022.3.4f1**. Observation v1 pozostaje dostępna wyłącznie jako referencja diagnostyczna.

## Czas i akcje

| Parametr | Protocol v1 |
| --- | --- |
| Fixed timestep | 0,01 s (100 kroków fizyki/s) |
| Decision interval | 0,05 s |
| Decision frequency | 20 Hz |
| Kroki fizyki na akcję | 5 |
| Główna action space | Discrete: `LEFT`, `NONE`, `RIGHT` |
| Dodatkowa action space | Continuous steering w `[-1, 1]` |
| Maksymalna prędkość sterowania agentów | 144 stopnie/s w obu przestrzeniach |

`DecisionScheduler` korzysta z całkowitego licznika kroków fizyki. Po resecie licznik wynosi zero, a utrzymywana akcja to `NONE`. Kontroler jest wywoływany w krokach 0, 5, 10, ..., a zwrócona akcja jest utrzymywana przez pięć kroków. Półotwarty przedział `[0,00; 1,00)` zawiera więc dokładnie 20 decyzji, w krokach od 0 do 95; decyzja dokładnie w 1,00 s należy do następnego przedziału. Decyzja w kroku 0 usuwa początkowe 0,05 s wymuszonego `NONE`.

Sterowanie człowieka pozostaje na oryginalnej ścieżce `Update`. Scheduler dotyczy wyłącznie Research Mode. Znak jest względny wobec gracza w obu lokacjach: dodatni steering oznacza `LEFT`, ujemny `RIGHT`.

## Epizod

Każdy standardowy epizod zaczyna się z wynikiem 0, poziomem 1, lokacją `Inside`, trzema życiami, bez Shield, bez ochrony czasowej, z zerowym Boost charge i nieaktywnym Turbo. Standardowy limit to 300 s czasu gry; `maxScore = 0`, więc wynik nie kończy epizodu protokołu.

| Wynik | Znaczenie | Flagi CSV |
| --- | --- | --- |
| `LivesExhausted` | Prawdziwy terminal środowiska po utracie wszystkich aktualnie dostępnych żyć | `terminated=true`, `truncated=false` |
| `MaxDuration` | Odcięcie przez limit czasu | `terminated=false`, `truncated=true` |
| `MaxScore` | Opcjonalne, niestandardowe odcięcie przez skonfigurowany wynik | `terminated=false`, `truncated=true` |
| `ResetRequested` | Anulowana próba | bez zdarzenia wyniku, callbacku i wiersza CSV |

Czas gry, `timeInside` i `timeOutside` są sumowane z kroków fizyki po 0,01 s. Warunki końca są odczytywane po logice gameplayu i kolizjach. Unity może wykonać kilka kroków fizyki przed jedną renderowaną klatką, dlatego końcowy zapis czasu może nieznacznie różnić się przy przyspieszonym `timeScale`. Efekt zmierzono w pilocie; nie zmienia on decision interval.

## Observation v2

`ObservationFrame.SchemaVersion = 2`. Wektor ma stałe **236 floatów**:

```text
8 global + 3 tuby * 76 cech = 236
```

Provider czyta bieżący stan gry, transformy i `CircularGeometry`. Nie używa kamery, obrazu, raycastów, seeda ani przyszłego losowania generatora. Tuby są uporządkowane po world Z, a następnie po stabilnej kolejności generacji. Uwzględniane są najwyżej trzy najbliższe tuby, których tylna krawędź nie minęła gracza. Każda brakująca tuba jest reprezentowana przez 76 zer.

### Stan globalny: indeksy 0–7

| Indeks | Pole | Kodowanie |
| ---: | --- | --- |
| 0 | `livesNormalized` | `playerLives / maxPlayerLives` |
| 1 | `hasShield` | 0/1 |
| 2 | `boostCharge` | bieżąca znormalizowana wartość paska Turbo |
| 3 | `boostActive` | 0/1 |
| 4 | `temporaryProtection` | `playerImmortality`, 0/1 |
| 5 | `environmentSpeedNormalized` | `speed / (50 + speed)` |
| 6 | `isOutside` | Inside 0, Outside 1 |
| 7 | `levelNormalized` | `level / (1 + level)` |

### Układ tuby

Tuba `t` ma indeks bazowy `8 + 76*t`, dla `t = 0, 1, 2`. Indeksy bazowe wynoszą 8, 84 i 160.

| Offset względny | Pole | Kodowanie |
| ---: | --- | --- |
| 0 | `exists` | 0/1 |
| 1 | `timeToReach` | wzór poniżej |
| 2 | `hasPortal` | 0/1 |
| 3 | `hasHazard` | 0/1; pozostaje ustawione, gdy ruchomy hazard jest chwilowo poza orbitą gracza |

Dla tuby o pozycji środka `zTube`, długości `L`, płaszczyźnie gracza `zPlayer` i bieżącej prędkości środowiska `v`:

```text
seconds = max(0, zTube - L/2 - zPlayer) / max(v, 0.0001)
timeToReach = seconds / (1 + seconds)
```

Wzór mapuje nieujemny czas do `[0,1)` i daje zero dla bieżącej lub już rozpoczętej tuby.

### Hazard grid: offsety względne 4–63

Pełna orbita jest podzielona na 12 sektorów po 30 stopni. Kąty są normalizowane do `[-pi, pi)`, a dodatni kąt wskazuje kierunek istniejącej akcji `LEFT`. Zastosowanie `LEFT` przesuwa dodatni cel w kierunku zera w lokacji Inside i Outside.

Sektor `s` ma środek `-pi + s*(2*pi/12)`. Sektor 0 ma środek w `-pi` i przechodzi przez granicę `-pi/pi`; sektor 6 ma środek w zerze. Wiersz sektora zaczyna się od `tubeBase + 4 + 5*s`.

| Offset wiersza | Pole | Kodowanie |
| ---: | --- | --- |
| 0 | `wallOccupancy` | suma przedziałów Wall po ich złączeniu / szerokość sektora, ograniczona do 0..1 |
| 1 | `obstacleOccupancy` | suma przedziałów Obstacle po ich złączeniu / szerokość sektora, ograniczona do 0..1 |
| 2 | `nearestHazardDistance` | najbliższy przecinający collider: `Clamp01((bounds.min.z-zPlayer)/240)`; 0 przy braku |
| 3 | `movingHazard` | 1, jeżeli zajęta geometria należy do aktywnego `ObstacleMovement` |
| 4 | `approximateGeometry` | 1, jeżeli część zajętości pochodzi z geometrii oznaczonej przez `CircularGeometry` jako approximate |

Przedziały kątowe są łączone przed podzieleniem przez szerokość sektora, więc nakładające się collidery nie podnoszą occupancy powyżej 1. `nearestHazardDistance = 0` jest rozróżniane przez pola occupancy. Ruchomy collider znajdujący się obecnie poza orbitą nie tworzy fałszywej zajętości, natomiast nagłówek `hasHazard` zachowuje informację o jego logicznej obecności.

### Bonusy strategiczne: offsety względne 64–75

Eksponowane są wyłącznie Heart, Shield i Boost, w tej kolejności. Bonus `b` zaczyna się od `tubeBase + 64 + 4*b`.

| Offset wiersza | Pole |
| ---: | --- |
| 0 | `exists` |
| 1 | `sin(relativeAngle)` |
| 2 | `cos(relativeAngle)` |
| 3 | `Clamp01((bounds.min.z-zPlayer)/240)` |

Jeśli istnieje kilka colliderów jednego typu, provider wybiera najbliższy dostępny według `bounds.min.z`. Gold i Diamond pozostają w gameplayu i metrykach epizodu, lecz są celowo niewidoczne w Observation v2.

Observation v1 jest zamrożona jako `ObservationProviderV1` / `ObservationFrameV1`, z wersją schematu 1 i 2633 floatami. Jest narzędziem reference/debug i nie trafia do kontrolerów protokołu v1.

## Pilot reward i fitness

Niezależny od algorytmu `PilotRewardCalculator` pobiera wartości `ResearchEvent`. Domyślne, konfigurowalne parametry to `scoreScale = 0.01` i `lifeLossPenalty = 0.5`. Reward zamykany na każdej granicy decyzji wynosi:

```text
decisionReward = scoreDeltaSincePreviousDecision / 100
               - 0.5 * lifeLostSincePreviousDecision
```

Pozostały niepełny przedział jest domykany przy końcu epizodu. `episodeReward` przechowuje sumę w CSV. Kolizja bez utraty życia, zużycie Shield oraz zebranie Heart, Shield, Boost, Gold lub Diamond nie mają bezpośredniego rewardu. Ich wartość wynika z późniejszego przeżycia i wyniku.

Odpowiadający episode fitness wynosi:

```text
fitness = finalScore / 100 - 0.5 * lifeLossCount
```

Kalkulator nie zależy od PPO ani NEAT. Obie wagi są polami konfiguracji, dzięki czemu przyszły protokół może je zmienić bez ingerencji w gameplay.

## Podział seedów

Wersjonowane pliki źródłowe znajdują się w [`Assets/Turbo_Dash/Research/Seeds`](../Assets/Turbo_Dash/Research/Seeds):

| Zbiór | Liczba | Zastosowanie |
| --- | ---: | --- |
| TRAIN | 700 | trening i prace developerskie |
| VALIDATION | 100 | wybór parametrów, wariantów i checkpointów |
| TEST | 200 | wyłącznie zamrożona ewaluacja końcowa |

`ResearchSeedCatalog.ValidateAll` sprawdza wersję protokołu, nazwę zbioru, dokładne liczby, dodatnie wartości int32, globalną unikalność i brak przecięć. Są to zapisane dane, których uruchomienie nie generuje ponownie. Pilot pobierał tylko TRAIN i VALIDATION. TEST przeszedł walidację strukturalną, lecz **status rozgrywki/ewaluacji TEST pozostaje UNUSED**.

## CSV i metryki

Protocol v1 dodaje do istniejącego podsumowania: `protocolVersion`, `observationSchemaVersion`, `decisionInterval`, `decisionCount`, `terminated`, `truncated` i `turboActivations`. `turboActivations` liczy przejścia z nieaktywnego do aktywnego Turbo, a nie zebrane Boosty.

Pełny schemat:

```text
episodeId,controllerType,actionSpaceType,protocolVersion,observationSchemaVersion,
decisionInterval,decisionCount,seed,finalScore,survivalTime,segmentsPassed,
obstaclesEncountered,obstaclesAvoided,collisionsTotal,lifeLossCount,shieldHits,
fatalCollision,heartsCollected,shieldsCollected,boostsCollected,turboActivations,
goldCollected,diamondsCollected,maxLevel,outsideStagesReached,timeInside,timeOutside,
maxEnvironmentSpeed,terminalReason,terminated,truncated,trainingRunId,trainingStep,
generation,episodeReward,fitness,trainingTime
```

CSV używa UTF-8, separatora przecinkowego i kropki dziesiętnej niezależnie od kultury systemu. Każda sesja wymaga nowego pliku. Publiczny launcher edytora:

```text
-batchmode -projectPath <project>
-executeMethod TurboDash.Research.Editor.ResearchMenu.RunBatch
-turboResearchConfig <config.json> -logFile <log>
```

`RunBatch` otwiera `DeafultLevel`, włącza Play Mode, prowadzi i resetuje skonfigurowaną serię, zapisuje CSV, a następnie kończy Unity kodem 0 dla `Finished` lub 1 dla `Faulted`. Nie należy dodawać `-quit`, ponieważ zakończeniem procesu zarządza launcher.
