# UML Diagrams: MENTORX

Contents: [Class diagram](#1-class-diagram) · [Sequence diagrams](#2-sequence-diagrams) · [Activity diagrams](#3-activity-diagrams) · [State diagram](#4-state-diagram-study-session). The use case diagram is in [use-cases.md](../srs/use-cases.md); the ER diagram is in [database.md](database.md).

## 1. Class diagram

Domain entities (persisted) on the left, services and ML classes on the right. Attributes are abbreviated; the full columns are in the ER diagram.

```mermaid
classDiagram
  direction LR

  class User {
    +UUID id
    +str email
    +str role
    +int daily_goal
    +bool consent_research
    +str experiment_group
  }
  class Subject {
    +int id
    +str code
    +str name
  }
  class Concept {
    +int id
    +str code
    +str name
    +int topo_order
    +prerequisites() list~Concept~
  }
  class Question {
    +int id
    +str external_id
    +int version
    +str stem
    +dict options
    -str correct_key
    +int author_difficulty
    +float est_difficulty
    +is_correct(key) bool
  }
  class StudySession {
    +UUID id
    +SessionType type
    +SessionStatus status
    +int target_count
    +int answered_count
    +serve(question, p, model) void
    +accept_answer(question_id, key) Attempt
    +is_finished() bool
  }
  class Attempt {
    +int id
    +str selected_key
    +bool is_correct
    +int response_ms
    +int attempt_no
    +bool is_valid
    +float predicted_p_correct
  }
  class Mastery {
    +float p_mastery
    +float peak_mastery
    +int n_attempts
    +datetime last_attempt_at
  }
  class LearningPath {
    +UUID id
    +bool is_current
    +str trigger
    +items list~LearningPathItem~
  }
  class LearningPathItem {
    +int position
    +Reason reason
    +int target_difficulty
    +str explanation
  }
  class ModelVersion {
    +int id
    +str name
    +str model_type
    +dict metrics
    +bool is_active
  }

  User "1" --> "*" StudySession
  User "1" --> "*" Mastery
  User "1" --> "*" LearningPath
  Subject "1" *-- "*" Concept
  Concept "*" --> "*" Concept : prerequisite
  Concept "1" --> "*" Question
  StudySession "1" *-- "*" Attempt
  Attempt "*" --> "1" Question
  Mastery "*" --> "1" Concept
  Mastery "*" --> "1" ModelVersion
  LearningPath "1" *-- "1..5" LearningPathItem
  LearningPathItem "*" --> "1" Concept

  class KnowledgeModel {
    <<interface>>
    +version: ModelVersion
    +predict(history, question, at) float
    +predict_many(history, questions, at) list~float~
  }
  class LogisticKT
  class GradientBoostingKT
  class BayesianKT {
    +dict params_per_concept
  }
  class HeuristicKT {
    +smoothed concept accuracy
  }
  class FeatureBuilder {
    +build(history, question, at) FeatureVector
  }
  class ModelRegistry {
    +active() KnowledgeModel
    +activate(version_id) void
    -verify(artifact) bool
  }
  class QuizEngine {
    +start_session(user, subject, type, concept) StudySession
    +next_question(session) Question
    +submit_answer(session, question_id, key) AnswerResult
  }
  class QuestionSelector {
    +target_p: float
    +select(user, candidates, group) Selection
  }
  class MasteryService {
    +update_after(attempt) Mastery
    +current(user, concept) Mastery
  }
  class RecommendationEngine {
    +generate(user, subject, trigger) LearningPath
  }
  class RevisionScheduler {
    +due(user, subject) list~Concept~
  }
  class EngagementService {
    +classify_valid(attempt, recent) bool
    +streak(user) Streak
  }

  KnowledgeModel <|.. LogisticKT
  KnowledgeModel <|.. GradientBoostingKT
  KnowledgeModel <|.. BayesianKT
  KnowledgeModel <|.. HeuristicKT
  LogisticKT ..> FeatureBuilder
  GradientBoostingKT ..> FeatureBuilder
  ModelRegistry o-- KnowledgeModel
  QuizEngine --> QuestionSelector
  QuizEngine --> MasteryService
  QuizEngine --> EngagementService
  QuestionSelector --> KnowledgeModel
  MasteryService --> KnowledgeModel
  RecommendationEngine --> MasteryService
  RevisionScheduler --> MasteryService
  QuizEngine ..> StudySession
  MasteryService ..> Mastery
  RecommendationEngine ..> LearningPath
```

## 2. Sequence diagrams

### 2.1 Register and log in

```mermaid
sequenceDiagram
  actor S as Student
  participant FE as Frontend
  participant R as /auth router
  participant A as AuthService
  participant P as PilotService
  participant DB as PostgreSQL

  S->>FE: Fill in register form
  FE->>R: POST /auth/register {name, email, password, privacy_accepted}
  R->>R: Validate (Pydantic)
  R->>A: register(...)
  A->>DB: SELECT user by email (citext)
  alt email exists
    A-->>R: EmailTaken
    R-->>FE: 409 email_taken
  else new
    A->>A: hash password (Argon2id)
    A->>P: assign_group() if pilot active
    A->>DB: INSERT user
    A->>A: create access JWT + refresh token
    A->>DB: INSERT refresh_tokens (sha256 hash)
    A-->>R: tokens
    R-->>FE: 201 {access_token} + Set-Cookie refresh (HttpOnly)
    FE-->>S: Onboarding
  end

  Note over FE,R: Later, the access token expires
  FE->>R: POST /auth/refresh (cookie)
  R->>A: rotate(refresh)
  A->>DB: revoke old, insert new (one transaction)
  R-->>FE: 200 {access_token} + new cookie
```

### 2.2 Answer a question (adaptive practice)

```mermaid
sequenceDiagram
  actor S as Student
  participant FE as Frontend
  participant Q as QuizEngine
  participant Sel as QuestionSelector
  participant KM as KnowledgeModel
  participant M as MasteryService
  participant E as EngagementService
  participant DB as PostgreSQL

  FE->>Q: POST /sessions/{id}/next
  Q->>DB: lock session, load candidates + exclusions
  Q->>Sel: select(user, candidates, group)
  Sel->>KM: predict_many(history, candidates, now)
  KM-->>Sel: [p1, p2, ...]
  Sel-->>Q: question, p, model_version (random among top-3 closest to 0.65)
  Q->>DB: UPDATE session SET current_question, served_at, predicted_p
  Q-->>FE: question (stem + options, no key)
  S->>FE: Picks option B
  FE->>Q: POST /sessions/{id}/answer {question_id, "B"}
  Q->>DB: BEGIN, then SELECT session FOR UPDATE
  alt question_id != current_question_id
    Q-->>FE: 409 session_question_mismatch
  else ok
    Q->>Q: is_correct, response_ms = now - served_at
    Q->>E: classify_valid(attempt, recent)
    Q->>DB: INSERT attempt (with predicted_p, model_version)
    Q->>M: update_after(attempt)
    M->>KM: predict(history, reference item, now)
    M->>DB: UPSERT mastery, INSERT snapshot
    Q->>DB: clear current_*, answered_count++, COMMIT
    Q-->>FE: {correct, correct_key, explanation, mastery before/after}
  end
```

### 2.3 Complete the diagnostic and generate the first path

```mermaid
sequenceDiagram
  actor S as Student
  participant FE as Frontend
  participant Q as QuizEngine
  participant M as MasteryService
  participant Rec as RecommendationEngine
  participant DB as PostgreSQL

  loop one diagnostic question per concept (topological order)
    FE->>Q: next, then answer (as in 2.2, but no feedback shown)
  end
  Q->>DB: session completed, enrollment.diagnostic_completed_at = now
  Q->>M: ensure mastery for all concepts (cold-start prior if unanswered)
  Q->>Rec: generate(user, subject, trigger="diagnostic")
  Rec->>M: current(user, concept) for all concepts
  Rec->>Rec: walk DAG, apply rules, rank, top 5
  Rec->>DB: mark old path not current, INSERT new path and items
  Q-->>FE: summary {strong, weak, first recommendation}
```

### 2.4 Train, register and activate a model (offline)

```mermaid
sequenceDiagram
  actor Dev as ML developer
  participant Scr as ml/scripts
  participant Rep as reports/
  participant Art as artifacts/
  participant Adm as /admin/models
  participant Reg as ModelRegistry
  participant DB as PostgreSQL

  Dev->>Scr: download.py, clean.py (public data or pilot export)
  Dev->>Scr: train.py --config configs/gbm.yaml
  Scr->>Scr: student-level split, fit on train, tune on val
  Dev->>Scr: evaluate.py
  Scr->>Rep: metrics table, reliability plot, CIs
  Dev->>Dev: review report, choose by pre-registered rule
  Scr->>Art: model.joblib + metadata.json (features, sha256, metrics)
  Dev->>Adm: POST register + activate
  Adm->>Reg: activate(version)
  Reg->>Reg: load, verify hash + feature names, benchmark latency
  alt verification fails
    Reg-->>Adm: 422, previous version stays active
  else ok
    Reg->>DB: set is_active
    Reg-->>Adm: 200
  end
```

## 3. Activity diagrams

### 3.1 Practice session

```mermaid
flowchart TD
  A([Start practice]) --> B{Active session exists?}
  B -- yes --> C[Resume session]
  B -- no --> D[Create session<br/>type, focus concept or path]
  C --> E
  D --> E[Build candidate set]
  E --> F{Any eligible candidates?}
  F -- no --> G[Fallback: least recently seen<br/>log content_exhausted]
  F -- yes --> H{Experiment group}
  H -- adaptive --> I[Predict p for each candidate<br/>pick random among 3 closest to 0.65]
  H -- control --> J[Pick uniformly at random]
  G --> K
  I --> K[Store served question, p, model version, time]
  J --> K
  K --> L[/Student answers/]
  L --> M{Answer matches served question?}
  M -- no --> N[409 conflict] --> L
  M -- yes --> O[Store attempt<br/>correctness, response time, validity]
  O --> P[Update mastery + snapshot]
  P --> Q[Update goal progress / streak]
  Q --> R[Show feedback + explanation + mastery change]
  R --> S{answered = target<br/>or student ends?}
  S -- no --> E
  S -- yes --> T[Close session]
  T --> U[Regenerate learning path]
  U --> V([Session summary])
```

### 3.2 Learning path generation

```mermaid
flowchart TD
  A([Trigger: diagnostic / session end / revision due]) --> B[Load mastery for all concepts<br/>recompute stale ones]
  B --> C[Collect due revisions:<br/>peak ≥ 0.8 and current < 0.6]
  C --> D[For each concept in topological order]
  D --> E{mastery < 0.6 or never attempted?}
  E -- no --> D
  E -- yes --> F{All prerequisites ≥ 0.6?}
  F -- yes --> G[Candidate: weak if attempted, new otherwise]
  F -- no --> H[Candidate: weakest unmet prerequisite<br/>reason = prerequisite]
  G --> D
  H --> D
  D -- done --> I[Rank: revision > prerequisite > weak > new,<br/>then lowest mastery, then topological order]
  I --> J[De-duplicate, keep top 5]
  J --> K[Target difficulty from mastery band:<br/>&lt;0.4 → 1, 0.4–0.7 → 2, ≥0.7 → 3]
  K --> L[Write explanation per item]
  L --> M[Mark old path not current, save new path]
  M --> N([Path ready])
```

## 4. State diagram: study session

```mermaid
stateDiagram-v2
  [*] --> Active: start_session
  state Active {
    [*] --> AwaitingServe
    AwaitingServe --> AwaitingAnswer: next_question (store served q, p, time)
    AwaitingAnswer --> AwaitingServe: submit_answer (attempt stored)
    AwaitingAnswer --> AwaitingAnswer: mismatched answer (409)
  }
  Active --> Completed: answered_count = target_count
  Active --> Completed: student ends
  Active --> Abandoned: inactive > 24 h
  Completed --> [*]
  Abandoned --> [*]
```
