# Engagement module (M10)

**Purpose:** help students build a study habit without rewarding empty activity, and give the
team a direct feedback channel. Covers FR-ENG-01/02/03/05 and FR-PILOT-03.

## Daily goal and streak (FR-ENG-01..03)

- A student's **daily goal** is a number of *valid* answers (1–100, default 10), set in Settings.
- An answer is **valid** if it took at least 3 seconds (`VALID_ANSWER_MIN_MS`). Faster answers are
  treated as possible rapid guesses and don't count (FR-ENG-02). Any run of 5+ fast answers
  consists only of such answers, so the single time check covers that rule too.
- Days are the student's **local calendar days**, in the time zone from their profile.
- When today's valid answers reach the goal, the day is recorded in `goal_days` together with the
  goal **in force at that moment**. Lowering the goal later can't grant past days, and raising it
  can't take them away.
- **Current streak:** consecutive recorded days ending today. If today isn't done yet, the
  streak ending yesterday stays alive until the end of today. **Longest streak:** the longest run
  ever.
- `goal_days` is the only stored engagement state. Everything else is computed from attempts and
  mastery snapshots on request.

## Weekly report (FR-ENG-05)

For the last 7 local days (today included), per subject:
- questions answered and accuracy,
- days the goal was met,
- mean mastery at the start and at the end of the week, over concepts that had an estimate at
  both times, and their difference,
- **concepts improved:** concepts whose mastery rose by at least 0.05 over the week.

## Feedback (FR-PILOT-03)

Any page has a Feedback button: a 1–5 rating, a category (bug, question content, idea, other),
an optional message, and the page it was sent from. Stored in `feedback`, included in the data
export, and deleted with the account. Limited to 10 per hour per student.

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/engagement/streak` | goal, today's valid answers, current and longest streak |
| GET | `/api/v1/engagement/weekly?subject=ML` | the weekly report |
| POST | `/api/v1/feedback` | 201 with the stored feedback's id |

Every answer response also carries `goal`, the updated goal progress, so the quiz screen can
celebrate the moment the goal is reached.

## Not in M10

Achievements (FR-ENG-04) and the adaptive challenge (FR-ENG-06) are "could have" items, left
until after the pilot starts.
