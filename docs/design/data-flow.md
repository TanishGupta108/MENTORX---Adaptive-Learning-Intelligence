# Data Flow Diagrams: MENTORX

Notation (Gane–Sarson style, drawn with Mermaid): rectangles = external entities, rounded boxes = processes, cylinders = data stores, arrows = data flows.

## Level 0: context diagram

```mermaid
flowchart LR
  Student[Student]
  Admin[Admin / ML developer]
  Datasets[Public KT datasets<br/>ASSISTments, EdNet]

  P0((0<br/>MENTORX))

  Student -- "registration, login, answers, settings, feedback" --> P0
  P0 -- "questions, feedback, mastery, learning path,<br/>revision queue, dashboard, streaks" --> Student
  Admin -- "question bank YAML, model artifacts, activation" --> P0
  P0 -- "pilot metrics, pseudonymised export, flags" --> Admin
  Datasets -- "historical interaction logs" --> P0
```

## Level 1

```mermaid
flowchart TB
  Student[Student]
  Admin[Admin / ML developer]
  Datasets[Public KT datasets]

  P1(["1.0 Authenticate & manage profile"])
  P2(["2.0 Load content"])
  P3(["3.0 Select & serve question"])
  P4(["4.0 Record attempt"])
  P5(["5.0 Estimate mastery"])
  P6(["6.0 Generate learning path"])
  P7(["7.0 Compute revision & engagement"])
  P8(["8.0 Report analytics"])
  P9(["9.0 Train & evaluate model (offline)"])

  D1[("D1 Users & tokens")]
  D2[("D2 Subjects, concepts, questions")]
  D3[("D3 Sessions")]
  D4[("D4 Attempts (raw)")]
  D5[("D5 Mastery & snapshots")]
  D6[("D6 Learning paths")]
  D7[("D7 Model versions & artifacts")]
  D8[("D8 Feedback & flags")]

  Student -- credentials, profile --> P1
  P1 -- tokens, profile --> Student
  P1 <--> D1

  Admin -- question bank YAML --> P2
  P2 -- validated content --> D2

  Student -- start / next --> P3
  D2 -- candidate questions --> P3
  D4 -- history & exclusions --> P3
  D7 -- active model --> P3
  P3 -- served question, p, time --> D3
  P3 -- question without key --> Student

  Student -- selected option --> P4
  D3 -- served state --> P4
  D2 -- answer key --> P4
  P4 -- attempt --> D4
  P4 -- correctness, explanation --> Student

  D4 -- concept history --> P5
  D7 -- active model --> P5
  P5 -- mastery, snapshot --> D5

  D5 -- mastery --> P6
  D2 -- prerequisite DAG --> P6
  P6 -- path --> D6
  D6 -- recommendations --> Student

  D5 -- mastery, peaks --> P7
  D4 -- valid answers per day --> P7
  P7 -- revision queue, streak --> Student

  D4 & D5 & D6 -- stored data --> P8
  P8 -- dashboard --> Student
  P8 -- pilot metrics --> Admin
  Student -- feedback, flags --> D8
  D8 -- feedback --> P8

  Datasets -- logs --> P9
  D4 -- pseudonymised export (consented) --> P9
  P9 -- artifact, metrics --> D7
  P9 -- evaluation report --> Admin
```

## Level 2: 5.0 Estimate mastery

```mermaid
flowchart LR
  D4[("D4 Attempts")]
  D2[("D2 Questions")]
  D7[("D7 Active model")]
  D5[("D5 Mastery")]

  P51(["5.1 Load concept history<br/>(attempts before now)"])
  P52(["5.2 Build features<br/>(shared FeatureBuilder)"])
  P53(["5.3 Predict P(correct)<br/>on reference item"])
  P54(["5.4 Update mastery,<br/>peak & snapshot"])

  D4 --> P51
  D2 -- concept, difficulty --> P51
  P51 -- ordered history --> P52
  P52 -- feature vector --> P53
  D7 -- model --> P53
  P53 -- p_mastery, version --> P54
  P54 --> D5
```

## Data dictionary (key flows)

| Flow | Contents |
|---|---|
| answers | `session_id, question_id, selected_key \| null` |
| served question | `question_id, stem, options (A–D)`, no key or explanation |
| attempt | `user, session, question, selected_key, is_correct, response_ms, attempt_no, is_valid, predicted_p, model_version, created_at` |
| concept history | ordered attempts of one user on one concept: `is_correct, created_at, question difficulty, attempt_no` |
| feature vector | prior attempts/correct on concept, smoothed accuracy, last-k correctness, log time since last (concept/any), overall accuracy, question difficulty, attempt_no |
| pseudonymised export | `sha256(user_id + salt), question external_id, concept code, difficulty, is_correct, response_ms, attempt_no, created_at` |
