# Frontend (M8)

React 19 + TypeScript (strict) + Vite + Tailwind v4. Every number on screen comes from the API; there are no hard-coded or placeholder values (FR-DASH-08).

## Pages

| Route | Page | Requirements |
|---|---|---|
| `/` | Landing (logged out) | — |
| `/register`, `/login` | Account creation with privacy notice; login | FR-AUTH-01/04 |
| `/onboarding` | Enrol in ML, explain and start the diagnostic | FR-CONT-02, FR-DIAG-01 |
| `/session/:id` | Question player for diagnostic, practice and revision: no feedback during the diagnostic, feedback + explanation + mastery change in practice, "I don't know yet", report a problem, keyboard shortcuts (A–D / 1–4), resume | FR-DIAG, FR-QUIZ, FR-REV-04 |
| `/dashboard` | Resume banner, diagnostic call to action, mean mastery, mastered count, answers, accuracy, next 3 path items, revision due, strongest/weakest, 30-day trend chart, 12-week activity heatmap | FR-DASH-01/03/04/06/07 |
| `/path` | Full learning path with reasons, explanations, suggested level, refresh | FR-PATH |
| `/revision` | Due queue (peak → now) and model-projected due dates | FR-REV-02/05 |
| `/concepts` | Concept map laid out as the prerequisite graph, coloured by mastery; details and practice | FR-DASH-02 |
| `/history` | Sessions with accuracy and mastery before → after | FR-DASH-05 |
| `/settings` | Name, daily goal, time zone, research consent, data download, account deletion | FR-AUTH-08..11 |

## Auth design

- The API is called on the **same origin** (`/api/v1/...`). Vite proxies it in development, and Vercel rewrites it in production. So the refresh token can stay in an `HttpOnly`, `SameSite=Strict` cookie scoped to `/api/v1/auth`, which JavaScript never sees.
- The 30-minute access token is kept **in memory only**. On page load the app calls `/auth/refresh` to restore the session. On a 401 the client refreshes once (concurrent requests share the refresh) and retries.
- Redirects after login only go to in-app paths (no open redirect).

## Accessibility and mobile (NFR-USE-03, NFR-A11Y)

- Touch targets are at least 44 px (`min-h-11`), and the layout is responsive down to 360 px with a mobile menu.
- Answer options are real radio inputs in a `fieldset`, and focus moves to each new question and to the feedback.
- Charts have text alternatives: an `aria-label` summary, plus a screen-reader table for the trend chart. Mastery bars are `role="meter"`.
- There's a skip link, and `prefers-reduced-motion` and dark mode are respected.

## Bundle

There's no chart or UI library: charts and the concept map are hand-written SVG. The production JS is **97 KB gzipped** (budget 250 KB, NFR-PERF-03), as measured by `npm run build` on 2026-11-08.

## Tests (`npm test`)

- **API client:** token refresh, a single shared refresh, session expiry, error shape, and hiding 5xx details.
- **Routing:** the landing page, the protected-route redirect, onboarding, the dashboard's empty state with no placeholder numbers, and the 404 page.
- **Session player:** practice feedback and mastery change, no feedback during the diagnostic, "I don't know yet" sends null, the keyboard shortcut, and the diagnostic summary.
- **Chart and graph helpers:** gaps stay gaps, heatmap levels, and the concept-map layering with cycle detection.
