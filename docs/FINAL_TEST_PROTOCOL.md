# Turbo Dash — zamrożony protokół końcowego TEST

Status przed wykonaniem: modele i protokół zamrożone, `test.json` nieodczytany, liczba wykonanych epizodów TEST: 0.

## Rozdzielenie faz

1. Dobór modeli został zakończony wyłącznie na istniejących wynikach VALIDATION z limitem 500 s. Zamrożenie zapisano w `Training/final_test/final_model_selection.json` wraz ze ścieżkami, SHA-256, wersjami konfiguracji i commitami źródłowych treningów.
2. Preflight sprawdza czyste Git, kompletność i hashe modeli, zgodność konfiguracji, deterministyczne wczytanie polityk, build workera oraz handshake protokołu. Na tym etapie `test.json` nie jest otwierany.
3. Dopiero po udanym preflight skrypt otwiera TEST, sprawdza 200 unikalnych dodatnich ziaren i brak przecięcia z TRAIN/VALIDATION, tworzy jeden deterministyczny harmonogram i rozpoczyna epizody.
4. Do chwili zapisania 3000 poprawnych epizodów proces pozostaje zaślepiony: pokazuje tylko postęp, zdrowie workerów, liczbę retry i ETA. Nie oblicza ani nie pokazuje wyników metod.
5. Po komplecie danych następuje automatyczne odślepienie i analiza według poniższego planu. Nie wykonuje się ponownego wyboru modelu.

## Zamrożone metody

| Metoda | Zamrożony artefakt | Podstawa wyboru |
|---|---|---|
| RuleBasedV1 | `RuleBasedController.cs`, parametry domyślne | jedyny finalny deterministyczny baseline protokołu v1 |
| PPO-D | run 3, checkpoint 3 000 000 | najwyższa średnia `finalScore` VALIDATION 500: 74 890,256 |
| PPO-C | run 3, checkpoint 2 000 004 (etykieta 2M) | najwyższa średnia VALIDATION 500: 72 340,235 |
| NEAT-D | v2 run 3, generacja 141, genome 8134 | najwyższa średnia VALIDATION 500: 39 742,598 |
| NEAT-C | run 1, generacja 62, genome 3390 | najwyższa średnia VALIDATION 500: 63 393,311 |

RuleBasedV1 nie ma istniejącego artefaktu VALIDATION 500. Nie uruchomiono dodatkowej walidacji podczas zamrażania; luka generalizacji tej metody będzie jawnie oznaczona jako niedostępna. Adapter Pythona jest portem inferencyjnym niezmienionego algorytmu C#: zachowuje jego parametry, układ Observation v2, stan `previousAction`, regułę remisów i obliczenia float32, a jego akcje są faktycznie wysyłane przez ten sam most co pozostałe polityki.

## Wykonanie TEST

- `MaxDuration=500`, 200 ziaren TEST, 3 powtórzenia, 5 metod.
- Dokładnie 600 epizodów na metodę i 3000 łącznie.
- Metody są uruchamiane sekwencyjnie: RuleBasedV1, PPO-D, PPO-C, NEAT-D, NEAT-C.
- Wewnątrz metody działa dokładnie 6 workerów Unity, `timeScale=20`.
- Wszystkie metody otrzymują identyczny harmonogram 600 par `(seed, repetition)`, tasowany raz przez `schedule_random_seed=20260930`.
- Inferencja jest deterministyczna. Protokół gry pozostaje bez zmian: Research Protocol v1, Observation v2/236, `fixedDeltaTime=0.01`, decyzja co 0,05 s.
- Klucz wznowienia to `(method, seed, repetition)`. Zakończony klucz nie jest wykonywany ponownie.
- Surowy CSV jest synchronizowany po każdym epizodzie, a progress JSON zapisywany atomowo.
- Błąd techniczny powoduje restart puli i maksymalnie 2 retry danego klucza. Trzeci błąd zatrzymuje eksperyment bez zastępowania obserwacji.

## Telemetria akcji

Dla metod dyskretnych zapisywane są liczby i udziały LEFT/NONE/RIGHT. Dla ciągłych zapisywane są średnia, średnia wartość bezwzględna, odchylenie, udziały `|steering|<0.1`, `|steering|>0.9`, `steering<-0.1`, `steering>0.1` oraz histogram 40 równych przedziałów na `[-1,1]`. Dla wszystkich metod zapisywana jest częstotliwość zmiany akcji. Wszystkie udziały są normalizowane liczbą decyzji, nie długością epizodu.

## Zamrożona analiza

Metryką główną jest `finalScore`, a jednostką analizy seed. Najpierw trzy powtórzenia są uśredniane osobno dla każdej pary metoda–seed, co daje 200 sparowanych obserwacji na metodę.

- Test omnibus: Friedman, α=0,05.
- Tylko gdy Friedman jest istotny: wszystkie 10 sparowanych testów Wilcoxona i korekta Holma dla jednej rodziny.
- Każda para: średnia i mediana różnic, sparowany bootstrap 95% CI po seedach (20 000 replik, seed 20261001) oraz sparowany rank-biserial effect size.
- Jednoznaczny zwycięzca musi mieć najwyższą średnią i być istotnie lepszy od każdej pozostałej metody po korekcie Holma. W przeciwnym razie raport mówi „brak jednoznacznego zwycięzcy” i podaje nierozdzielny zbiór czołowy.
- Dodatkowe wyniki: przeżycie Kaplan–Meier (`LivesExhausted` = zdarzenie, `MaxDuration` = cenzorowanie), przyczyny końca, kolizje, utraty życia, uniki, poziom, bonusy, waluta, turbo, rozrzut trzech powtórzeń i opisowa luka VALIDATION 500 → TEST.
- Analiza przeżycia jest opisowa i nie zastępuje kryterium `finalScore`.

## Artefakty

Katalog `Training/final_test/` zawiera `raw/final_test_episodes.csv`, manifest wykonania, `test_schedule.json`, atomowy `final_test_progress.json`, wymagane tabele CSV, `analysis/test_seed_difficulty.csv`, `final_test_results.json`, `FINAL_TEST_REPORT.md` i 15 wykresów PNG 300 dpi w `plots/`.

Jedynym punktem wejścia jest `Training/Start-FinalTestExperiment.ps1`. Parametr `-Resume` wznawia wyłącznie ten sam run po kontroli hashy protokołu, modeli, workera, TEST i harmonogramu. `-Workers` musi wynosić 6. `-RebuildWorker` jest opcjonalny.
