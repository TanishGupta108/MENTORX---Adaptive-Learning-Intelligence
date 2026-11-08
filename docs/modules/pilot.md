# Pilot module (M11)

**Purpose:** produce real evidence for the report. Does ML-driven question selection help students
learn more than random selection, is MENTORX usable, and how well does the model predict real
students? Covers FR-PILOT-01/02/04/05, FR-DASH-09 and FR-QUIZ-10.

## Who takes part

- While `PILOT_ACTIVE=true`, every new sign-up is randomly assigned, permanently, to the
  **adaptive** or **control** group (50/50) and to pre-test **form A or B** (counterbalancing).
  Accounts created while the pilot is off are never in the study.
- A student becomes a **participant** only after agreeing on the dashboard's study invitation
  (sets `consent_research`). They can withdraw at any time in Settings. Research outputs only
  ever include consenting students.
- Students are never shown their group.
- **Control** students get practice questions chosen uniformly at random from the same eligible
  candidates (same concepts, same session length). Everything else is identical (FR-QUIZ-10).

## The study, from the student's side

1. **Pre-test:** their form, 19 questions (one per concept, in prerequisite order), no feedback.
   It **replaces the diagnostic**: when it ends, the starting profile and learning path are
   built from it, so participants answer 19 questions at the start instead of 38.
2. Use MENTORX normally.
3. **Post-test:** the *other* form, available once the team sets `POSTTEST_OPEN=true`.
4. **SUS questionnaire:** the 10 standard System Usability Scale statements (Brooke, 1996), with
   "the system" replaced by "MENTORX", scored 0–100 in the standard way.

Pre/post-test questions (`test_form` A/B) never appear in practice, so test scores can't be
inflated by having practised the exact questions. Test answers are stored as normal attempts and
update mastery, like diagnostic answers.

**Score:** the fraction of the form answered correctly. Unanswered and "I don't know yet" count
as incorrect. **Gain:** post minus pre.

## The study team's side (Study page, `/admin`)

Accounts whose email is in `ADMIN_EMAILS` see a **Study** link with:
- learning gain by group: mean pre, post and gain with a 95% t-interval; the adaptive − control
  difference with a Welch 95% CI and Cohen's d. With 30–60 students, report these as
  preliminary;
- engagement: students, weekly active, day-1 and day-7 retention, session completion rate;
- live model quality from the prediction stored with every served question: AUC, Brier score,
  expected calibration error and a 10-bin calibration table;
- recent feedback;
- two **pseudonymised CSV exports** (FR-PILOT-05). Each student appears as a stable 12-character
  code (an HMAC of their ID), with no names or emails, consenting students only:
  - `mentorx-attempts.csv`: every answer, for retraining;
  - `mentorx-outcomes.csv`: one row per participant (group, form, pre, post, gain, SUS).

## Retraining (Phase B, v2)

Once there's enough data, from `ml/`:

```bash
# 1. Study page -> "Answers (for retraining)", save as ml/data/raw/mentorx/mentorx-attempts.csv
python scripts/clean.py --dataset mentorx     # -> data/processed/mentorx.parquet
python scripts/train.py --config configs/mentorx.yaml
python scripts/evaluate.py --config configs/mentorx.yaml
```

The cleaner drops answers under 3 s and students with fewer than 5 answers. Compare v2 against
v1 on held-out MENTORX students, and say so plainly if the data is too small to separate them.

## Running the pilot: checklist

| When | Who | What |
|---|---|---|
| Before | Team | Add your emails to `ADMIN_EMAILS` on Render. Check the Study page opens. |
| Start | Team | Set `PILOT_ACTIVE=true` on Render. Share the sign-up link with students. |
| During | Team | Watch the Study page: participants, pre-tests done, feedback. |
| End (after 2–4 weeks) | Team | Set `POSTTEST_OPEN=true`. Ask students to log in and take the post-test and questionnaire. |
| After | Team | Set `PILOT_ACTIVE=false`. Download both CSVs. Retrain (above). Write up. |

## API

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/pilot/status?subject=ML` | student: the next study step |
| POST | `/api/v1/sessions` with `type: pretest` or `posttest` | participant |
| POST | `/api/v1/pilot/sus?subject=ML` | participant, after the post-test, once |
| GET | `/api/v1/admin/pilot/metrics` | admin |
| GET | `/api/v1/admin/export/attempts.csv`, `/outcomes.csv` | admin |
