---
name: write-tickets
description: Turn feature requests into tickets that workers can build in parallel without asking questions. Each feature gets its own folder with rd.md (the requirements) and eval.md (a concrete, pass/fail way to check the feature was built correctly, including agent-browser checks). Tickets start as draft and only become ready after the user approves them, and a board shows which tickets can run at the same time. Use this skill whenever the user asks to write tickets, spec out or scope a feature, write requirements, a PRD or acceptance criteria, break a feature list into work items, or plan features before building them, even if they never say "ticket". Use it whenever the user lists one or more things they want built and wants them written down rather than coded right away.
---

# Write Tickets

Turn each feature the user asks for into a ticket: a folder holding two files.

- **rd.md**: the requirements. What to build and why, specific enough that someone could build it without asking follow-up questions.
- **eval.md**: the check. Concrete steps that anyone, human or agent, can run on the finished work to get a clear pass or fail on each requirement, without having to judge for themselves.

The two files work as a pair. rd.md says what "done" means. eval.md proves it. Every requirement needs at least one eval, and every eval checks at least one requirement. A requirement with no eval won't get checked, and an eval with no requirement checks scope nobody asked for.

This skill writes tickets. It does not build the features. Stop after writing the tickets unless the user also asks you to build them.

**Who reads these tickets.** Each ticket is handed to a separate worker agent. The workers run at the same time, each in its own copy of the project, and **they can't ask anyone a question while they work**. So a ticket has to settle every decision up front. Anything left open, the worker will guess, and different workers will guess differently. That's why this skill interviews the user before writing anything (step 3), marks which tickets can safely run together (step 7), and only lets a ticket be handed out after the user approves it (step 8).

## Workflow

### 0. First run only: fill in the project profile

Every agent that builds these tickets reads `.claude/project.md` for the project's commands, ports, test accounts and core flows. If its `**Profile:**` line says `not filled in`, or it still contains `{{`, fill it in before writing any ticket:

1. Read the project: the manifest and scripts (`package.json`, `Makefile`, `pyproject.toml`, …), README, AGENTS.md / CLAUDE.md, `.env.example`, the routes or entry points, and how the app is started. If a lint, build or test command doesn't exist, write "none" rather than inventing one.
2. Replace every `{{…}}` with the real value for this project. Keep the Ports table as it is unless something on this machine already uses those ports.
3. If there is a start command, check it really works on another port: start the app on 3199 in the background, run the "App is up when" check, then stop it. Fix the command (or pick a different page for the check) until it passes.
4. If the app needs a gitignored file such as `.env` to start, check that a `.worktreeinclude` file at the project root lists it. If not, propose adding one (it uses `.gitignore` syntax and makes Claude Code copy those files into every new worktree).
5. Bring the watchdog's numbers in line with the profile: in the ```json block of `.claude/watchdog/RULES.md`, set `healthPaths` to the page(s) the "App is up when" check uses (`[]` if the start command is `none`), add every file under "Files tools rewrite on their own" to `driftIgnore`, and change `appUrl` if the main checkout's port isn't 3000. Keep the block valid JSON.
6. Show the user the filled-in profile and ask them to confirm or correct it, especially the **Core flows** (the checker and watchdog walk these after every merge) and the **Patterns reviewers check**.
7. Once they confirm, set the line to `**Profile:** filled in`. Also make sure `.job/` and `.claude/worktrees/` are in `.gitignore`, and add them if not.

Skip this step when the profile already says `filled in`.

### 1. Split the request into features

One ticket per feature. A feature is the smallest piece that can be shipped and checked on its own and that is worth something to a user.

- "Add auth and a dashboard" is two tickets.
- "Add a button, and make the button save the form" is one ticket, because the button is useless without the saving.
- A large epic ("build a CRM") becomes several tickets. Tell the user how you split it, so they can merge or split tickets differently if they want.

If one ticket needs another to be done first, record that under Dependencies in its rd.md.

### 2. Read the codebase first

Tickets based on the real code are much more useful than generic ones. Before writing, look at:

- The stack, plus the scripts in `package.json` / `Makefile` / `pyproject.toml` (dev server, build, lint, test commands). eval.md should use the project's real commands.
- The files, routes, components, data models and APIs the feature will touch. Name them in rd.md under Affected areas.
- Patterns already in use (state management, styling, data fetching, test framework). Requirements shouldn't conflict with these without a stated reason.
- Any project docs (README, AGENTS.md, CLAUDE.md, framework docs in `node_modules`) that affect how the feature must be built.

Keep this short. You're checking enough to write precise tickets, not auditing the whole repo.

### 3. Interview the user until nothing is left to guess

Workers can't ask questions later, so settle everything now. Interview the user about each feature, **one question at a time**. When there's a choice, offer the options (with your recommendation first) rather than an open question. Keep going until a worker could build the feature without making any decision that changes what the user sees or gets.

- Ask about anything that changes the feature itself: who it's for, what happens on each path, what the user sees, what happens when it fails.
- Don't ask about things the codebase already answers (step 2). Follow the existing patterns.
- Small details that don't change the outcome (a variable name, an internal file layout) you can decide yourself. Write every one of those under **Decisions made** in rd.md, so the user can see and overrule them in step 8.

### 4. Choose the location and number

Tickets go in `specs/tickets/` at the project root.

```
specs/tickets/
├── 001-user-login/
│   ├── rd.md
│   └── eval.md
└── 002-task-board-drag-drop/
    ├── rd.md
    └── eval.md
```

The folder name is `NNN-short-kebab-slug`. Find the highest number already in `specs/tickets/` and continue from it, so older tickets are never overwritten. If a ticket for the same feature already exists, update it rather than making a duplicate, and tell the user you did.

### 5. Write rd.md

Use this template. Leave out a section only if it really has nothing to say. Write "None" rather than padding a section with filler.

```markdown
# NNN: <Feature title>

**Status:** draft

## Summary
One or two sentences: what this feature is and who it is for.

## Why
The problem it solves or the value it adds. This tells the builder what to favour when a detail isn't covered here.

## User stories
- As a <user>, I want <capability>, so that <benefit>.

## Functional requirements
- **FR-1**: <One specific, testable behaviour. Use "must". Say what input or action produces what observable result.>
- **FR-2**: ...

## Non-functional requirements
- **NFR-1**: <Performance, accessibility, security, responsiveness, browser support, etc. Only the ones that matter for this feature, each with a measurable limit.>

## Edge cases & error handling
- <Empty states, invalid input, network failure, permissions, limits, and what must happen in each case.>

## Out of scope
- <Things a reader might expect but that are deliberately excluded. This stops scope creep and stops the eval from checking them.>

## Affected areas
- `path/to/file-or-dir`: <what changes there>

## Do not touch
- `path/to/file-or-dir`: <areas the worker must leave alone, especially ones another ticket owns>

## Dependencies
- <Other tickets, services, env vars, packages. Or "None".>

## Decisions made
- **Agreed with the user**: <every answer from the interview, in one line each>
- **Decided by the ticket writer**: <every small call you made yourself, so the user can overrule it>
```

There is no "open questions" section. A ticket with an open question isn't finished: go back to step 3 and ask it.

Rules for a good requirement:
- **Testable.** "Must be fast" fails this rule. "Search results must appear within 300 ms for up to 1,000 items" passes.
- **Behaviour, not implementation.** Say what the system does. Name a specific library or approach only when the user or the codebase requires it.
- **One behaviour per FR**, so each can pass or fail separately.

### 6. Write eval.md

This file matters most, because it is what decides whether the feature counts as done. Write it so that someone who has never seen the conversation or the code can run it and get a clear pass or fail on each requirement.

```markdown
# NNN: <Feature title>: Evaluation

## Setup
Exact steps to get to a state where the checks can run: install, env vars, seed data, start command (e.g. `npm run dev`, then open http://localhost:3000/tasks).
The checks may run in a fresh copy of the project with no local data and with other copies running at the same time. So the setup must create everything from scratch (test accounts, pages, seed data), and it must start the dev server with the start command from `.claude/project.md` on `<port>`, never a fixed port.

## Automated checks
Commands that must succeed, plus any tests the builder must add:
- <Lint command from .claude/project.md> exits 0
- <Build command from .claude/project.md> exits 0
- <Tests command from .claude/project.md> passes, including new tests for FR-x
(Write the real commands. Leave out any line whose command is `none` in project.md.)

## Acceptance checks

### E-1: <short name> (covers FR-1)
- **Type**: automated | browser | API | CLI
- **Steps**:
  1. <exact action: click, request, command, with real values>
  2. ...
- **Expected**: <observable, binary result: exact text, status code, element state, file contents, count>

### E-2: ...

## Edge case checks
### E-N: <edge case> (covers FR-x / edge case list)
...

## Regression checks
- <Existing behaviour near this feature that must still work, and how to confirm it.>

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-4 |
| FR-2        | E-2   |
| NFR-1       | E-5   |

## Definition of done
- [ ] All automated checks pass
- [ ] All acceptance checks E-1…E-N pass
- [ ] No items from "Out of scope" were built
```

What makes an eval concrete:

| Vague (don't write) | Concrete (write this) |
|---|---|
| "Validation works correctly" | "Submit the form with Title empty. Expected: the form is not submitted, and the text `Title is required` appears under the Title field." |
| "The API handles errors" | "`curl -X POST localhost:3000/api/tasks -H 'Content-Type: application/json' -d '{}'` returns status 400 with body `{\"error\":\"title_required\"}`." |
| "Drag and drop is smooth" | "Drag card 'A' from To Do to Done. Expected: 'A' shows in Done, To Do's count drops by 1, and after a page reload 'A' is still in Done." |
| "It's responsive" | "At 375px viewport width, there is no horizontal scrollbar and the nav collapses into a menu button." |

Guidelines:
- Use real values: real routes, real selectors or visible text, real commands from this repo, real sample data. Placeholders like `<some value>` make an eval impossible to run.
- Check things that last, not just how the screen looks right now (reload the page, restart, look at storage) whenever the requirement involves saving data.
- Where an automated test makes sense, describe the test the builder should write: file location, what it asserts. Then the eval can be re-run later.
- If a requirement can only be checked by human judgment (e.g. a visual style), say so clearly and give the most objective criteria you can (reference screenshot, specific colours or tokens, spacing values).
- Fill in the Traceability table last and use it as a self-check. Any FR or NFR without an eval is a gap you should fix before finishing.
- **For an API or a CLI/library** (project.md's App type), write `API` or `CLI` checks: the exact command and the exact expected output or status code. The rest of this bullet is for web apps.
- **Anything a user does in a web app is a `browser` check that the worker runs itself with agent-browser** (the browser CLI the workers use). Write the steps as what to open, what to click or type, and what must appear, using real URLs, visible text and values. Use the test account and URLs from `.claude/project.md`, with `<port>` and `tNNN` as placeholders that the worker swaps for its own. If you're unsure of an agent-browser command, run `agent-browser skills get core` (its built-in usage guide) rather than guessing.
- Include regression checks in the browser for the neighbouring features this ticket could break, not just the feature itself.

### 7. Check which tickets can run at the same time

Workers each build in their own copy of the project, and the copies get merged back afterwards. Two tickets that change the same files will clash when they're merged. After writing all the tickets, and before reporting back:

1. Compare the **Affected areas** of every ticket, including tickets already marked ready.
2. If two tickets change the same file or shared piece (a schema, a shared component, a route, the database), either move that change into one ticket and list it under **Do not touch** in the other, or mark the second ticket as **waits for NNN**.
3. Decide each ticket's **Mode**. Use `team` when the ticket has separate parts that must agree on a shared shape to work at all (for example, tracking on the published site + storing it + showing it in the dashboard, which all have to agree on what one record looks like). Otherwise use `solo`. For a `team` ticket, split rd.md's Affected areas into one block per part, so each teammate owns different files.
4. Write `specs/tickets/BOARD.md` in exactly this format (the router reads it, see `.claude/README.md`):

   ```markdown
   | # | Title | Status | Mode | Runs |
   |---|---|---|---|---|
   | 001 | Pricing monthly/yearly toggle | draft | solo | alongside |
   | 002 | SEO settings per page | draft | solo | waits for 001: both change the published-page route |
   ```

### 8. Approval: draft → ready

Every ticket starts as **Status: draft**. Only **ready** tickets get handed to workers.

- Walk the user through each draft: the summary, the **Decisions made** list, and the board.
- Apply any changes they ask for, then re-run step 7 if the affected areas changed.
- Mark a ticket **Status: ready** (in rd.md and in BOARD.md) only when the user approves that ticket. Never mark one ready on your own.

### 9. Report back

When the tickets are written, give the user a short summary:
- Each ticket's path and a one-line description
- How you split the request, if it wasn't obvious
- Every decision you made on your own, so they can overrule it
- The board: which tickets run together and which wait
- Which tickets are still draft

Don't paste the full files into chat. They're on disk.
