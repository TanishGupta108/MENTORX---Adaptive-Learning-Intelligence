# Viva preparation: likely questions and model answers

Every team member should be able to answer every question here, not only those about their own
area. Numbers come from [ml-report.md](../ml-report.md) and the [testing report](testing-report.md).
Where the pilot hasn't produced results yet, the answer says so. Never quote a number that isn't
in a generated report.

## A. The problem and the idea

**1. What problem does MENTORX solve?**
Practice is usually one-size-fits-all: every student gets the same questions in the same order.
MENTORX estimates each student's mastery of 19 Machine Learning concepts from their real answers,
then uses those estimates to choose the next question, recommend what to study next (respecting
prerequisites) and schedule revision when predicted mastery decays.

**2. Why is this a machine learning problem and not just rules?**
The core decision (which question next) needs a calibrated probability that *this* student gets
*this* question right, given their whole history, timing and the question's difficulty. A rule
like "running accuracy on the concept" is what we compared against. It was badly calibrated
(ECE ≈ 0.12) and much less accurate than the trained model (AUC 0.681 vs 0.775 on ASSISTments).

**3. What are your objectives and how do you measure them?**
OBJ-1: beat baselines at predicting correctness (AUC, log loss, calibration on held-out students:
met on both public datasets). OBJ-2: match difficulty to the student (observed correctness near
the 0.65 target: measured live in the pilot). OBJ-3: improve learning (pre/post gain, adaptive vs
control: pilot). OBJ-4: engagement (WAU, D7, completion: pilot). OBJ-5: tested, deployed,
maintainable system (CI green, public URL, documentation: met).

## B. Machine learning

**4. Which model do you use and why?**
Gradient boosting (scikit-learn HistGradientBoosting) on concept-agnostic features: the student's
history on the concept and overall, time since practice, and question/concept difficulty. It was
chosen by a selection rule written down *before* any run: lowest validation log loss, among models
with ECE ≤ 0.05 that score 50 candidates in ≤ 50 ms. It won on both datasets (test AUC 0.775 on
ASSISTments 2009, 0.771 on EdNet; ECE 0.004).

**5. Why log loss as the selection metric, not AUC?**
MENTORX acts on the probabilities themselves (it targets P(correct) ≈ 0.65), so they must be
calibrated, not just correctly ranked. Log loss rewards calibrated probabilities; AUC ignores
calibration.

**6. How did you avoid data leakage?**
Splits are by student (70/15/15), so no student is in two splits. Item and concept difficulty are
learned from training students only, and cross-fitted within training so a row's own label never
feeds its feature. History features use strictly earlier answers. Tests enforce this: changing a
row's label or any later label leaves its features unchanged. The test set is scored once by
`evaluate.py`, which refuses to re-run without `--force`.

**7. Your data is maths and English, but the app teaches ML. Isn't that a problem?**
Yes, and we say so. That's why every feature is concept-agnostic (counts, accuracies, times,
difficulties), never "which concept". The public results validate the method, not performance on
MENTORX. To measure real performance, MENTORX stores the model's prediction *before* every answer,
so the Study page computes live AUC and calibration on real students. Phase B retrains on the
pilot's consented data (v2) and compares it with v1 on held-out MENTORX students.

**8. Is gradient boosting significantly better than logistic regression?**
Consistently better on both datasets (by 0.014 and 0.019 AUC), but the unpaired intervals overlap
slightly. So the honest claim is "consistently better", not "significantly better". Against the
heuristic baseline, the paired improvement is clearly significant.

**9. Why not deep knowledge tracing (DKT)?**
It was a "could have". With a small team, we prioritised a well-validated, well-calibrated,
fast, explainable model. Published DKT results on ASSISTments 2009 typically include scaffolding
rows, so they aren't directly comparable with ours anyway.

**10. What was BKT's role?**
An interpretable baseline that we implemented from scratch and tested (it recovers known
parameters from simulated students). It was clearly worse (AUC 0.716 and 0.642), especially on
EdNet's many small tag-set concepts, so it isn't deployed.

**11. What does the ablation study show?**
Question difficulty matters most: removing per-item difficulty costs 0.029 AUC, and removing all
difficulty features costs 0.057. The two time features add 0.009 on EdNet. Each group adds a
measurable, significant improvement.

**12. How does MENTORX handle forgetting?**
Mastery is the model's prediction on a reference question *now*, so it falls as time since
practice grows (on EdNet, mean predicted accuracy peaks at 0.693 one hour after practice and falls
to 0.645 after six months). Gradient boosting isn't monotone in time (we measured 0.587 at 30 days
but 0.600 at 90), so we apply a monotone envelope (D-10). With no new answers, mastery can only
fall. A test enforces this.

**13. How is the next question chosen?**
For each eligible candidate question, the model predicts P(correct). MENTORX picks at random among
the 3 whose prediction is closest to 0.65 (D-9). The randomness adds exploration data for
retraining. In the pilot's control group the choice is uniformly random among the same
candidates, and everything else is identical.

**14. What happens with a brand-new question that has no answers?**
Its difficulty feature starts from a prior based on the author's 1–3 rating, then updates as
answers arrive. The ablation suggests this costs roughly 0.03 AUC at first.

**15. What if the model file is broken in production?**
The `KnowledgeModel` interface has fallbacks (D-2): logistic regression, then a constant prior,
so the app keeps working. The smoke test after each deploy prints which model version is
actually in use.

## C. Software engineering

**16. Describe the architecture.**
A modular monolith (D-1): a React + TypeScript single-page app on Vercel; a FastAPI backend in
Docker on Render; managed PostgreSQL. The browser only talks to the Vercel origin, which forwards
`/api/*` to Render, so cookies stay same-origin. ML feature code is a shared package used by both
training and serving (D-3), which prevents train/serve skew.

**17. Why a monolith and not microservices?**
Four people, one deployment, free hosting, and one database transaction per answer (store the
attempt, update mastery, update the goal). Modules talk through Python interfaces, so the ML
service could be split out later.

**18. How do you know training and serving compute the same features?**
They use the same `mentorx_ml` code, and the fast serving path has tests that check it produces
identical values to the training code.

**19. How is the system secured?**
Short-lived access JWTs and a rotating refresh token in a `Secure; HttpOnly; SameSite=Strict`
cookie (D-8). Passwords are hashed. Rate limits on login (per account and IP) and registration
(per IP). The answer key never reaches the browser, and the server holds the served-question
state and timing (D-5). Security headers include a strict CSP and HSTS. The app refuses to start in
production with an insecure secret or insecure cookies. Interactive API docs are off in
production, and the container runs as a non-root user.

**20. How did you test it?**
See the [testing report](testing-report.md): unit, integration and API tests on a real PostgreSQL
database, frontend component tests, ML leakage and correctness tests, a production smoke test run
against the live site after every deploy, a CI job that builds and smoke-tests the Docker image,
and a 50-user load test against the latency requirement.

**21. How is the database schema managed?**
Alembic migrations, applied automatically when the container starts. A test checks that the
SQLAlchemy models and the migrations describe exactly the same schema.

**22. Tell us about a bug you found and fixed.**
Two good ones. (a) Deployment: the frontend's API rewrite initially pointed at a guessed host,
`mentorx-api.onrender.com`, which belonged to a stranger's service, so sign-ups failed. We fixed
it, documented "never guess the host", and the smoke test now runs through the real frontend.
(b) ML: gradient boosting's non-monotone time response made concepts flip in and out of revision,
fixed with the monotone envelope (D-10).

**23. How is the question bank quality-controlled?**
Questions live in YAML in git (D-7) and are validated by tests: coverage per concept, answer-letter
balance, no duplicates. All 285 were drafted with AI assistance. An AI answer-key check
re-derived every calculation and found no wrong keys, and fixed three questions or explanations.
A random sample of 20 is human spot-checked ([review log](../question-review-log.md)). We say
plainly that the review was AI-assisted.

## D. Data, ethics and the pilot

**24. How do you protect student data?**
Data minimisation, a privacy notice accepted at sign-up, and research consent that is separate,
optional and revocable. Students can export or delete all their data, and deletion cascades
through every table. Research exports contain only consenting students, under a stable
pseudonym (an HMAC of the ID) with no names or emails.

**25. How does the pilot work?**
While it runs, new sign-ups are randomly assigned (50/50) to adaptive or control and to pre-test
form A or B (counterbalanced). Consenting participants take a 19-question pre-test (which also sets
up their profile), use MENTORX for 2–4 weeks, then take a post-test on the other form and the SUS
questionnaire. The outcome is learning gain (post − pre), compared between groups.

**26. Can you claim the ML caused better learning?**
Only as far as the design allows: random assignment, identical treatment apart from question
selection, and parallel test forms that are never used in practice. With 30–60 students, the
results are preliminary. We report effect sizes with Welch 95% confidence intervals and Cohen's d,
and say so if the interval includes zero.

**27. Why might the pilot show no difference?**
Small sample, a short duration, both groups still getting feedback and explanations (the control
group is a strong baseline), and model mis-calibration on a new domain. Each of these is
measurable: live calibration on the Study page, engagement per group.

**28. What does the SUS score mean?**
The System Usability Scale: 10 standard statements scored 0–100. Around 68 is average. Our target
was ≥ 70 (NFR-USE-02).

## E. Reflection

**29. What would you do differently?**
Build the deployment pipeline even earlier, use a paid database from the start of the pilot,
add a monotone constraint in training instead of post-processing, and get human reviewers onto the
question bank earlier.

**30. What's next?**
Run the pilot, retrain v2 on real data, add achievements and adaptive challenges (deferred "could
have" requirements), and add more subjects. The content and model pipeline are subject-agnostic.
