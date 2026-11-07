# Watchdog rules

These are the rules the watchdog follows when it decides whether something is wrong. The watchdog is a background helper the router starts for itself, inside the router's session, so you never run it separately. Edit this file any time, in plain English, or ask the router to change a rule and it passes the request to the watchdog. The watchdog re-reads this file whenever it has changed, so changes apply from the next round.

## Numbers you can change

The check script (`.claude/watchdog/check.mjs`) reads the numbers below, and the watchdog itself reads `roundIntervalMinutes`, `browserWalkEveryNRounds` and `restartAfterRounds`. Change a value here and the next run uses it. Keep this as valid JSON: if it can't be read, the script falls back to its built-in defaults (the same values you see here) and prints a warning.

```json
{
  "roundIntervalMinutes": 10,
  "restartAfterRounds": 24,
  "staleMinutes": 15,
  "staleMinutesByStep": { "testing": 30, "reviewing": 30 },
  "slowStepMinutes": 45,
  "evalRoundsWithoutProgress": 3,
  "appUrl": "http://localhost:3000",
  "healthPaths": ["/"],
  "healthTimeoutSeconds": 30,
  "browserWalkEveryNRounds": 3,
  "repeatReportAfterMinutes": 60,
  "driftIgnore": [".job/", "rayfin-imaging/rayfin/functions/src/types.ts", "rayfin-imaging/rayfin/functions/runtimemetadata.json"]
}
```

- `roundIntervalMinutes`: minutes between watch rounds. Use a whole number from 1 to 25 (the watchdog treats anything outside that range as the nearest end). A new value takes effect when the watchdog next restarts its timer, within about 25 minutes.
- `restartAfterRounds`: after this many rounds the watchdog hands over to a fresh copy of itself, so it never runs out of room on a long session. The router starts the fresh one. At 10-minute rounds, 24 rounds is about 4 hours.
- `staleMinutes`: a worker counts as silent when its status file hasn't been updated for this long. This is the limit for every step not listed in `staleMinutesByStep`.
- `staleMinutesByStep`: a longer silence limit for particular steps. A worker can't update its status file while it waits on its tester and reviewer, so `testing` and `reviewing` get 30 minutes. Add a step here to give it its own limit.
- `slowStepMinutes`: a worker counts as slow when it has been on the same step for this long. The step's start time comes from `stepStarted` in the status file when it's there.
- `evalRoundsWithoutProgress`: a worker counts as stuck when this many test rounds in a row end without fewer failing checks than its best round so far. A new round is counted when `evals.round` in the status file goes up.
- `appUrl`, `healthPaths`, `healthTimeoutSeconds`: where the main app runs, which pages must load, and how long to wait for each one. Use pages that return 200 without signing in (for example `"/login"`); an API can list a health endpoint, and an app with no server uses `[]` to skip the health checks.
- `browserWalkEveryNRounds`: the watchdog walks through the app in a browser like a new user would on every round whose number divides by this (3 means rounds 3, 6, 9 ...), and only when the app's pages loaded and no team ticket is in progress.
- `repeatReportAfterMinutes`: how long to wait before telling the router about the same problem again.
- `driftIgnore`: paths a worker may always change without it counting as drift. A worker may also always change its own ticket folder. Add the files your tools rewrite on their own (project.md lists them), for example `"AGENTS.md"` for Next.js.

## What counts as stuck

A worker is stuck when any of these is true:

- Its `.job/status.json` `updated` time is older than the stale limit for its step (`staleMinutesByStep`, otherwise `staleMinutes`) while its step is not `done` or `blocked`. Workers update the file at least every 10 minutes outside of testing and reviewing, so silence past the limit usually means the worker died or is hung on a command.
- It has been on the same step for longer than `slowStepMinutes`.
- Its failing check count (`evals.failed`) has not gone down for `evalRoundsWithoutProgress` test rounds in a row. It is going in circles.
- Its step is `blocked`. The `note` field says why. This always needs someone to act.

Not stuck:

- A step of `done`, however old.
- A worker that was just slow once and has since moved on to a new step.
- A worktree with no status file that was created less than `staleMinutes` ago. It is still setting up.

## What counts as drifting

A worker is drifting when it changes files that its ticket doesn't list under `## Affected areas` in `specs/tickets/<slug>/rd.md`. Changes in its own ticket folder (`specs/tickets/<slug>/`) and in the `driftIgnore` paths don't count.

Judge drift with common sense before reporting it:

- Ignore files that come along with a listed change: a lockfile next to a listed `package.json`, a generated type file, a test file next to a listed source file.
- Report it when the file belongs to another ticket's area, or when it is a shared piece (database setup, auth, a shared schema or data model, routing or middleware) that the ticket doesn't mention. These cause merge clashes and surprise breakage.
- If the ticket has no `rd.md` or no Affected areas list, there is nothing to compare against. Don't report drift for it.

## App health

The main checkout (the app on `appUrl`) must keep working, because that is what the user sees.

- Every page in `healthPaths` must return HTTP 200.
- Every `browserWalkEveryNRounds` rounds, and only when the pages above loaded, the **Core flows** in `.claude/project.md` must work for a first-time user. Use the test account `t000`, created the way project.md says.
- If the app isn't running at all, that is not a fault. Note it in the log and skip the health checks and the browser walk. Only report it to the router if a ticket is waiting on the main app (for example, one marked done that needs a check after merge).
- **While a team ticket is in progress** (any `.job/status-*.json` in the main checkout has a step other than `done`), the team is editing and restarting the app on port 3000. The check script prints a `team-active` line. Skip the browser walk that round, and treat the app on 3000 being down or erroring as "team in progress", not a fault. Report it only if a teammate's status file has also gone stale; the script then prints it as `app-down` with that reason.
- **Finished team tickets don't count.** The check script already skips team status files whose ticket shows `done` on the board. Also ignore any team status file (`.job/status-*.json` in the main checkout) whose ticket shows `done` in `specs/tickets/BOARD.md`, even if the file's step is not `done`. Don't report it as stale or team-active, don't let it skip the browser walk, and judge app health on port 3000 as normal. Check BOARD.md before judging any `team-active` or team `stale` line.

## What to report and what to ignore

Report:

- Any worker that is stuck, as defined above.
- Any `blocked` worker.
- Drift into shared pieces or into another ticket's area.
- The main app returning an error or failing a step of the browser walk.

Ignore:

- Anything the check script flags that, on a closer look, is fine. Write the reason in the log.
- The same problem you already reported within `repeatReportAfterMinutes`, unless it got worse (for example, a slow worker is now also silent, or the app went from one failing page to two).
- Warnings in the dev server output that don't change what a user sees.
- Workers whose step is `done`.

## How to word messages to the router

- The router is the main conversation, so every message goes to it with SendMessage to `main`.
- One message per real problem. One line each.
- Start with `WATCHDOG:`.
- Include the ticket number when there is one.
- Say what the user would notice, not the internal detail. Then say what you saw in a few words.
- Don't suggest code fixes. The router decides what to do.

Examples:

- `WATCHDOG: ticket 004 has gone quiet. No status update for 22 min while building.`
- `WATCHDOG: ticket 002 is going in circles. Still 3 of 9 checks failing after 3 fix rounds.`
- `WATCHDOG: ticket 007 is blocked. Its note says "needs a decision on the plan names".`
- `WATCHDOG: ticket 003 is changing files outside its ticket: lib/auth.ts, which login depends on.`
- `WATCHDOG: the main app is broken. Publishing a page shows an error, so users can't publish.`
