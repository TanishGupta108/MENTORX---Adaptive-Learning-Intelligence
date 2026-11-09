# Demo video script (about 7 minutes)

**Record with:** Windows: press **Win + Alt + R** in the browser window (Xbox Game Bar), or use
OBS Studio (free). Use a 1080p browser window at 100% zoom, and close other tabs and
notifications.

**Before recording (10 minutes before):**
1. Open https://mentorx-adaptive-learning-intellige.vercel.app so the free server wakes up.
2. Have two accounts ready:
   - **Demo student:** a fresh account that has done nothing yet. Create it just before recording,
     e.g. `demo-<date>@yourmail.com`.
   - **Admin:** an account whose email is in `ADMIN_EMAILS`.
3. Have a second tab ready with the GitHub repository's **Actions** page.

Speak slowly. Each scene lists **what to click** and **what to say**.

---

### Scene 1: The problem (0:00–0:40)
**Show:** the landing page.
**Say:** "Most practice apps give every student the same questions in the same order. MENTORX
teaches Machine Learning, and it uses a trained model to estimate what each student knows, from
their real answers, and to decide what they should practise next."

### Scene 2: Sign-up and the diagnostic (0:40–1:50)
**Click:** Log in as the demo student → enrol in Machine Learning → **Start the diagnostic**.
Answer 4–5 questions, including one "I don't know yet", then **End early** and confirm.
**Say:** "The diagnostic asks one question per concept, in prerequisite order, with no feedback,
so it measures rather than teaches. The model then estimates mastery of all 19 concepts, even ones
I didn't reach."

### Scene 3: The dashboard (1:50–2:50)
**Show:** Dashboard: mean mastery, strongest and weakest concepts, the daily goal and streak card,
"This week", the 30-day chart.
**Say:** "Every number here comes from my real answers. There are no placeholders: before I'd
answered anything, these cards explained what to do instead of showing zeros."

### Scene 4: Adaptive practice (2:50–4:00)
**Click:** **Start recommended practice**. Answer 3 questions, one of them wrongly on purpose.
**Say:** "For every candidate question the model predicts my chance of getting it right, and
MENTORX picks one close to 65%: hard enough to learn from, not so hard it's discouraging. After
each answer I get the explanation and see my mastery change. That change in points is the model
updating its estimate."

### Scene 5: Learning path and revision (4:00–4:50)
**Click:** **Learning path**, then **Revision**, then **Concepts** (the prerequisite map).
**Say:** "The path recommends concepts whose prerequisites I've already got in place, and each item
says why. Revision is scheduled when the model predicts my mastery has decayed: it learnt
forgetting from timing data."

### Scene 6: Feedback and privacy (4:50–5:20)
**Click:** **Feedback** in the header (show the dialog, then cancel) → **Settings** (show daily
goal, research consent, export and delete).
**Say:** "Students can send feedback from any page, download all their data, or delete their
account completely. Research consent is separate and optional."

### Scene 7: The study team's view (5:20–6:10)
**Click:** Log out → log in as the admin → **Study**.
**Say:** "For the pilot study, new students are randomly assigned to adaptive or random question
selection, and take a pre-test and a post-test on two parallel forms. This page shows learning
gain by group with confidence intervals, engagement, and the model's live accuracy and
calibration on real students, measured from the prediction stored before every answer. Exports
are pseudonymised: no names or emails."
*(If the pilot hasn't started, say: "The numbers fill in once the pilot runs.")*

### Scene 8: Engineering (6:10–7:00)
**Show:** the GitHub **Actions** tab with a green run, opening the `docker` job.
**Say:** "Every push runs about 230 automated tests across the backend, the ML pipeline and the
frontend, then builds the production Docker image and runs an end-to-end smoke test against it.
Only then does it deploy. The model was chosen with a selection rule we wrote down before
training, evaluated once on held-out students, and it beat every baseline on two public datasets."
**End on:** the landing page. "Thank you."

---

**After recording:** trim the start and end, check the audio is audible, and export as MP4
(1080p). Upload it unlisted to YouTube or Google Drive and put the link in the report.
