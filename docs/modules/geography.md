# Geography: map skills (Slepemapy.cz)

The second v3 subject. Students find and name countries, cities, rivers, mountains and islands on
six maps. Everything below comes from scripts that ran; the numbers are copied from their output
(`backend/model_artifacts/geography/kt_meta.json` holds the model's).

## Source and licences

| What | Source | Licence | Where it lives |
|---|---|---|---|
| Answers (training data) | Slepemapy.cz "Adaptive Geography Practice" data set, 2015-05-21 release, Adaptive Learning group, Masaryk University | Open Database License 1.0; contents Database Contents License 1.0 | Never committed. Local copy: `C:/Users/Tanish Gupta/Downloads/mentorx-new-subject/slepemapy-2015-05-21/` |
| Place names | `place.csv` from the same data set | same | read by the seed at seeding time |
| Map outlines | SVG maps of the open-source slepemapy app, github.com/adaptive-learning/geography | MIT, (c) 2013 Vit Stanislav | derived, code-free JSON in `frontend/public/maps/` and `backend/app/tutor/seeddata/geography/` |

Citation (the data set asks for it): Papoušek, J., Pelánek, R., & Stanislav, V. (2016). Adaptive
Geography Practice Data Set. *Journal of Learning Analytics*, 3(2), 317-321.
https://doi.org/10.18608/jla.2016.32.17

Attribution shown in the app (subject card, Skill page footer, Profile -> Data & credits), from
`app/tutor/subjects.py`: "Geography practice data © Adaptive Learning group, Masaryk University
(slepemapy.cz), Open Database License 1.0. Papoušek, Pelánek & Stanislav (2016), Adaptive Geography
Practice Data Set, Journal of Learning Analytics 3(2). Map outlines: adaptive-learning/geography,
MIT licence, © 2013 Vít Stanislav." The MIT text ships in `frontend/public/maps/LICENSE.txt` and
`backend/app/tutor/seeddata/geography/LICENSE.txt`; the ODbL notice in
`backend/model_artifacts/geography/NOTICE.txt`. If we ever publish an adapted database, it must be
released under the ODbL too.

Disclaimer shown under every map: "Maps are simplified for practice and do not show official
international boundaries."

## Scope and exclusions

- **Maps shipped (6):** Europe, Africa, South America, North America, Oceania, United States.
  **Not shipped:** World, Asia, India, China and every regional map. The World/Asia/India/China maps
  draw India's borders; we cannot verify them, and an incorrect depiction is a real problem for our
  audience.
- **Vetting** (`ml/scripts/build_geography_maps.py` refuses a map otherwise): no element of a
  shipped map has a South Asian code (in, pk, cn, np, bt, bd, mm, lk, af) as `data-code` or
  `data-state-code`; every base map was rendered to PNG and looked at (no South Asia anywhere), and
  three random places per map were drawn over it to prove the outlines line up.
- **Never asked, never offered as an option** (disputed status): Kosovo, Western Sahara,
  Somaliland, Falkland Islands, and the cities in them that the maps contain: Pristina, Bir Lehlou,
  Laayoune (tagged Morocco in the source map, but in Western Sahara) and Hargeysa. They are still
  drawn as plain land, with no highlight. They have no entry in the geometry files and the seed
  filters them again.
- **Names:** the 2015 data abbreviates some names and predates renames. `names.yaml` fixes them
  (North Macedonia, Eswatini, Kyiv, Democratic Republic of the Congo, ...). One dataset place is two
  different cities: San José (Costa Rica) on the North America map, San Jose (California) on the US map.

## Skills and questions

A skill is (map, place type). It ships only with **at least 6 askable places** and **at least 1,000
dataset answers** on askable places. All 16 candidates passed:

| Skill id | Code | Name | Places | Questions | Dataset answers |
|---|---|---|---|---|---|
| 1000101 | `GEO.EU.COUNTRY` | Countries of Europe | 38 | 76 | 1,673,450 |
| 1000102 | `GEO.EU.CITY` | Cities of Europe | 43 | 86 | 373,886 |
| 1000105 | `GEO.EU.RIVER` | Rivers of Europe | 28 | 56 | 230,466 |
| 1000108 | `GEO.EU.MOUNTAINS` | Mountains of Europe | 25 | 50 | 198,252 |
| 1000109 | `GEO.EU.ISLAND` | Islands of Europe | 20 | 40 | 122,058 |
| 1000201 | `GEO.AF.COUNTRY` | Countries of Africa | 49 | 98 | 711,283 |
| 1000202 | `GEO.AF.CITY` | Cities of Africa | 56 | 112 | 97,828 |
| 1000205 | `GEO.AF.RIVER` | Rivers of Africa | 10 | 20 | 107,381 |
| 1000301 | `GEO.SA.COUNTRY` | Countries and territories of South America | 13 | 26 | 204,504 |
| 1000302 | `GEO.SA.CITY` | Cities of South America | 15 | 30 | 68,879 |
| 1000401 | `GEO.NA.COUNTRY` | Countries and territories of North America | 18 | 36 | 180,796 |
| 1000402 | `GEO.NA.CITY` | Cities of North America | 34 | 68 | 48,839 |
| 1000501 | `GEO.OC.COUNTRY` | Countries and territories of Oceania | 7 | 14 | 58,354 |
| 1000502 | `GEO.OC.CITY` | Cities of Oceania | 11 | 22 | 30,918 |
| 1000602 | `GEO.US.CITY` | Cities of the United States | 50 | 100 | 65,612 |
| 1000607 | `GEO.US.STATE` | US states | 48 | 96 | 558,932 |
| | | **Total** | **465** | **930** | **4,731,438** |

The 4,731,438 answers are those on askable places of the six shipped maps (4,831,402 answers in
total on those maps). Difficulty of the 930 questions: 492 easy, 428 medium, 9 hard, 1 unrated.
Locate questions read "Where is France?", "Where is the river Niger?", "Where are the Alps?".

Each place gives two questions, both multiple choice with options A-D:

- **name_place** (dataset type 2): "What is the name of the highlighted country?" One region is
  highlighted; the options are four place names.
- **locate_place** (dataset type 1): "Where is France? Choose the letter on the map." Four regions are
  lettered A-D; tapping a letter on the map picks that option.

Distractors are the same-skill places that students most often gave instead of the right answer
(`question_stats.json`, all answers on the shipped maps), then random same-skill places (fixed seed).
In locate questions every two lettered places are at least 6 % of the map width apart. Options are
shuffled once, at seed time, with a fixed seed. Difficulty uses the Maths thresholds on the training
students' success rate (easy >= 0.75, medium >= 0.45, else hard; unrated under 10 answers).

**No leaks.** The base maps (`frontend/public/maps/<map>.json`) are outlines only: no codes, names or
ids. A question's `media` holds just its regions' outlines, anchors, shapes and letters, listed in
letter order; the key is an option id in `items.answer_key` (server only).

**IDs** (no collision with Maths; the seed checks): skill = 1,000,000 + map x 100 + place type
(Europe 1, Africa 2, South America 3, North America 4, Oceania 5, US 6); item = 100,000,000 +
place id x 100 + map x 2 + direction (0 name, 1 locate).

**Notes:** one short notes resource per skill (`resources_geography.yaml`), our own text, labelled
"AI-assisted, pending teacher review", no links. No worked examples or videos.

## The model

Same DKT-Q architecture and input convention as Mathematics (served by the same NumPy code,
`app/ml/dkt.py`), trained separately by `ml/scripts/train_geography_kt.py`
(config `ml/configs/geography.yaml`):

- Question id = the item id above; skill id as above; label = the answered place is the asked place
  ("I don't know" is wrong); hints and saw-answer are 0; the time gap comes from `inserted`.
- Answers on askable places of the 16 skills only.
- Split by student 70/15/15 (seed 42). **CPU budget:** a seeded random sample of students, each
  student's first answers only (exact numbers below). Early stopping on validation log loss.
- Baseline: each question's success rate among training students (the global rate for questions
  they never saw), evaluated on exactly the same test predictions.

**Run of 2026-11-13** (`kt_meta.json`; log in `ml/artifacts/geography/train_log.txt`, not committed):

- Sample: 30,000 of 54,399 students with at least 2 askable answers (seeded random sample, CPU
  budget); each student's first 500 answers. Rows: 1,647,247 train, 344,135 validation,
  341,761 test (20,999 / 4,500 / 4,501 students).
- 580,004 parameters; 930 question ids, 16 skills. Early stopping after epoch 6; the best epoch (4)
  is exported.
- NumPy parity with PyTorch (`app/ml/dkt.py`, 20 validation + 20 test students, plus
  the stateful `state()` + `predict_questions()` path for 5 test students): max |difference| = **1.47e-07** (limit 1e-5).

| Test set: 337,260 predictions for 4,501 held-out students | AUC (95% CI, bootstrap by student) | Accuracy | Log loss | Brier | ECE |
|---|---|---|---|---|---|
| **DKT-Q** | **0.776** (0.772-0.780) | 0.793 | 0.442 | 0.143 | 0.007 |
| Baseline: per-question training success rate | 0.633 (0.627-0.639) | 0.778 | 0.510 | 0.166 | 0.003 |

Validation: DKT-Q AUC 0.778, baseline 0.628. The model is better than the per-question baseline
because it uses each student's own history; accuracy is close because most answers are correct
(the baseline already reaches 0.778).

**Caveats (not hidden):** the source app mixed open map clicks with 2-6 option questions (type 2
questions were almost always multiple choice, type 1 mostly open clicks), and its users were mostly
Czech and Slovak students in 2013-2015. MENTORX serves 4-option questions, so predictions are only
approximately calibrated. Observed answers always decide a student's skill status; the admin model
monitor (`?subject=GEO`) shows live calibration. Facts are recall (where is X), not conceptual
geography, and the skills are not mapped to any curriculum.

## How to rebuild

```powershell
# 1. map assets (needs the six SVGs from github.com/adaptive-learning/geography, geography/static/map/)
python -I ml/scripts/build_geography_maps.py --svg-dir <folder with europe.svg, africa.svg, ...>
# 2. model (needs torch; about an hour on a laptop CPU)
python -I ml/scripts/train_geography_kt.py --data-dir "C:/Users/Tanish Gupta/Downloads/mentorx-new-subject/slepemapy-2015-05-21"
# 3. seed (local DB, or production with DATABASE_URL set)
cd backend; python scripts/seed_geography.py --data-dir "C:/Users/Tanish Gupta/Downloads/mentorx-new-subject/slepemapy-2015-05-21"
```

The seed is idempotent, keeps admin edits, never touches Mathematics, and needs only `place.csv` from
the data folder. Tests: `backend/tests/test_geography_seed.py` (synthetic fixture in
`backend/tests/fixtures/geo_mini/`).
