# User Stories: MENTORX

Format: *As a [role], I want [goal], so that [benefit].* Acceptance criteria use Given/When/Then and are the basis for tests. Priority is MoSCoW (M/S/C). Linked requirements refer to the [SRS](SRS.md).

## Epic E1: Account and privacy

**US-01 Register** (M · FR-AUTH-01/02/03)
As a student, I want to create an account with my email, so that my progress is saved.
- Given I'm on the register page, when I submit a valid name, email and password (≥ 8 chars) and accept the privacy notice, then my account is created and I land on onboarding.
- Given the email is already registered (in any letter case), when I submit, then I see "An account with this email already exists" and no account is created.
- Given I haven't accepted the privacy notice, then the submit button is disabled.

**US-02 Log in** (M · FR-AUTH-04/06/07)
As a student, I want to log in, so that I can continue where I left off.
- Given valid credentials, when I log in, then I see my dashboard.
- Given a wrong password or unknown email, then I see the same message "Email or password is incorrect".
- Given 5 failed attempts within a minute, then further attempts are blocked for 1 minute.

**US-03 Stay signed in and log out** (M · FR-AUTH-04/05)
As a student, I want to stay signed in for a while and be able to log out, so that I don't retype my password every visit but can still secure shared devices.
- Given I logged in within 14 days and didn't log out, when I reopen the app, then I'm still signed in.
- When I log out, then my refresh token is revoked and protected pages redirect to login.

**US-04 Set my goal and profile** (M · FR-AUTH-08)
As a student, I want to set my daily question goal and time zone, so that streaks match my routine.
- Given the profile page, when I set a goal between 1 and 100 and save, then today's progress uses the new goal.

**US-05 Control my data** (M · FR-AUTH-09/10/11)
As a student, I want to choose whether my data trains the model, download my data and delete my account, so that I stay in control of my information.
- The research-consent toggle defaults to *off* and can be changed at any time.
- When I request an export, then I get a JSON file with my profile, attempts, sessions and mastery.
- When I delete my account and confirm by typing my email, then all my records are deleted and I'm logged out.

## Epic E2: Getting started

**US-06 Choose a subject** (M · FR-CONT-01/02)
As a student, I want to pick a subject to study, so that I only see relevant material.
- Given the onboarding page, then I see each active subject with its concept count. When I choose one, then I'm enrolled and offered the diagnostic.

**US-07 Take a diagnostic** (M · FR-DIAG-01/04/06)
As a new student, I want a short placement test, so that MENTORX knows where to start me.
- Given I'm enrolled, when I start the diagnostic, then I get one question per concept in prerequisite order, with a progress bar showing "n of 19".
- Given I leave halfway, when I return, then it resumes at the next unanswered question.

**US-08 Admit I don't know** (M · FR-DIAG-02)
As a student, I want an "I don't know yet" option, so that I don't have to guess, and my starting point is more accurate.
- When I choose "I don't know yet", then it counts as incorrect with no option selected, and the next question appears.

**US-09 See my starting point** (S · FR-DIAG-03/04)
As a student, I want a summary after the diagnostic, so that I understand my strengths and gaps.
- When I finish, then I see my strong and weak concepts and my first recommended concept, using the model's mastery estimates.

## Epic E3: Adaptive practice

**US-10 Practise what's recommended** (M · FR-QUIZ-01/09)
As a student, I want to press one button and get the right practice, so that I don't have to plan my studying.
- When I start "Recommended practice", then I get a 10-question session drawn from my current learning path.

**US-11 Practise a chosen concept** (M · FR-QUIZ-01)
As a student, I want to practise a specific concept, so that I can prepare for a class or exam topic.
- When I choose a concept on the mastery map and start practice, then all questions are on that concept.

**US-12 Questions at the right level** (M · FR-QUIZ-02/03/05)
As a student, I want questions that are neither trivial nor impossible, so that practice is efficient and motivating.
- Given the adaptive group, then each question is chosen from the 3 candidates whose predicted P(correct) is closest to 0.65.
- I never see the same question twice in a session, or a question I got right in the last 7 days (unless the concept's questions have run out).

**US-13 Learn from each answer** (M · FR-QUIZ-08)
As a student, I want immediate feedback with an explanation, so that I learn from my mistakes.
- When I submit, then I see whether I was right, the correct option, the explanation and my updated mastery for that concept.

**US-14 Report a bad question** (S · FR-QUIZ-11)
As a student, I want to flag a question that seems wrong, so that content quality improves.
- When I flag a question with an optional comment, then admins can see it and my session continues.

**US-15 See mastery change** (M · FR-KT-03)
As a student, I want to see how my answer changed my mastery, so that I see progress as it happens.
- After each answer, the concept's mastery bar animates from its old to its new value, as computed by the active model.

## Epic E4: Guidance

**US-16 Know what to study next** (M · FR-PATH-01/03/04)
As a student, I want a short list of what to study next, so that I always have a clear next step.
- The dashboard shows up to 5 recommended concepts, each with a reason tag and target difficulty. They update after every session.

**US-17 Be sent back to prerequisites** (M · FR-PATH-02)
As a student struggling with a concept, I want to be pointed to the prerequisite I'm missing, so that I fix the root cause.
- Given my mastery of Regularisation is low and of Bias & Variance is < 0.6, then the path recommends Bias & Variance with reason "prerequisite" before Regularisation.

**US-18 Understand why** (S · FR-PATH-06)
As a student, I want each recommendation explained in plain words, so that I trust it.
- Each item shows a sentence that names the concept, its mastery and the reason.

**US-19 Revise before I forget** (M · FR-REV-01/02/03)
As a student, I want to be told when a topic I'd mastered is fading, so that I revise it in time.
- Given a concept peaked at ≥ 0.8 and its current predicted mastery is < 0.6, then it appears in my revision queue, and I can start a 5-question revision session.

**US-20 See revision pay off** (S · FR-REV-04)
As a student, I want to see my mastery before and after revising, so that I know it worked.

## Epic E5: Progress

**US-21 Overall progress** (M · FR-DASH-01/03)
As a student, I want to see overall progress and my strongest and weakest concepts at a glance.
- Concepts with fewer than 3 attempts aren't listed as strong or weak; they show "Not enough data yet".

**US-22 Mastery map** (M · FR-DASH-02)
As a student, I want a map of all concepts and how they connect, so that I see how my knowledge fits together.
- Each node shows the concept name and mastery %, coloured by band. Clicking a node opens its details and a "Practise" button.

**US-23 Trends** (M · FR-DASH-04/07)
As a student, I want charts of my accuracy and mastery over time, so that I see improvement.

**US-24 History** (M · FR-DASH-05)
As a student, I want a list of past sessions, so that I can review what I did.

## Epic E6: Motivation

**US-25 Daily goal and streak** (M · FR-ENG-01/02/03)
As a student, I want a daily goal and streak, so that I build a habit.
- Only valid answers count (≥ 3 s, not in a rapid-guess run). The streak increments when today's valid answers reach my goal, in my time zone.

**US-26 Weekly report** (S · FR-ENG-05)
As a student, I want a weekly summary, so that I see the bigger picture.

**US-27 Meaningful achievements** (C · FR-ENG-04)
As a student, I want achievements for real learning milestones, not just activity.

## Epic E7: Pilot

**US-28 Pre-test and post-test** (M · FR-PILOT-01/02)
As a pilot participant, I want clear pre- and post-tests, so that my learning can be measured fairly.

**US-29 Give feedback** (M · FR-PILOT-03/04)
As a student, I want to send feedback from any page, so that the team can improve MENTORX.

## Epic E8: Administration

**US-30 Load content** (M · FR-CONT-05/06)
As an admin, I want to load the question bank from YAML with one command, so that content is reviewed in git and deployed reliably.
- Running the seed command twice produces no duplicates. Changing a question's text creates a new version.

**US-31 Train and compare models** (M · FR-KT-07/08)
As an ML developer, I want one command per step (download, clean, train, evaluate), so that results are reproducible and comparable.

**US-32 Switch model version** (S · FR-KT-05)
As an admin, I want to activate a newly trained model without redeploying, so that improvements reach students quickly and safely.

**US-33 Pilot metrics** (M · FR-DASH-09)
As an admin, I want a pilot dashboard, so that we can evaluate engagement, learning gains and live model accuracy.

**US-34 Export training data** (M · FR-PILOT-05)
As an ML developer, I want a pseudonymised export of consenting users' attempts, so that the model can be retrained without exposing personal data.
