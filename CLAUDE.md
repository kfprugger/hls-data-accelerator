## Working on this project

- **Work happens through tickets.** Two steps: write the tickets in a normal chat with the `write-tickets` skill (`specs/tickets/NNN-slug/rd.md` + `eval.md`, approved from `draft` to `ready`), then start the router with `claude --agent router --name router --permission-mode auto`. The router is the only session you run: it starts its own background watchdog and the agents that build the tickets. Don't build an unticketed feature on `main`.
- **Agent setup.** Who does what, how to run it, the ticket format, the status file and the worker report are all in `.claude/README.md`. The project's commands, test accounts and core flows are in `.claude/project.md`.
- **Ports.** The main checkout runs on 3000. A worker on ticket NNN uses 3100 + NNN and the reproducer uses 3090, each in its own worktree. A team ticket works in the main checkout and uses its server on 3000. Start the app on any port with the start command in `.claude/project.md`.
- **Browser checks** use agent-browser. Run `agent-browser skills get core` before first use, use your own named session (`--session <name>`), and save screenshots to `specs/tickets/NNN-slug/evidence/`.
