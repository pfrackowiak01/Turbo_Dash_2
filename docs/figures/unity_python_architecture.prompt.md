# Schemat Unity–Python do pracy magisterskiej

Plik: `unity_python_architecture.png`.

Generator: wbudowane narzędzie `image_gen`, za pośrednictwem umiejętności `imagegen`. Nowy obraz, następnie jedna korekta czytelności.

Proponowany podpis: „Architektura środowiska badawczego Turbo Dash: komunikacja Unity–Python, algorytmy PPO i NEAT oraz walidacyjny wybór modelu”.

## Zakres i weryfikacja

Schemat przedstawia architekturę na poziomie odpowiedzialności komponentów. Sprawdzono wizualnie czytelność napisów, kierunki TCP oraz kolejność kandydat → VALIDATION → najlepszy model, w odniesieniu do implementacji i dokumentacji projektu. Nie wykonywano kompilacji ani eksperymentów przy przygotowaniu ilustracji.

- Python wysyła RESET i STEP; Unity zwraca obserwacje i wyniki.
- Etykieta „6 workerów w sesji” dotyczy puli jednej sesji; nie określa całkowitej liczby procesów podczas okresowej walidacji PPO.
- Wspólna strzałka wyników zbiorczo opisuje odpowiedzi protokołu. RESET_RESULT zawiera początkową obserwację; STEP_RESULT zawiera obserwację, nagrodę, osobne flagi terminated/truncated i metryki.
- PPO i NEAT są alternatywnymi wariantami eksperymentu. Walidacja służy selekcji modelu.
- Pas artefaktów zbiera wyjścia całego eksperymentu, w tym treningu i walidacji; jego położenie nie oznacza, że wszystkie pliki powstają dopiero po walidacji.
- Rysunek pomija szczegóły implementacji adapterów i handshake'u. Częstotliwości odnoszą się do czasu gry.

## Prompt początkowy

```text
Use case: scientific-educational.
Create a NEW original publication-quality Polish software architecture diagram for a master's thesis about Turbo Dash, a Unity endless-runner environment controlled by Python PPO and NEAT. Generate the actual polished diagram image. Landscape composition approximately 3:2, very high resolution. Pure white background, precise flat vector-like geometry, sober academic visual design, navy typography, pale blue Python grouping, pale teal Unity grouping, muted amber validation grouping. No decorative illustrations, shadows, gradients, logos, or watermark. Large exceptionally sharp Polish text with correct diacritics. The goal is effortless comprehension on a printed thesis page. Sparse structure, generous whitespace, no crossing connectors.

LAYOUT:
The upper two thirds contain PYTHON ON THE LEFT, a spacious TCP communication gap in the middle, and UNITY ON THE RIGHT. The lower third is a separate horizontal Python model-selection strip, and a slim artifacts strip below it. No oversized overall title and no figure number or caption embedded.

UPPER LEFT GROUP header exactly "Python — sterowanie eksperymentem".
Inside show two small sibling cards:
"PPO" with second line "uczenie polityki";
"NEAT" with second line "ewolucja populacji".
Above or below these two cards place "Warianty alternatywne".
These are alternative algorithms, not sequential steps or concurrent cooperating agents.
Below them a single wide card:
"Orkiestrator"
"seedy TRAIN / VALIDATION"
"uruchamianie i zamykanie workerów".
Connect the algorithms to the orchestrator with a minimal two-way logical interaction connector, showing actions and returned observations, without crossing any text.

UPPER RIGHT GROUP header exactly "Unity — symulacja gry".
Use one representative worker container with two slightly offset thin outlines behind it to suggest replicated independent processes; a clear small badge "6 workerów w sesji". This count describes a worker session, NOT a guarantee of six total operating-system processes across training and validation.
Within the front worker, header "Research Worker".
Then "Scena: DeafultLevel" (the unusual spelling DeafultLevel is intentional: D e a f u l t L e v e l; preserve exactly).
Within the worker show two clearly distinguished internal panels, not a long fake sequential pipeline:
"Gra i fizyka" / "ruch, kolizje, generowanie trasy"
and "Research Mode" / "reset i zastosowanie akcji" / "Observation v2: 236 × float32" / "nagroda i metryki epizodu".
Research Mode and gameplay are components within the SAME worker and scene.
A modest footer in this Unity grouping: "Fizyka: 100 Hz • decyzje: 20 Hz" and on the next line "częstotliwości w czasie gry".
A separate nearby small label "Niezależne procesy Unity".

TCP GAP:
Heading "Lokalne TCP".
Exactly TWO primary horizontal directed arrows connect the Python orchestrator to the Unity worker.
The upper blue arrow points RIGHT, from Python on the LEFT to Unity on the RIGHT. Its labels, on two readable lines:
"RESET(seed)"
"STEP(action)"
The lower teal arrow points LEFT, from Unity on the RIGHT back to Python on the LEFT. Its readable labels:
"RESET_RESULT: obserwacja"
"STEP_RESULT: obserwacja, nagroda,"
"terminated, truncated, metryki"
Place labels around arrows with enough clearance. Arrowheads must visibly terminate at the receiving group boundary. Never reverse the arrowheads. The return flags must be separated terminated and truncated, not done. RESET_RESULT carries only initial observation. Do not draw six repeated TCP rows.
Under the gap, if needed, a brief unobtrusive label "Jedno połączenie na workera".

LOWER HORIZONTAL MODEL SELECTION STRIP:
Header "Python — walidacja i wybór modelu".
Three clear boxes connected LEFT TO RIGHT by solid directional arrows:
1. "Kandydat PPO / NEAT"
2. "VALIDATION" / "100 seedów" / "średni finalScore"
3. "Najlepszy model" / "wybór według walidacji".
A clean downward connector from the upper Python algorithm area to the candidate box, routed outside text. Do not connect the training algorithms directly to the best-model box.
A readable explanatory line below these three boxes:
"Walidacja używa tego samego interfejsu Unity–Python."
This is a separate evaluation phase, not training on validation data.

BOTTOM ARTIFACT STRIP:
A compact full-width neutral light-gray rounded rectangle with bold label "Artefakty eksperymentu" and this exact content on one or two large readable lines:
"Checkpointy • wyniki CSV / JSON • manifesty i logi"
"TensorBoard: metryki PPO".
Link the Python workflow to this output strip using one simple downward save arrow, avoiding complex many-to-many arrows.

Constraints: render only the supplied labels, keep all Polish accents exact, no tiny paragraph text, no invented modules, no ML-Agents, no cloud, no neural-net clip art, no TEST in training or model selection, no physical-distance claims. Allow sensible line wrapping and balanced spacing but preserve correct directions, component boundaries, and selection criterion. Keep the design crisp, restrained, and suitable for an engineering master's thesis.
```

## Prompt korekty (finalna wersja)

```text
Edit the attached Polish academic architecture diagram. Preserve its overall composition, every main box, palette, polish, all correct existing text, all correct TCP arrow directions, and the bottom validation/selection strip. Improve ONLY the following two local clarity issues; otherwise keep everything unchanged.

1. In the Python group, between the two algorithm cards and the Orkiestrator card, remove the current two single-headed arrows and ALL existing text in that space, including "akcje (konfiguracja, start, stop)" and "obserwacje (wyniki, metryki)". Replace with exactly TWO SEPARATE VERTICAL DOUBLE-HEADED arrows: one directly connecting the PPO card bottom center to the Orkiestrator top underneath PPO; the other directly connecting the NEAT card bottom center to the same Orkiestrator top underneath NEAT. Both algorithms therefore exchange actions AND observations independently with the common orchestrator. Place exactly one large readable label centered between these two connectors, on two lines:
"akcje"
"obserwacje i wyniki"
No words configuration/start/stop here and no third connector. Do not move the rest of the Python group.

2. In the narrow TCP gap, keep the blue arrow pointing RIGHT (Python to Unity), and keep the teal arrow pointing LEFT (Unity to Python). Preserve blue labels "RESET(seed)" and "STEP(action)". Replace the overly condensed text beneath the teal arrow with these exact three short lines in a normal-width sans-serif font large enough to read:
"obserwacje i nagroda"
"zakończenie / limit"
"metryki epizodu"
This is a high-level summary of return data across response messages. Remove the long RESET_RESULT and STEP_RESULT labels entirely to make the illustration readable. Keep "Jedno połączenie na workera" beneath the TCP gap.

Retain all other original text, including intentional scene spelling "DeafultLevel", "236 × float32", alternative PPO/NEAT, the 100-seed validation and best-model criterion. Preserve the wide white-margin landscape image. Crisp precise publication-style typography, high-resolution PNG, no new elements or watermarks.
```

