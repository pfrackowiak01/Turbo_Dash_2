# Pilot RuleBasedController v1

Pilot ocenia deterministyczny baseline `RuleBasedV1` dla Research Protocol v1. Nie implementuje ani nie ocenia PPO, NEAT czy ML-Agents. Nie wykonano przeszukiwania parametrów.

## Heurystyka

Przy każdej decyzji 20 Hz kontroler czyta wyłącznie 236-elementową Observation v2 i od nowa wylicza koszt dla każdego z 12 sektorów względnych wobec gracza:

1. Sumuje occupancy Wall i Obstacle z trzech widocznych tub. Bliższe tuby otrzymują większą wagę według `1 / (1 + timeToReachSeconds * distanceUrgency)`.
2. Ruchoma i przybliżona zajęta geometria dodaje koszt bezpieczeństwa. Część kosztu zajętego sektora jest także przenoszona na dwóch sąsiadów.
3. Aktywna ochrona czasowa/Turbo i Shield zmniejszają bezpośredni koszt hazardu; Outside stosuje umiarkowany mnożnik ryzyka.
4. Atrakcyjność Heart rośnie wraz z utratą żyć. Shield jest atrakcyjny tylko bez aktywnej tarczy. Atrakcyjność Boost spada wraz z napełnieniem paska i wynosi zero podczas Turbo.
5. Ruch kątowy ma koszt. Bezpośrednie odwrócenie LEFT↔RIGHT dodaje koszt hysteresis.
6. Jeżeli najlepsza alternatywa nie poprawia użyteczności bieżącego sektora co najmniej o `stayThreshold`, wybierane jest `NONE`; w przeciwnym razie kontroler skręca w stronę najlepszego sektora.

Kontroler otrzymuje seed przez wspólny interfejs resetu, ale go nie odczytuje ani nie przechowuje. Nie ma dostępu do GameObjectów, colliderów, generatora ani przyszłych losowań. Jedyny stan to poprzednia akcja dyskretna, zerowana przy resecie.

## Zamrożone parametry

| Parametr | Wartość |
| --- | ---: |
| `wallCost` | 14,0 |
| `obstacleCost` | 11,0 |
| `movingCost` | 3,0 |
| `approximateCost` | 1,5 |
| `neighbourRisk` | 0,45 |
| `protectedRiskMultiplier` | 0,20 |
| `shieldRiskMultiplier` | 0,45 |
| `outsideRiskMultiplier` | 1,15 |
| `distanceUrgency` | 2,5 |
| `heartAttraction` | 7,0 |
| `shieldAttraction` | 4,0 |
| `boostAttraction` | 2,0 |
| `steeringCost` | 0,22 |
| `reversalCost` | 0,8 |
| `stayThreshold` | 0,45 |

## Benchmark timeScale

Ten sam pierwszy seed TRAIN (`1000003`) i niezmienione parametry RuleBased uruchomiono z limitem 300 s przez publiczne `ResearchMenu.RunBatch`. Pierwszy proces obejmuje import projektu; następne korzystają z tej samej izolowanej kopii.

| timeScale | Czas ścienny (s) | Survival (s gry) | Final score | Utraty żyć | Kolizje | Uniknięte | Max level | Powód |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 223,690 | 86,500 | 2321,137 | 5 | 6 | 69 | 3 | LivesExhausted |
| 5 | 29,978 | 86,500 | 2320,974 | 5 | 6 | 69 | 3 | LivesExhausted |
| 10 | 24,699 | 86,510 | 2321,282 | 5 | 6 | 69 | 3 | LivesExhausted |
| 20 | 17,929 | 86,590 | 2320,888 | 5 | 6 | 69 | 3 | LivesExhausted |

Wszystkie cztery przebiegi zakończyły się bez wyjątków. Liczba kolizji, unikniętych przeszkód, utrat życia, poziom i terminal były identyczne. Score różnił się maksymalnie o 0,394, a końcowy czas gry o 0,090 s, ponieważ score i rozpoznanie końca nadal przechodzą przez granice Unity `Update`/`FixedUpdate`. Jest to jawna tolerancja niedeterministyczności runtime przyjęta dla pilota. Nie wystąpił sygnał zgubionej kolizji, dlatego wybrano najwyższe sprawdzone ustawienie: **timeScale 20**.

## Plan pilota

| Kohorta | Kontroler | Zbiór | Seedy | Max duration | timeScale |
| --- | --- | --- | ---: | ---: | ---: |
| Baseline | NoAction | TRAIN | 10 | 300 s | 20 |
| Development | RuleBasedV1 | TRAIN | 30 | 300 s | 20 |
| Validation | RuleBasedV1 | VALIDATION | 20 | 300 s | 20 |

Każda kohorta używa pierwszych zapisanych seedów swojego zbioru. Runner pilota nie pobierał TEST; żaden seed TEST nie został rozegrany ani użyty do doboru parametrów. Te same parametry zastosowano bez zmian dla TRAIN i VALIDATION. Wszystkie 60 epizodów zakończyły się przez `LivesExhausted`; żaden nie osiągnął odcięcia 300 s.

Trzy publiczne procesy Unity zakończyły się w łącznym czasie ściennym **418,950 s**, wraz z importem izolowanego projektu. Każdy zwrócił kod 0, utworzył dokładnie 10/30/20 rekordów CSV i nie zapisał wyjątku. Poniższe odchylenia standardowe są odchyleniami populacyjnymi dla całej wskazanej kohorty pilota.

## Wyniki

### NoAction — TRAIN, n=10

| Metryka | Mean | Median | Std | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| survivalTime | 13,570 | 12,030 | 4,422 | 10,800 | 26,401 |
| finalScore | 342,039 | 302,668 | 112,015 | 272,171 | 666,877 |
| lifeLossCount | 3,000 | 3,000 | 0,000 | 3 | 3 |
| collisionsTotal | 5,000 | 5,000 | 1,414 | 3 | 7 |
| obstaclesAvoided | 4,300 | 3,500 | 3,900 | 1 | 15 |
| maxLevel | 1,000 | 1,000 | 0,000 | 1 | 1 |
| heartsCollected | 0,000 | 0,000 | 0,000 | 0 | 0 |
| shieldsCollected | 0,000 | 0,000 | 0,000 | 0 | 0 |
| boostsCollected | 0,000 | 0,000 | 0,000 | 0 | 0 |
| goldCollected | 5,500 | 5,000 | 5,220 | 0 | 15 |
| diamondsCollected | 0,200 | 0,000 | 0,600 | 0 | 2 |
| turboActivations | 0,000 | 0,000 | 0,000 | 0 | 0 |

Rozkład terminali: `LivesExhausted` 10/10.

### RuleBasedV1 — TRAIN, n=30

| Metryka | Mean | Median | Std | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| survivalTime | 91,767 | 72,992 | 64,469 | 15,610 | 277,339 |
| finalScore | 3042,354 | 2107,302 | 2878,994 | 394,036 | 12293,223 |
| lifeLossCount | 3,867 | 3,500 | 1,118 | 3 | 7 |
| collisionsTotal | 5,800 | 5,000 | 3,229 | 3 | 18 |
| obstaclesAvoided | 78,467 | 56,500 | 67,561 | 7 | 287 |
| maxLevel | 3,600 | 3,000 | 2,951 | 1 | 13 |
| heartsCollected | 1,000 | 0,500 | 1,291 | 0 | 5 |
| shieldsCollected | 1,033 | 1,000 | 1,303 | 0 | 5 |
| boostsCollected | 0,867 | 0,000 | 1,408 | 0 | 5 |
| goldCollected | 43,567 | 31,500 | 39,714 | 0 | 179 |
| diamondsCollected | 0,600 | 1,000 | 0,611 | 0 | 2 |
| turboActivations | 0,633 | 0,000 | 0,948 | 0 | 4 |

Rozkład terminali: `LivesExhausted` 30/30.

### RuleBasedV1 — VALIDATION, n=20

| Metryka | Mean | Median | Std | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| survivalTime | 110,908 | 103,354 | 73,038 | 14,410 | 277,319 |
| finalScore | 3738,057 | 3105,487 | 2990,956 | 361,495 | 11658,671 |
| lifeLossCount | 4,450 | 4,000 | 1,431 | 3 | 8 |
| collisionsTotal | 7,150 | 5,500 | 4,126 | 3 | 18 |
| obstaclesAvoided | 98,650 | 87,500 | 75,223 | 7 | 283 |
| maxLevel | 4,100 | 3,500 | 2,931 | 1 | 12 |
| heartsCollected | 1,750 | 1,000 | 1,609 | 0 | 5 |
| shieldsCollected | 1,800 | 1,000 | 1,887 | 0 | 7 |
| boostsCollected | 0,800 | 0,500 | 0,980 | 0 | 3 |
| goldCollected | 51,600 | 42,500 | 39,085 | 0 | 159 |
| diamondsCollected | 0,700 | 0,000 | 1,308 | 0 | 4 |
| turboActivations | 0,750 | 0,500 | 0,887 | 0 | 3 |

Rozkład terminali: `LivesExhausted` 20/20.

Pilot ustanawia użyteczny deterministyczny baseline i weryfikuje pełną ścieżkę batch. Nie jest wnioskiem o przyszłej jakości PPO lub NEAT. Duży rozrzut między seedami powinien pozostać widoczny w późniejszych porównaniach per seed, zamiast ograniczenia raportu do samej średniej.

## Ograniczenia przed mostem treningowym

- Oryginalny score i część efektów nadal są aktualizowane w renderowanych klatkach. Przyszły bridge musi zdefiniować czas przejścia i zaakceptować zmierzoną małą tolerancję końca epizodu albo jawnie wersjonować bardziej rygorystyczną zmianę czasu.
- Observation v2 opisuje bieżące przecięcia orbity środka gracza. Nie uwzględnia całej bryły collidera gracza ani przyszłej obwiedni ruchomych przeszkód. `hasHazard` może wynosić 1 przy zerowym bieżącym occupancy.
- Launcher edytora obsługuje jedno środowisko na proces Unity. Standalone/headless, transport, back-pressure, odzyskiwanie po awarii i orkiestracja wielu procesów pozostają osobnymi decyzjami projektowymi.
- Adapter PPO musi osobno przekazać `terminated` i `truncated`, zdefiniować bootstrap wartości przy truncation oraz pobrać już domknięty decision reward bez podwójnego naliczenia terminalu.
- Pola metadanych uruchomienia i checkpointu istnieją w CSV, lecz bridge nie definiuje jeszcze ich właściciela ani trwałości.
