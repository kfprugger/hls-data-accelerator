# Project profile

**Profile:** not filled in

Every agent in this setup reads this file for the things that depend on your project: how to install, lint, build and start it, how to make a test account, and which user flows matter most. It ships empty on purpose. The first time you run `/write-tickets`, Claude reads your project, replaces every placeholder in double curly braces, shows you the result, and sets the line above to `**Profile:** filled in` once you confirm. The router won't route anything until it says `filled in`.

Wherever a command below needs a port, write `<port>`. Agents swap in their own (see Ports). Any command your project doesn't have is written as `none`, and agents skip that step.

- **App type:** {{web app | API | CLI or library}}. A web app gets browser checks with agent-browser. An API gets `curl` checks. A CLI or library has no server: its Start command is `none`, and its checks and Core flows are commands.

## The app

- **What it is:** {{one line a new teammate would understand, e.g. "a drag-and-drop landing-page builder"}}
- **Stack:** {{language, framework and version, database}}
- **Codebase map:** {{where to start reading, e.g. "README.md has the map; app code is in src/"}}
- **Read before writing code:** {{docs that override what a model knows, e.g. "AGENTS.md, then node_modules/next/dist/docs/ for any Next.js API"; or "none"}}

## Commands

| What | Command |
|---|---|
| Install | {{e.g. `npm install`}} |
| Lint | {{e.g. `npm run lint`, or "none"}} |
| Build | {{e.g. `npm run build`, or "none"}} |
| Tests | {{e.g. `npm test`, or "none"}} |
| Start the app on a port | {{e.g. `PORT=<port> npm run dev -- -p <port>`, or `none` for a CLI or library}} |
| App is up when | {{e.g. `curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/login` prints 200 (pick a page that returns 200 without signing in), or `none`}} |

- **Fresh worktree setup:** {{what a brand-new copy of the repo needs before it runs, e.g. "`npm install`; the database creates itself on first request"}}. A new worktree has none of your gitignored files, and agents can't read `.env`. If the app needs `.env` to start, list it in a `.worktreeinclude` file at the project root (same syntax as `.gitignore`) and Claude Code copies it into every new worktree.
- **Local data is per folder:** {{yes / no. Yes when each worktree gets its own database (e.g. SQLite in ./data). No when every copy shares one database server: then test account names must be unique across tickets, and the team and reproducer accounts below should change to names no ticket number can produce, e.g. `team` and `repro`.}}
- **One dev server per folder:** {{yes / no. Yes for Next.js (it locks `.next/dev/lock`). This is why a team ticket shares the main checkout's server.}}
- **Build and dev server can run together in one folder:** {{yes / no}}

## Ports

| Who | Port | Where |
|---|---|---|
| Main checkout (you, checker, watchdog, team tickets) | 3000 | the project folder |
| Worker on ticket NNN | 3100 + NNN (004 → 3104) | its worktree |
| Reproducer | 3090 | its worktree |

Change these only if something else on your machine already uses them, and change them in the router's prompt too.

## Test accounts

- **How to create one:** {{exact steps with `<name>` in place of the account name, e.g. "open http://localhost:<port>/signup, fill Email `<name>@test.local`, Username `<name>`, Password `testpass123`, click **Create account**, land on /dashboard". If the app has no accounts, write "none".}}
- **How to sign in to an existing one:** {{e.g. "http://localhost:<port>/login with the same email and password"}}
- **Names:** worker on ticket NNN → `tNNN`; team → `t050`; reproducer → `t090`; checker and watchdog → `t000`.
- **Extra URLs agents should know:** {{e.g. "published sites are at http://<username>.localhost:<port>; on any port other than 3000 start the app with `NEXT_PUBLIC_ROOT_DOMAIN=localhost:<port>`"; or "none"}}

## Core flows

The flows a user can't live without. The checker walks them after every merge, and the watchdog walks them every few rounds, the way a first-time user would. Keep it to 3 to 6 flows, each one line of real steps.

1. {{e.g. Sign up, log out, log back in.}}
2. {{e.g. Create a page, add two blocks, change a field, reload: the changes are still there.}}
3. {{e.g. Publish the page and open the published site: content matches the editor.}}

## Patterns reviewers check

Project rules the reviewer holds every change to. Only ones that cause real bugs or duplication when broken.

- {{e.g. "Block fields live in lib/blocks/schema.ts so the inspector and sanitizer pick them up"}}
- {{e.g. "Every data read and write is scoped to the signed-in user"}}

## Files

- **Never commit:** `.job/`, `.claude/worktrees/`, {{e.g. `node_modules/`, `.next/`, `data/`, `.env*`}}
- **Files tools rewrite on their own** (commit them with the work if they change, never count them as drift): {{e.g. "AGENTS.md and tsconfig.json, rewritten by `next dev`"; or "none"}}
