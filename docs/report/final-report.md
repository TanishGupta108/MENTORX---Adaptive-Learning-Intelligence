# MENTORX: An Adaptive Learning Platform for Machine Learning Driven by Knowledge Tracing

**Final project report** · Team MENTORX · November 2026
Live system: https://mentorx-adaptive-learning-intellige.vercel.app

> **Status of this draft.** Everything up to and including §8 describes the finished system and
> uses measured results. §9 (pilot results) has marked gaps, **[PENDING PILOT]**, that must be
> filled from the Study page and the exported CSVs once the study has run. No pilot number in this
> report may be estimated or invented.

---

## Abstract

Practice platforms usually give every student the same questions in the same order. MENTORX is
a web application that teaches undergraduate Machine Learning (19 concepts, 285 multiple-choice
questions with a prerequisite graph) and personalises practice with a trained knowledge-tracing
model. For every candidate question, the model predicts the probability that this student answers
it correctly, from the student's answer history, the time since they last practised, and the
question's difficulty. MENTORX serves a question whose predicted probability is close to 0.65,
estimates mastery of every concept, recommends a learning path that respects prerequisites, and
schedules revision when predicted mastery decays.

We compared five models on two public datasets, using a selection rule fixed before training and
held-out students. Gradient boosting was best on both: AUC 0.775 (95% CI 0.762–0.785) on
ASSISTments 2009 and 0.771 (0.763–0.780) on EdNet, with expected calibration error 0.004. The
system is deployed (React, FastAPI, PostgreSQL on Vercel and Render) and covered by 228 automated
tests, with 97% backend coverage. A randomised pilot (adaptive vs. random question selection,
counterbalanced pre/post-tests, SUS questionnaire) is built in, and its results are
**[PENDING PILOT]**.

---

## 1. Introduction

### 1.1 Problem
Students learning Machine Learning face a long chain of dependent concepts: linear algebra and
probability before regression, gradient descent before neural networks. Static question sets
ignore what a student already knows. They waste time on mastered material, push students into
topics whose prerequisites are missing, and never return to material that is being forgotten.

### 1.2 Aim and objectives
MENTORX aims to make practice adaptive using a model trained on real student data, and to
measure honestly whether that helps.

| ID | Objective | Measured by | Status |
|---|---|---|---|
| OBJ-1 | Predict correctness better than simple baselines | AUC, log loss, calibration on held-out students | **Met** on two public datasets (§5) |
| OBJ-2 | Match question difficulty to the student | Observed correctness on served questions close to the 0.65 target | **[PENDING PILOT]**: logged for every answer |
| OBJ-3 | Improve learning outcomes | Pre/post gain, adaptive vs. control | **[PENDING PILOT]** |
| OBJ-4 | Keep students practising meaningfully | WAU, D7 retention, completion rate | **[PENDING PILOT]** |
| OBJ-5 | A maintainable, tested, deployed system | CI, coverage, public URL, documentation | **Met** (§7–8) |

### 1.3 Contributions
1. A complete, deployed adaptive learning system for ML with a reviewed question bank and
   prerequisite graph.
2. A leakage-safe evaluation of five knowledge-tracing approaches on two public datasets, with a
   pre-registered selection rule, bootstrap confidence intervals and ablations.
3. Engineering for honest live evaluation: the model's prediction is stored *before* every answer,
   so its real-world accuracy and calibration can be measured on MENTORX students.
4. A built-in randomised pilot with counterbalanced parallel test forms and pseudonymised exports.

---

## 2. Background

**Knowledge tracing** models what a student knows from their sequence of answers. *Bayesian
Knowledge Tracing* (BKT; Corbett & Anderson, 1994) treats each skill as a hidden binary state with
learn, guess and slip probabilities. *Performance Factors Analysis* (Pavlik et al., 2009) and
related logistic models predict correctness from counts of past successes and failures.
*Deep Knowledge Tracing* (Piech et al., 2015) uses recurrent networks. Gradient-boosted decision
trees (e.g. LightGBM; Ke et al., 2017) are strong on tabular features like these.

**Difficulty targeting.** Practice is most effective when it's neither trivial nor
overwhelming. Wilson et al. (2019) argue, under their assumptions, that an error rate around 15%
maximises learning speed. MENTORX targets a slightly harder 65% success rate as a configurable
compromise for new conceptual material, and records the observed rate so it can be checked.

**Forgetting and revision.** Spaced-repetition systems schedule review from a model of
forgetting (e.g. Settles & Meeder, 2016). MENTORX doesn't need a separate forgetting model.
Its prediction model takes time since practice as an input, so mastery estimated *now* falls
naturally as time passes.

**Calibration.** MENTORX acts on predicted probabilities, so they must be calibrated, not just
correctly ranked. We report expected calibration error (ECE; Guo et al., 2017) alongside AUC.

**Datasets.** ASSISTments 2009 (school mathematics; Feng et al., 2009) and EdNet-KT1 (TOEIC
English, multiple choice; Choi et al., 2020). Neither covers Machine Learning, which motivates the
concept-agnostic design in §5.

---

## 3. Requirements

Requirements were written before implementation in a Software Requirements Specification
([SRS.md](../srs/SRS.md)): **87 functional requirements, 29 non-functional requirements,
34 user stories** and the use cases, prioritised with MoSCoW. The main functional groups:

| Group | Examples |
|---|---|
| AUTH | registration with a privacy notice, login, refresh-token rotation, profile, export and deletion of one's data |
| CONT | subjects, concepts, prerequisite graph, versioned questions loaded from YAML |
| DIAG | a 19-question diagnostic (one per concept, prerequisite order, no feedback) |
| QUIZ | model-driven question selection, answer feedback, mastery change, question flags |
| KT | mastery estimation, decay, model versions and fallbacks |
| PATH / REV | learning path respecting prerequisites; revision when mastery decays |
| DASH | dashboard with real data only, trends, heatmap, history |
| ENG | daily goal of *valid* answers, streaks, weekly report |
| PILOT | random group assignment, pre/post-tests, SUS, feedback, pseudonymised exports |

Requirements are traced to milestones and test files (SRS §6). The testing report gives the
status of every non-functional requirement.

---

## 4. Design

### 4.1 Architecture
MENTORX is a **modular monolith** (design decision D-1):

```
Browser ── HTTPS ──> Vercel: React SPA ── /api/* rewrite ──> Render: FastAPI (Python) ──> PostgreSQL
                                                                 │
                                                       mentorx_ml (shared feature code)
                                                       + model artifact (gradient boosting)
```

- **Frontend:** React 19, TypeScript, Vite and Tailwind CSS. The browser only talks to the Vercel
  origin, which forwards `/api/*` to Render. The API is therefore same-origin, which lets the refresh
  token live in a `Secure; HttpOnly; SameSite=Strict` cookie.
- **Backend:** FastAPI with Pydantic v2, SQLAlchemy 2 and Alembic. Services hold the business
  logic; routers only translate HTTP.
- **ML:** a separate `mentorx_ml` package used by *both* the training scripts and the backend,
  which prevents training/serving skew (D-3).

Thirteen design decisions are recorded with their reasons in
[architecture.md](../design/architecture.md). The most consequential are:

| ID | Decision | Reason |
|---|---|---|
| D-3 | Shared feature package for training and serving | Train/serve skew is the most common bug in deployed ML; a test proves the serving features equal the training features |
| D-4 | Store the prediction before every answer | Enables honest live evaluation on real students |
| D-5 | The server holds the served question, its timing and the answer key | No cheating from the browser; trustworthy response times |
| D-6 | Mastery = the model's prediction on a reference question, *now* | Decay with time comes for free; no separate forgetting model |
| D-9 | Random choice among the 3 candidates closest to the target | Avoids repetition and adds exploration data for retraining |
| D-10 | Monotone envelope over time | Gradient boosting isn't monotone in time; mastery must not rise without practice |

### 4.2 Data model
PostgreSQL with 18 tables ([database.md](../design/database.md)). Principles: `attempts` is the
append-only record; mastery, snapshots and paths are derived. Questions and models are versioned.
Every user-owned table cascades from `users`, so account deletion is a single statement.

### 4.3 Content
19 concepts with a prerequisite DAG and 285 questions in YAML under version control (D-7). Per
concept there are 1 diagnostic question, at least 12 practice questions spread over three
difficulties, and two parallel test-form questions (A and B) that never appear in practice. A
validator enforces this standard, including balanced answer letters (each of A–D is the key for
24–26% of questions).

---

## 5. Machine learning

Full details and reproduction commands: [ml-report.md](../ml-report.md).

### 5.1 Task and features
Predict P(correct) for an answer using only information available before it. The features are
**concept-agnostic**, so a model trained on mathematics or English can be applied to ML
questions:
- *history*: attempts and smoothed accuracy on the concept, the last-3 accuracy, the previous
  outcome, first-attempt flag, interactions since last practice, overall and last-10 accuracy;
- *time*: log seconds since the concept was last practised and since the previous answer;
- *difficulty*: smoothed item and concept correct rates, learnt from training students only and
  cross-fitted.

### 5.2 Protocol
Student-level 70/15/15 split. Tuning and model choice on validation students only. A selection
rule written in the config **before any run**: the lowest validation log loss among models with
ECE ≤ 0.05 that score 50 candidates in ≤ 50 ms. The test set is scored once (the evaluation
script refuses to re-run without `--force`). 95% CIs come from bootstrapping whole students (200
replicates). Leakage is guarded by unit tests.

### 5.3 Results (held-out test students)

| Model | ASSISTments 2009 AUC (95% CI) | EdNet AUC (95% CI) | ECE (ASSIST / EdNet) |
|---|---|---|---|
| **Gradient boosting** | **0.775** (0.762–0.785) | **0.771** (0.763–0.780) | 0.004 / 0.004 |
| Logistic regression | 0.761 (0.748–0.772) | 0.752 (0.744–0.759) | 0.011 / 0.009 |
| BKT (from scratch) | 0.716 (0.703–0.727) | 0.642 (0.633–0.653) | 0.013 / 0.019 |
| Heuristic (concept accuracy) | 0.681 (0.664–0.695) | 0.566 (0.551–0.581) | 0.120 / 0.117 |
| Prior (constant) | 0.500 | 0.500 | 0.012 / 0.006 |

Gradient boosting was chosen by the pre-registered rule on both datasets. It is consistently
better than logistic regression (by 0.014 and 0.019 AUC), though the unpaired intervals overlap
slightly, and clearly better than the heuristic baseline.

**Ablations** (paired, on the same test students): removing per-item difficulty costs 0.029 AUC
(0.025–0.035); removing all difficulty features costs 0.057 (0.050–0.064); removing the two time
features costs 0.009 (0.007–0.012) on EdNet.

**Forgetting.** Varying only the time since practice, the EdNet model's mean predicted accuracy
peaks at 0.693 one hour after practice and falls to 0.645 after six months. This is the behaviour
the revision scheduler relies on. Because gradient boosting isn't monotone in time (one student's
projection was 0.587 at 30 days but 0.600 at 90), MENTORX applies a running-minimum envelope
(D-10), so mastery never rises without practice.

### 5.4 Deployed model
v1 = gradient boosting trained on EdNet, chosen because it is multiple-choice like MENTORX, has
timestamps, and is four times larger. Fallbacks are logistic regression, then a constant prior.
Question difficulty starts from the author's 1–3 rating and is updated as real answers arrive.

---

## 6. Implementation

The system was built in milestones, each finished, tested and deployed before the next:

| Milestone | Delivered |
|---|---|
| M0–M1 | Repository, CI; SRS, user stories, use cases, architecture, database and UML designs |
| M2 | Question bank: 19 concepts, prerequisite DAG, 285 questions, validator |
| M3–M4 | Data pipelines and EDA for two datasets; five models; evaluation; ablations; exported artifact |
| M5 | Schema and migrations, authentication, core API |
| M6 | Adaptive quiz engine: diagnostic, model-driven selection, attempt logging, mastery updates |
| M7 | Learning paths and revision scheduling |
| M8 | Frontend on real API data |
| M9 | Deployment (Vercel, Render, PostgreSQL), security headers, rate limits, structured logs, smoke tests |
| M10 | Daily goal, streaks, weekly report, feedback |
| M11 | Pilot: consent, pre/post-tests, SUS, admin metrics, pseudonymised exports, retraining pipeline |
| M12 | Performance fix, dependency update, testing report, this report |

**Question selection** (FR-QUIZ). Eligible candidates exclude test-form questions and questions
answered correctly in the last 7 days. The model predicts P(correct) for each, and one of the 3
closest to 0.65 is served. The served question, its prediction and the model version are stored
on the session before the student sees it. On submission the server computes correctness and
response time, stores the attempt, and recomputes mastery for that concept.

**Learning path** (FR-PATH). Concepts are recommended in this order: revision due, then
prerequisites to fix, then weak, then new. A concept counts as having its prerequisites in place
only if they have been *practised* and reached 0.6 mastery (D-11), since a model guess for an
unpractised concept isn't evidence. Each item states its reason.

**Engagement.** Only answers taking at least 3 s count toward the daily goal (rapid guesses
don't). The day is recorded with the goal in force at the time, so changing the goal later can't
rewrite history.

**Privacy.** Research consent is separate from the privacy notice, optional and revocable.
Students can export or delete all their data. Research exports contain only consenting students,
identified by an HMAC pseudonym.

---

## 7. Testing

Summary of the [testing report](testing-report.md):

- **228 automated tests**, all passing: backend 152 (unit 50, integration 26, API 76) on a real
  PostgreSQL database; ML 48; frontend 28. **Backend coverage 97%.**
- **CI** on every push: lint, type checks, all suites, a production build, and a job that installs
  the API exactly as Render does and runs the 17-step end-to-end smoke test against it. The smoke test also
  passes against the live production site.
- **Performance** (NFR-PERF-01: p95 ≤ 300 ms with 50 concurrent students): met at 10 concurrent
  students (p95 79 / 169 ms), **not met at 50**. Profiling found per-request aggregation of all
  students' answers. A tested cache cut p95 at 50 students from 6.9 s to 1.3 s (next question)
  and from 8.2 s to 1.6 s (submit), and removed all errors. The remaining gap needs more CPU than
  a single process on the free hosting plan provides.
- **Security:** headers and HSTS, rate limits, refusal to start with insecure settings,
  request-ID sanitising, and a dependency audit. A high-severity `react-router` advisory was found
  and fixed, leaving 0 known vulnerabilities in production dependencies.
- **Defects found by testing** and fixed: a misconfigured API host in production, the latency
  growth above, the dependency vulnerability, non-monotone decay, and log injection through
  request IDs.

---

## 8. Deployment and operations

Frontend on Vercel, API as a native Python web service on Render, managed PostgreSQL on Render.
No Docker is used. Each push to `main` that passes CI is deployed automatically. On start, the
service migrates the
database, loads the question bank idempotently and serves the API. Production refuses insecure
settings, hides the interactive API docs, and sends JSON logs with a request ID on every
line. A step-by-step guide is in [deployment.md](../deployment.md).

**Known operational limits** (free plan): the server sleeps when idle (first request up to about a
minute), there are no automated database backups, and the free database expires. These must be
fixed by upgrading before the pilot.

---

## 9. Pilot study

### 9.1 Design
- **Participants:** students recruited through the team's college network (target 30–60). Only
  students who sign up while the pilot is active and who consent are included.
- **Randomisation:** at sign-up, each student is assigned 50/50 to the **adaptive** group
  (model-driven selection) or the **control** group (uniformly random selection among the same
  eligible questions). Everything else is identical. Students are not told their group.
- **Measurement:** a 19-question pre-test on form A or B (randomly counterbalanced), then 2–4
  weeks of normal use, then a post-test on the other form. Test questions never appear in
  practice. **Gain** = post − pre (fraction correct).
- **Usability:** the SUS questionnaire after the post-test (Brooke, 1996). Target ≥ 70
  (NFR-USE-02); about 68 is average (Bangor et al., 2009).
- **Analysis:** mean gain per group with a 95% t-interval; difference with a Welch 95% CI and
  Cohen's d. Engagement: WAU, D1/D7 retention, completion. Live model quality: AUC, Brier score,
  ECE and a reliability table from the stored predictions. With N = 30–60, all results are
  **preliminary**.

### 9.2 Results: **[PENDING PILOT]**

Fill from the Study page and `mentorx-outcomes.csv`:

| | Adaptive | Control |
|---|---|---|
| Participants (consenting) | [PENDING PILOT] | [PENDING PILOT] |
| Completed pre / post | [PENDING PILOT] | [PENDING PILOT] |
| Mean pre-test | [PENDING PILOT] | [PENDING PILOT] |
| Mean post-test | [PENDING PILOT] | [PENDING PILOT] |
| Mean gain (95% CI) | [PENDING PILOT] | [PENDING PILOT] |
| SUS mean (n) | [PENDING PILOT] | [PENDING PILOT] |

Adaptive − control gain: [PENDING PILOT] (Welch 95% CI [PENDING]; Cohen's d [PENDING]).

Live model quality on MENTORX students: AUC [PENDING], Brier [PENDING], ECE [PENDING]; observed
correctness on served questions: [PENDING] vs. the 0.65 target (OBJ-2).

Engagement: students [PENDING], WAU [PENDING], D1 [PENDING], D7 [PENDING], completion [PENDING].

### 9.3 Retraining (v2): **[PENDING PILOT]**
The exported answers are cleaned into the same table format as the public datasets
(`ml/mentorx_ml/data/mentorx.py`, tested), then trained and evaluated with `configs/mentorx.yaml`.
Compare v2 with v1 on held-out MENTORX students, and report plainly if the data is too small to
separate them.

---

## 10. Discussion

**What worked.**
- The concept-agnostic feature design let a model trained on public data drive a new subject from
  day one.
- The pre-registered selection rule and single-use test set make the ML results credible.
- Storing predictions before answers turns the deployed system into an evaluation instrument.
- Milestone-by-milestone delivery with CI and smoke tests caught real defects early. The wrong
  production host is an example: it was found and fixed within one session.

**Threats to validity.**
1. *Domain transfer:* the public results are about mathematics and English, not ML. Live
   evaluation (§9) is the real test.
2. *Small sample:* the pilot can show a direction and an effect size, not proof.
3. *Strong control:* the control group still gets explanations and the learning path; only
   question selection differs. That isolates the model's effect but makes a difference harder
   to detect.
4. *Content review:* the question bank was drafted and answer-checked with AI assistance.
   Human review was a 20-question random spot-check ([review log](../question-review-log.md)).
5. *Test forms:* each form has one question per concept, so test scores are coarse.

**Limitations of the system.**
- Latency at 50 concurrent students on the free plan (§7).
- Single process: rate limits and caches are per process.
- No DKT comparison.
- Achievements and adaptive challenges (both "could have") were not built.

---

## 11. Future work
1. Run the pilot; retrain v2 on MENTORX data; train with a monotone time constraint.
2. Cache per-student mastery state, and move to multiple workers with a shared store, to meet
   NFR-PERF-01 at 50 users.
3. Lighthouse, axe-core and real-device tests; a 5-user usability test.
4. More subjects: the content format, model and pipeline are subject-agnostic.
5. Achievements tied to learning milestones; adaptive challenges at P(correct) ≈ 0.4.

## 12. Conclusion
MENTORX shows that a calibrated, concept-agnostic knowledge-tracing model can drive adaptive
practice in a subject with no training data of its own. It beat simple baselines on two
independent datasets with a pre-registered, leakage-safe protocol, and it is deployed as a
tested, documented system. Whether adaptive selection improves learning for real students is
exactly what the built-in randomised pilot measures. That result belongs in §9, once it has been
measured.

---

## References

- Bangor, A., Kortum, P., & Miller, J. (2009). Determining what individual SUS scores mean:
  Adding an adjective rating scale. *Journal of Usability Studies*, 4(3), 114–123.
- Brooke, J. (1996). SUS: A "quick and dirty" usability scale. In P. W. Jordan et al. (Eds.),
  *Usability Evaluation in Industry* (pp. 189–194). Taylor & Francis.
- Choi, Y., Lee, Y., Shin, D., et al. (2020). EdNet: A large-scale hierarchical dataset in
  education. In *Artificial Intelligence in Education (AIED 2020)*. Springer.
- Corbett, A. T., & Anderson, J. R. (1994). Knowledge tracing: Modeling the acquisition of
  procedural knowledge. *User Modeling and User-Adapted Interaction*, 4(4), 253–278.
- Feng, M., Heffernan, N., & Koedinger, K. (2009). Addressing the assessment challenge with an
  online system that tutors as it assesses. *User Modeling and User-Adapted Interaction*, 19(3),
  243–266.
- Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural
  networks. In *Proceedings of ICML 2017*.
- Ke, G., Meng, Q., Finley, T., et al. (2017). LightGBM: A highly efficient gradient boosting
  decision tree. In *Advances in Neural Information Processing Systems 30*.
- Pavlik, P. I., Cen, H., & Koedinger, K. R. (2009). Performance factors analysis: A new
  alternative to knowledge tracing. In *Artificial Intelligence in Education (AIED 2009)*.
- Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python. *Journal of Machine
  Learning Research*, 12, 2825–2830.
- Piech, C., Bassen, J., Huang, J., et al. (2015). Deep knowledge tracing. In *Advances in
  Neural Information Processing Systems 28*.
- Settles, B., & Meeder, B. (2016). A trainable spaced repetition model for language learning.
  In *Proceedings of ACL 2016*.
- Wilson, R. C., Shenhav, A., Straccia, M., & Cohen, J. D. (2019). The eighty five percent rule
  for optimal learning. *Nature Communications*, 10, 4646.

**Please check every reference against the original source before submission.**

## Appendices (in the repository)
- A. Requirements: [SRS](../srs/SRS.md), [user stories](../srs/user-stories.md), [use cases](../srs/use-cases.md)
- B. Design: [architecture](../design/architecture.md), [database](../design/database.md), [UML](../design/uml.md)
- C. ML: [ml-report](../ml-report.md), [datasets](../datasets.md)
- D. Testing: [testing report](testing-report.md)
- E. Modules: [frontend](../modules/frontend.md), [engagement](../modules/engagement.md), [pilot](../modules/pilot.md)
- Slides: https://claude.ai/artifact/1AyGMjiSwAabi4jpuSzsao (private until shared; exports to PowerPoint and PDF)
- F. Operations: [deployment](../deployment.md); G. Content: [question bank guide](../question-bank-guide.md), [review log](../question-review-log.md)
