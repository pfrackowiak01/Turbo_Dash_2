# W5 — liczba gatunków względem generacji

Wykres zestawia trzy historyczne przebiegi NEAT-D v1 (`neat-discrete-5m-run1–3`) z trzema przebiegami NEAT-D v2 (`neat-discrete-v2-200g-run1–3`). Osobny, trzygeneracyjny pilot doboru parametrów v2 nie jest częścią tego zestawienia.

## Podpis do pracy

**W5. Liczba gatunków w kolejnych generacjach NEAT-D v1 i NEAT-D v2.** W konfiguracji v1 (`full_direct`, próg kompatybilności 3,0) we wszystkich trzech przebiegach utrzymywał się jeden gatunek. W konfiguracji v2 (`partial_direct 0,10`, próg 2,5) liczba gatunków wynosiła od 2 do 8. Krzywe v1 pokrywają się i kończą odpowiednio na generacjach 61, 63 i 58; przebiegi v2 obejmują po 200 generacji. Przedstawiono wartości `species_count` zapisane po zakończeniu generacji, bez wygładzania ani ekstrapolacji. Źródło: opracowanie własne na podstawie plików `generation_metrics.csv` sześciu przebiegów.

## Interpretacja i ograniczenia

Po zmianie konfiguracji utrzymało się więcej niż jedno skupienie genomów: przebiegi v2 zakończyły się odpowiednio z 2, 3 i 2 gatunkami. Dane nie uzasadniają stwierdzenia, że v2 utrzymywało stale 5–6 gatunków; taki zakres dotyczył krótkiego pilota specjacji, a nie całych przebiegów.

Inicjalizacja i próg kompatybilności zostały zmienione łącznie. Przebiegi v1/v2 mają też inne ziarna eksperymentu i warunki zatrzymania: około 5 mln przejść TRAIN w v1 oraz 200 generacji w v2. Wykres pokazuje zaobserwowaną różnicę między konfiguracjami, ale nie rozdziela przyczynowego wpływu każdego parametru ani nie jest porównaniem przy identycznym budżecie interakcji. Liczba gatunków sama w sobie nie jest miarą jakości sterowania.

W obu implementacjach `species_count` jest odczytywane po `population.run(..., 1)`, czyli po wykonaniu generacji wraz z reprodukcją/specjacją. Wersja v2 zapisuje dodatkowo `species_before`; wykres używa wspólnej obu wersjom metryki `species_count`.

## Pliki i odtworzenie

- `W5_neat_species.png`: obraz 300 dpi.
- `W5_neat_species.pdf`, `W5_neat_species.svg`: formaty wektorowe do składu pracy.
- `W5_neat_species.csv`: dokładne punkty wykresu (782 wiersze danych).
- `W5_neat_species.json`: konfiguracje, statystyki i SHA-256 źródłowych metryk oraz konfiguracji.
- `Training/plot_w5_neat_species.py`: generator oparty na Matplotlib; nie importuje modułów treningowych ani nie uruchamia Unity.

Uruchomienie z katalogu głównego projektu:

```powershell
.\Training\.venv\Scripts\python.exe .\Training\plot_w5_neat_species.py
```

Generator sprawdza ciągłość numerów generacji, zakres liczby gatunków, konfiguracje inicjalizacji i progu oraz kompletność przebiegów v2. Dla v2 weryfikuje też zgodność `species_count` z `species_before` kolejnej generacji. Odczytuje wyłącznie metryki i konfiguracje sześciu wskazanych przebiegów; nie odczytuje plików katalogów seedów ani danych TEST.
