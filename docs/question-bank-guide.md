# Question Bank Guide: authoring and review

The question bank is the content every other part of MENTORX depends on. A wrong answer key silently corrupts the training data and the mastery estimates, so **every question is peer-reviewed before it reaches students.**

## 1. Where things live

```
question_bank/machine_learning/
├─ concepts.yaml          # 19 concepts + prerequisite graph
└─ questions/
   ├─ 01_foundations.yaml # one file per concept, numbered in teaching order
   ├─ ...
   └─ 19_neural_networks.yaml
```

Run the report any time (from `backend/`):

```bash
python scripts/question_bank_report.py                         # coverage + review progress
python scripts/question_bank_report.py --review-sheet review.md # readable sheet for reviewers
pytest tests/unit/test_question_bank.py                        # the same rules CI enforces
```

## 2. Question format

```yaml
  - id: reg-016                 # <concept prefix>-<number>; never reuse or renumber
    concept: ml.regularization  # code from concepts.yaml
    difficulty: 2               # 1 easy, 2 medium, 3 hard (author's estimate)
    diagnostic: true            # optional: the ONE placement question for this concept
    test_form: A                # optional: A or B, the pre/post-test parallel forms
    review_status: reviewed     # optional: draft (default) or reviewed
    stem: The question text?
    options:
      A: First option
      B: Second option
      C: Third option
      D: Fourth option
    answer: C
    explanation: Why C is right, and why the most tempting wrong option is wrong.
```

### YAML traps (the validator catches these, but avoid them)
| Trap | Example | Fix |
|---|---|---|
| A value starting with a quote | `explanation: "Linear" means…` | Reword so it doesn't start with `"`, or quote the whole value |
| A value starting with `|`, `>`, `[`, `{`, `*`, `&`, `!`, `%`, `@` | `explanation: \|1 − 4\| + …` | Start with a word, or quote the whole value |
| Bare `yes`, `no`, `true`, `false`, `on`, `off` | `A: yes` | Quote it: `A: "yes"` |
| Bare numbers | `A: 0.5` | Quote it: `A: "0.5"` (options must be text) |
| `: ` (colon + space) inside a value | `stem: Note: x` | Quote the whole value |

## 3. The content standard (enforced by tests)

Per concept:
- exactly **1 diagnostic** question (medium, covers the core idea),
- **≥ 12 practice** questions with at least one at each difficulty (target 4 easy / 5 medium / 3 hard),
- exactly **1 form-A** and **1 form-B** question, the **same difficulty**, testing the same skill with different numbers or examples. They're never used in practice, so pre/post-test scores aren't contaminated.

Whole bank:
- the correct letter is A/B/C/D in **18–32%** of all questions,
- within the diagnostic, form A and form B separately, each letter is correct in **15–35%** of questions, so "always guess B" can't inflate a test score,
- no duplicate IDs or stems; every option text distinct; no unknown fields.

## 4. Writing good questions

1. **Test one concept.** If answering needs another concept, that concept should be a prerequisite.
2. **Make every distractor a real misconception**: a swapped formula, a sign error, confusing P(A | B) with P(B | A), forgetting the bias. A distractor nobody would choose wastes an option.
3. **No giveaways**: avoid "all of the above" and "none of the above", options of wildly different lengths, and grammatical hints between the stem and the right option.
4. **One unambiguously correct answer.** If an expert could argue for two, rewrite it.
5. **Explanations teach.** Say why the answer is right *and* name the misconception behind the main distractor. Students read these after every answer.
6. **Calculations**: use numbers that work out cleanly, and make the distractors the results of typical mistakes.
7. **Original wording only.** Don't copy from textbooks, courses or exam papers.
8. **Difficulty**: 1 = recall a definition; 2 = apply it in a straightforward case; 3 = reason about an edge case, combine ideas, or diagnose a situation.

## 5. Review process

All 285 questions in v1 were drafted by Claude (an AI assistant) and are marked `draft`. **They must be reviewed by a team member before use.** Draft questions may be loaded in development, but production loads only `reviewed` questions (enforced by the seed command in M5).

1. Each concept file is assigned to a reviewer who **did not write it** (see the table below).
2. The reviewer generates the review sheet, works through each question with the checklist, and fixes problems directly in the YAML.
3. For each question that passes, set `review_status: reviewed`.
4. Open a PR titled `content: review <concept>`. A second team member skims the diff, CI must pass, then merge.

### Review checklist
- [ ] The marked answer is correct (work calculations out yourself; don't trust the explanation).
- [ ] No other option could also be argued correct.
- [ ] The question tests the stated concept at the stated difficulty.
- [ ] Every distractor is plausible and is actually wrong.
- [ ] The explanation is correct, and any option letters it mentions match the options.
- [ ] The wording is clear, unambiguous and free of giveaways.
- [ ] For form A/B pairs: both test the same skill at the same difficulty.

### Suggested reviewer assignment
| Reviewer | Concept files |
|---|---|
| Member 1 (ML) | 11–15 (validation, k-NN, Naive Bayes, trees, ensembles) |
| Member 2 (Backend) | 01–05 (foundations, linear algebra, probability, preprocessing, linear regression) |
| Member 3 (Frontend) | 06–10 (gradient descent, logistic regression, metrics, bias-variance, regularisation) |
| Member 4 (Integration/QA) | 16–19 (SVM, clustering, dimensionality reduction, neural networks) |

## 6. Changing questions after launch

- **Fixing a typo** that doesn't change the meaning: edit in place.
- **Changing the stem, an option or the answer**: edit in place. The seed command (M5) detects the change and creates a new database version, so past attempts stay linked to the version the student actually saw.
- **Removing a question**: delete it from the YAML. The seed command retires it rather than deleting it.
- **Never reuse an ID** for a different question.
