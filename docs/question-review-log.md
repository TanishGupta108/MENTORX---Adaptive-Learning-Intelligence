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
