# Question bank review log

## 2026-11-09: AI answer-key check (Claude), all 285 questions

This was an automated second pass, **not** the human peer review required by the
[question bank guide](question-bank-guide.md). No question was marked `reviewed`.

**Method:** each question was read in full. Every calculation was re-derived independently
(dot products, norms, Bayes posteriors, Gini/entropy, sigmoid and log-loss values, hinge loss,
gradient steps, explained variance, centroids, parameter counts), and every conceptual answer
was checked against standard ML definitions. For each question the check covered whether the
marked answer is correct, whether another option could also be argued correct, and whether the
explanation is accurate.

**Result:** 0 incorrect answer keys found. 3 changes:

| ID | Change | Why |
|---|---|---|
| linalg-007 | Explanation corrected | It said `w X` is defined when n = d; the inner dimensions are actually 1 and n. |
| reg-015 | Explanation made precise | The number of non-zero lasso weights usually falls as λ grows, but not strictly at every step. |
| nn-014 (form A) | Input changed from [1, 3] to [1, 4], distractors updated | The pre-activation was exactly 0, so students who forgot the bias or the ReLU still got it right. |

**Minor observations, left for the human reviewers:**
- Some diagnostic questions (found-001, linalg-001) are difficulty 1, while the guide says diagnostics should be medium.
- tree-011 (difficulty 3) is the same calculation type as tree-014 (difficulty 2).
- Some form B items add a sign twist that their form A partner lacks (prep-015, gd-015, linreg-015). They test the same skill but may be slightly harder.

## 2026-11-09: decision, all 285 marked `reviewed` (AI-assisted)

The project owner chose to mark every question `review_status: reviewed` on the strength of the
check above, with a **human spot-check** of a random sample instead of a full peer review. This
departs from section 5 of the [question bank guide](question-bank-guide.md) and must be stated
as AI-assisted review in the final report.

### Human spot-check (to do)

20 questions drawn at random (`random.seed(20261109)`). For each one, a team member works through
the review checklist in the guide and records the result here. Any wrong answer key found means
the whole affected concept file gets a full human review.

| ID | Reviewer | Result (OK / fixed / problem) |
|---|---|---|
| clust-011 | | |
| clust-013 | | |
| ens-007 | | |
| ens-008 | | |
| found-005 | | |
| gd-008 | | |
| linalg-010 | | |
| linreg-011 | | |
| logreg-004 | | |
| logreg-005 | | |
| metrics-001 | | |
| metrics-005 | | |
| nb-010 | | |
| nb-011 | | |
| prep-004 | | |
| reg-014 | | |
| svm-014 | | |
| tree-010 | | |
| val-005 | | |
| val-014 | | |
