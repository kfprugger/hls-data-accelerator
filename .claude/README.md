# Agent setup

How features get built here: tickets are written and approved in a normal chat, then a router chat hands them to agents that build, check, merge and verify them. This file is the run guide and the shared contract. Every agent follows it. The project-specific parts (commands, test accounts, core flows) live in `.claude/project.md`.

## Who's who

All agents live in `.claude/agents/`.

| Agent | Runs as | Job |
|---|---|---|
| `router` | The main chat (`claude --agent router --name router --permission-mode auto`), the only session you run. Opus, high effort. | Starts the watchdog, talks to you, routes ready tickets, checks results against eval.md, sends follow-ups, dispatches merger, checker and reproducer, reacts to the watchdog. Never edits files or runs git. |
| `worker` | Subagent, own git worktree. Sonnet. | Builds one solo ticket, runs `tester` + `reviewer`, commits on its branch. A Stop hook (`.claude/hooks/worker-finish-gate.mjs`) won't let it finish until the status file says `done`, every eval passed and git is clean, or it says `blocked` with a note. |
| `tester`, `reviewer` | Nested helpers the worker starts. | Read-only. They never edit. |
| `merger` | Subagent, main checkout. | Merges a passed branch into main (a worker's ticket branch or a reproducer's fix branch), or commits a team ticket's uncommitted work. Runs lint + build, sets the ticket to `done` in rd.md and BOARD.md, commits. |
| `checker` | Subagent, main checkout, port 3000. | After a merge, walks the merged ticket and the core flows in the browser. Reports CONFIRMED breaks with repro steps, or "nothing found". Never edits. |
| `reproducer` | Subagent, own worktree, port 3090. | Tries to reproduce a bug. If confirmed and simple, fixes it and commits on its branch. Reports `CONFIRMED + FIXED`, `CONFIRMED, NO SIMPLE FIX` or `NOT REPRODUCED`. |
| `teammate` | Agent-team member, main checkout, port 3000. | Builds one block of a `team` ticket's Affected areas and messages the other teammates directly to agree on the shared shape. |
| `watchdog` | Background subagent of the router, started by the router when it starts. Sonnet, medium effort, compacts at 150k tokens. Exactly one at a time. | Every round (10 minutes by default) runs `.claude/watchdog/check.mjs --tick` on a Monitor timer, judges problems against `.claude/watchdog/RULES.md`, walks the core flows in the browser every 3rd round, and messages the router (the main conversation) with lines starting `WATCHDOG:`. Answers "why did X fail" and changes its rules when the router passes on your request. Hands over to a fresh copy every few hours (`WATCHDOG: restarting`), and the router starts the new one. Never fixes anything. |

Agents can't ask you questions. Anything they need decided goes to the router, which decides or asks you.

## Running it

**Before the first run (once).**

- **Fill in the profile.** Run `/write-tickets` once in a normal chat. On its first run it fills in `.claude/project.md` and asks you to confirm it. The router won't route until it says `**Profile:** filled in`.
- **`main` must hold everything.** Worktrees branch from the commit checked out in the project folder (`worktree.baseRef: "head"` in `settings.json`), so anything not committed on local `main` is invisible to workers. Before routing, `main` must contain the app plus `.claude/`, `CLAUDE.md` and `specs/tickets/`, and you must have `main` checked out in the project folder.
- **Ignore the job files.** `.job/` and `.claude/worktrees/` must be in `.gitignore`.
- **Trust the folder.** Open the project in Claude Code interactively once (`claude` in this folder) and accept the workspace trust prompt. Until you do, Claude Code skips hooks in agent frontmatter, so the worker's finish gate doesn't run.
- **Gitignored files.** A fresh worktree has none of them. If the app needs `.env` to start, list it in `.worktreeinclude` at the project root.

**1. Write tickets** in a normal chat (`claude`). Ask for features, and the `write-tickets` skill interviews you, writes `specs/tickets/NNN-slug/rd.md` + `eval.md`, and updates `specs/tickets/BOARD.md`. Approve each ticket so it moves from `draft` to `ready`, then commit to `main`.

**2. Start the router:**

```bash
claude --agent router --name router --permission-mode auto
```

It starts the watchdog in the background, then reads the board and starts every ready ticket that's allowed to run (or just the ticket number you give it). That's the only session you run. Talk to it like a normal chat: ask for status, mention bugs, ask about earlier tickets, ask why something failed, or ask it to change a watchdog rule (it passes those to the watchdog).

Note: auto mode has to be passed on the command line. Setting it in `settings.json` doesn't take effect.

## Tickets

```
specs/tickets/
├── BOARD.md
└── 004-seo-settings/
    ├── rd.md          requirements; **Status:** draft | ready | done, right under the title
    ├── eval.md        Automated checks, acceptance and edge case checks E-1, E-2, ... (Type automated | browser | API | CLI), Regression checks
    ├── results.md     one result line per check, written by the worker (or the teammates)
    ├── contract.md    team tickets only: the shared shape the teammates agreed on
    └── evidence/      screenshots and output from the checks
```

`specs/tickets/BOARD.md`:

```markdown
| # | Title | Status | Mode | Runs |
|---|---|---|---|---|
| 001 | Pricing monthly/yearly toggle | ready | solo | alongside |
| 002 | SEO settings per page | ready | solo | waits for 001: both change the published-page route |
```

- Only `ready` tickets get routed. `draft` tickets are never touched.
- `waits for NNN` is routed only after NNN is `done`.
- Mode `solo` means one worker. `team` means an agent team, with rd.md's Affected areas split into one block per teammate.
- Status on main changes only when the merger sets `done`. A ticket being built still reads `ready`; the router tracks what's running.

### Check IDs and results.md

The tester gives every check an ID, and results.md, the status file and the router all use the same IDs:

- `A-1`, `A-2`, ... for eval.md's Automated checks (lint, build, tests), in the order listed.
- `E-n` for Acceptance and Edge case checks, numbered as in eval.md.
- `R-1`, `R-2`, ... for eval.md's Regression checks, in the order listed.

results.md is a title line `# NNN-slug results`, then one line per check in that order:

```
A-1 | PASS | npm run lint exit 0
E-1 | PASS | specs/tickets/004-seo-settings/evidence/E-1.png
R-1 | FAIL | published site shows the old title after publish; specs/tickets/004-seo-settings/evidence/R-1.png
```

The third column is the evidence: a screenshot path that exists, or the short output that proves the result. Every browser check needs a screenshot. On a team ticket, each teammate writes its lines under its own `## <name>` heading in the same format.

## Ports

| Who | Port | Where |
|---|---|---|
| Main checkout (you, checker, watchdog, team ticket) | 3000 | the project folder |
| Worker on ticket NNN | 3100 + NNN (004 → 3104) | its worktree |
| Reproducer | 3090 | its worktree |

Every agent starts the app with the start command in `.claude/project.md`, with its own port swapped in. Worktrees are separate folders, so workers and the reproducer never clash. A team ticket works in the main checkout, so it uses the main checkout's own server on 3000: the first-named teammate starts it if nothing answers on 3000, and stops it at the end only if it started it. If your own dev server is running there, the team uses it and leaves it running.

## Fresh worktree

A new worktree has no installed packages, `.env` or local data. Each agent runs the **Fresh worktree setup** from `.claude/project.md` first.

Test accounts: worker on ticket NNN → `tNNN` (ticket 004 → `t004`). The reproducer uses `t090`, the team uses `t050` (on port 3000), and the checker and watchdog use `t000` (on port 3000). project.md says how to create one.

## Browser checks: agent-browser

Install with `npm i -g agent-browser && agent-browser install`. Before first use, run `agent-browser skills get core` for its usage guide. Every agent uses its own named browser session (`--session <name>`) so it doesn't share cookies with another agent, and saves screenshots to `specs/tickets/NNN-slug/evidence/`.

## Status file

Each worker and reproducer keeps `.job/status.json` at its worktree root. Each teammate keeps `.job/status-<name>.json` in the main checkout. `.job/` is gitignored. The watchdog and the router read these files.

```json
{
  "ticket": "004",
  "slug": "004-seo-settings",
  "step": "building",
  "stepStarted": "2026-11-03T13:50:00Z",
  "updated": "2026-11-03T14:05:00Z",
  "port": 3104,
  "branch": "<branch name>",
  "evals": { "passed": 3, "failed": 1, "total": 6, "round": 1 },
  "note": "E-4 fails: meta description not saved on reload"
}
```

- `slug` is the full ticket folder name, `NNN-slug`.
- `step` is one of `setup | building | testing | reviewing | fixing | done | blocked`.
- `stepStarted` is the ISO time the current step began. Set it to the same time as `updated` whenever `step` changes, and leave it alone otherwise.
- `updated` is the ISO time of this write.
- `evals.round` is the test round: 0 before the first test run, then one more each time the tester (or your own check run) reports.
- Update the file on every step change and at least every 10 minutes. A worker can't write it while it waits on its nested tester or reviewer, so the watchdog allows 30 minutes of silence in the `testing` and `reviewing` steps and 15 minutes in the others.

## Worker report

What a worker sends the router, at most 8 lines:

```
Ticket: NNN-slug: PASS x/y   (or FAIL x/y)
Branch: ...  Worktree: <abs path>
Changed for users: ...
Decisions I made that the ticket didn't cover: ... or none
Blocked / needs a decision: ... or nothing
```

Full detail lives in `specs/tickets/NNN-slug/results.md` on the branch. The router reads that and checks it against eval.md before anything gets merged. Follow-ups go back to the same worker, never to a fresh one.

## Who can run at the same time

- Solo workers: as many as the board allows, each in its own worktree.
- Merger, checker, reproducer: at most one of each at a time. They share the main checkout (merger, checker) or the fixed port 3090 (reproducer). The router queues the rest.
- Team: one at a time. While it runs, its uncommitted work sits in the main checkout, so the router queues every merger and checker run until the team is done. Solo workers and the reproducer keep running in their worktrees.

## Teams

Agent teams are turned on by `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`. Only the router (the main chat) can lead a team, and only one team runs at a time. Teammates work in the main checkout, each owning one block of Affected areas, and test on the main checkout's server on port 3000. While a team runs, the watchdog skips its browser walk and doesn't treat the app on 3000 being down as a fault unless a teammate's status file has also gone stale. When the team passes, the merger commits the work directly, since there's no branch.

## Safety

- `git push` is denied for every agent. Nothing leaves this machine until you push it yourself.
- Agents can't read `.env` or `.env.*` with the Read tool.
- The router has edit, write and shell tools only so that agent-team teammates (who run under its tool rules) can build. Its instructions forbid it from using them. Building happens in worktrees or the team, and only the merger writes to `main`.
- Workers can't finish until their evals pass and their branch is clean, unless they report `blocked` with a note saying why.
- Review what landed with `git log main` before you push.
