#!/usr/bin/env node
// Watchdog first pass. Run from the project root:
//   node .claude/watchdog/check.mjs          problems only
//   node .claude/watchdog/check.mjs --tick   one round line first, then problems
//
// With --tick, the first line is {"kind":"tick","round":n}. n goes up by one on
// every --tick run and is kept as "round" in .job/watchdog-state.json. Runs
// without --tick don't change it.
//
// Then it prints only problems, one JSON object per line:
//   {"kind":"stale|slow|blocked|drift|app-down|app-not-running|team-active","ticket":"004","detail":"..."}
// Prints nothing when all is well. Always exits 0. Warnings (for example an
// unreadable RULES.md) go to stderr, never stdout.
//
// "team-active" is not a fault: it says a team ticket is in progress in the
// main checkout (some .job/status-*.json has a step other than "done"). While
// that is true, app-health problems on the main app are held back, and only
// printed (as app-down) when a teammate's status file is also stale.
//
// Thresholds come from the first ```json block in .claude/watchdog/RULES.md.
// The stale limit is per step: staleMinutesByStep[step], else staleMinutes.
// Step start times come from status.stepStarted when present; otherwise they,
// and the eval-round history, are kept between runs in .job/watchdog-state.json
// in the main checkout. Eval rounds come from status.evals.round when present.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULTS = {
  staleMinutes: 15,
  staleMinutesByStep: { testing: 30, reviewing: 30 },
  slowStepMinutes: 45,
  evalRoundsWithoutProgress: 3,
  appUrl: "http://localhost:3000",
  healthPaths: ["/"],
  healthTimeoutSeconds: 30,
  browserWalkEveryNRounds: 3,
  repeatReportAfterMinutes: 60,
  driftIgnore: [".job/"],
  // Used by the watchdog agent, not by this script. Listed here only so a
  // wrong type in RULES.md gets a warning.
  roundIntervalMinutes: 10,
  restartAfterRounds: 24,
};

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TICK = process.argv.slice(2).includes("--tick");
const NOW = Date.now();
const MIN = 60 * 1000;
const NOT_RUNNING_CODES = new Set(["ECONNREFUSED", "ENOTFOUND", "EADDRNOTAVAIL", "EHOSTUNREACH"]);

const problems = [];
let pendingTick = "";

function warn(msg) {
  process.stderr.write(`check.mjs warning: ${msg}\n`);
}

function minutes(ms) {
  return Math.max(0, Math.round(ms / MIN));
}

function readJson(file) {
  try {
    return { ok: true, value: JSON.parse(fs.readFileSync(file, "utf8")) };
  } catch (err) {
    if (err && err.code === "ENOENT") return { ok: false, missing: true };
    return { ok: false, missing: false };
  }
}

function git(cwd, args) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 15000,
    });
  } catch {
    return null;
  }
}

// ---------- config ----------

function loadConfig() {
  let text;
  try {
    text = fs.readFileSync(path.join(HERE, "RULES.md"), "utf8");
  } catch {
    warn("RULES.md not found next to check.mjs; using built-in defaults.");
    return { ...DEFAULTS };
  }
  const match = text.match(/```json[^\n]*\n([\s\S]*?)\n```/);
  if (!match) {
    warn("no ```json block in RULES.md; using built-in defaults.");
    return { ...DEFAULTS };
  }
  try {
    const parsed = JSON.parse(match[1]);
    const cfg = { ...DEFAULTS };
    for (const key of Object.keys(DEFAULTS)) {
      if (parsed[key] === undefined) continue;
      if (typeof parsed[key] !== typeof DEFAULTS[key] || Array.isArray(parsed[key]) !== Array.isArray(DEFAULTS[key])) {
        warn(`RULES.md value "${key}" has the wrong type; using the default (${JSON.stringify(DEFAULTS[key])}).`);
        continue;
      }
      cfg[key] = parsed[key];
    }
    // staleMinutesByStep must map step names to positive numbers.
    const byStep = {};
    for (const [step, value] of Object.entries(cfg.staleMinutesByStep || {})) {
      if (typeof value === "number" && value > 0) byStep[step] = value;
      else warn(`RULES.md staleMinutesByStep.${step} is not a positive number; using staleMinutes for that step.`);
    }
    cfg.staleMinutesByStep = byStep;
    return cfg;
  } catch (err) {
    warn(`the json block in RULES.md is not valid JSON (${err.message}); using built-in defaults.`);
    return { ...DEFAULTS };
  }
}

// ---------- worktrees ----------

function listWorktrees() {
  const raw = git(process.cwd(), ["worktree", "list", "--porcelain"]);
  if (raw === null) return null;
  const entries = [];
  let cur = null;
  for (const line of raw.split("\n")) {
    if (line.startsWith("worktree ")) {
      cur = { dir: line.slice("worktree ".length), branch: null, bare: false, prunable: false };
      entries.push(cur);
    } else if (!cur) {
      continue;
    } else if (line.startsWith("branch ")) {
      cur.branch = line.slice("branch ".length).replace(/^refs\/heads\//, "");
    } else if (line === "bare") {
      cur.bare = true;
    } else if (line.startsWith("prunable")) {
      cur.prunable = true;
    }
  }
  return entries;
}

function guessTicket(...hints) {
  for (const h of hints) {
    const m = String(h ?? "").match(/(?:^|[^0-9])(\d{3})(?:[^0-9]|$)/);
    if (m) return m[1];
  }
  return "";
}

function normTicket(value, ...hints) {
  if (value === undefined || value === null || value === "") return guessTicket(...hints);
  const s = String(value).trim();
  return /^\d+$/.test(s) ? s.padStart(3, "0") : s;
}

// ---------- state between runs ----------

function loadState(file) {
  const r = readJson(file);
  const state = r.ok && r.value && typeof r.value === "object" ? r.value : {};
  state.workers ||= {};
  state.reports ||= {};
  return state;
}

function saveState(file, state) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(state, null, 2) + "\n");
  } catch (err) {
    warn(`could not save ${file} (${err.message}); step timings will restart next run.`);
  }
}

// ---------- reporting with repeat tracking ----------

function makeReporter(state) {
  const seen = new Set();
  function report(kind, ticket, key, detail) {
    const sig = `${kind}|${key}`;
    seen.add(sig);
    const first = state.reports[sig];
    if (first) {
      detail += ` (first flagged ${minutes(NOW - first)} min ago)`;
    } else {
      state.reports[sig] = NOW;
    }
    problems.push({ kind, ticket: ticket || "", detail });
  }
  function finish() {
    for (const sig of Object.keys(state.reports)) if (!seen.has(sig)) delete state.reports[sig];
  }
  return { report, finish };
}

// ---------- status checks ----------

function staleLimit(cfg, step) {
  const own = cfg.staleMinutesByStep?.[step];
  return typeof own === "number" && own > 0 ? own : cfg.staleMinutes;
}

// True when an active (not done/blocked) status hasn't been updated within its step's limit.
function isStale(status, cfg) {
  const step = typeof status.step === "string" ? status.step : "";
  if (step === "done" || step === "blocked") return false;
  const updated = Date.parse(status.updated);
  return !step || Number.isNaN(updated) || NOW - updated > staleLimit(cfg, step) * MIN;
}

function checkStatus({ key, label, status, prev, cfg, report }) {
  const ticket = status.ticket;
  const step = typeof status.step === "string" ? status.step : "";
  const updated = Date.parse(status.updated);
  const active = step !== "done" && step !== "blocked";
  const limit = staleLimit(cfg, step);
  const next = { step, since: prev?.since ?? null, evalRound: prev?.evalRound, evalTuple: prev?.evalTuple, best: prev?.best ?? null, stuck: prev?.stuck ?? 0 };

  if (step === "blocked") {
    const note = typeof status.note === "string" && status.note.trim() ? status.note.trim() : "no note given";
    report("blocked", ticket, key, `${label} is blocked: ${note}`);
  }

  if (!step) {
    report("stale", ticket, key, `${label} status file has no step`);
  }

  if (active) {
    if (Number.isNaN(updated)) {
      report("stale", ticket, key, `${label} status file has no valid "updated" time`);
    } else if (NOW - updated > limit * MIN) {
      report("stale", ticket, key, `${label} has not updated its status for ${minutes(NOW - updated)} min (limit ${limit} for this step), last step "${step}"`);
    }
  }

  // When did the current step start? Prefer an explicit field, then what we
  // saw on earlier runs, then the update time of the status that changed step.
  const explicit = Date.parse(status.stepStarted ?? status.stepSince ?? "");
  if (!Number.isNaN(explicit)) {
    next.since = explicit;
  } else if (!prev || prev.step !== step || !prev.since) {
    next.since = Number.isNaN(updated) ? NOW : Math.min(updated, NOW);
  }
  if (active && step && next.since && NOW - next.since > cfg.slowStepMinutes * MIN) {
    report("slow", ticket, key, `${label} has been on step "${step}" for ${minutes(NOW - next.since)} min (limit ${cfg.slowStepMinutes})`);
  }

  // Eval rounds: count a new round when evals.round changes (if workers
  // provide it), otherwise when the eval numbers change or the worker moves
  // into "fixing".
  const evals = status.evals && typeof status.evals === "object" ? status.evals : null;
  const failed = Number(evals?.failed);
  const total = Number(evals?.total);
  if (evals && Number.isFinite(failed) && Number.isFinite(total) && total > 0) {
    const tuple = `${evals.passed}/${failed}/${total}`;
    let newRound;
    if (evals.round !== undefined && evals.round !== null) {
      newRound = String(evals.round) !== String(prev?.evalRound ?? "");
      next.evalRound = String(evals.round);
    } else {
      newRound = tuple !== prev?.evalTuple || (step === "fixing" && prev?.step !== "fixing");
    }
    next.evalTuple = tuple;
    if (newRound) {
      if (next.best === null || failed < next.best) {
        next.best = failed;
        next.stuck = 0;
      } else {
        next.stuck += 1;
      }
    }
    if (step !== "done" && failed > 0 && next.stuck >= cfg.evalRoundsWithoutProgress) {
      report("slow", ticket, key, `${label} failing checks are not going down: ${failed} of ${total} failing after ${next.stuck} rounds without improvement (best so far ${next.best})`);
    }
  }

  return next;
}

// ---------- drift ----------

function findRd(root, status, ticket) {
  const ticketsDir = path.join(root, "specs", "tickets");
  const candidates = [];
  if (status.slug) {
    candidates.push(String(status.slug));
    if (ticket) candidates.push(`${ticket}-${status.slug}`);
  }
  if (ticket) {
    try {
      for (const name of fs.readdirSync(ticketsDir)) if (name.startsWith(`${ticket}-`)) candidates.push(name);
    } catch {
      // no specs/tickets folder
    }
  }
  for (const name of candidates) {
    const rd = path.join(ticketsDir, name, "rd.md");
    if (fs.existsSync(rd)) return { rd, folder: `specs/tickets/${name}/` };
  }
  return null;
}

function parseAffectedAreas(text) {
  const lines = text.split("\n");
  const areas = [];
  let inSection = false;
  for (const line of lines) {
    if (/^##\s+/.test(line) && !/^###/.test(line)) {
      inSection = /^##\s+Affected areas\b/i.test(line);
      continue;
    }
    if (!inSection) continue;
    const item = line.match(/^\s*[-*]\s+(.*)$/);
    if (!item) continue;
    const ticks = [...item[1].matchAll(/`([^`]+)`/g)].map((m) => m[1].trim());
    const picked = ticks.length ? ticks : [item[1].split(/:\s|\s[—-]\s/)[0].trim()];
    for (const p of picked) {
      if (!p || /\s/.test(p) || /^none$/i.test(p)) continue;
      areas.push(p);
    }
  }
  return areas;
}

function areaMatcher(area) {
  const clean = area.replace(/^\.\//, "").replace(/\/+$/, "");
  const escaped = clean.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const glob = escaped.replace(/\\\*\\\*/g, ".*").replace(/\\\*/g, "[^/]*");
  return new RegExp(`^${glob}(/.*)?$`);
}

function changedFiles(root, base) {
  const files = new Set();
  const committed = git(root, ["diff", "--name-only", `${base}...HEAD`]);
  if (committed === null) return null;
  for (const f of committed.split("\n")) if (f.trim()) files.add(f.trim());
  const status = git(root, ["status", "--porcelain=v1", "-uall"]);
  if (status !== null) {
    for (const line of status.split("\n")) {
      if (line.length < 4) continue;
      let f = line.slice(3);
      if (f.includes(" -> ")) f = f.split(" -> ").pop();
      f = f.replace(/^"(.*)"$/, "$1");
      if (f) files.add(f);
    }
  }
  return [...files];
}

function checkDrift({ key, label, root, status, ticket, base, cfg, report }) {
  const found = findRd(root, status, ticket);
  if (!found) return;
  let text;
  try {
    text = fs.readFileSync(found.rd, "utf8");
  } catch {
    return;
  }
  const areas = parseAffectedAreas(text);
  if (!areas.length) return;
  const matchers = areas.map(areaMatcher);
  const files = changedFiles(root, base);
  if (!files) return;
  const outside = files.filter((f) => {
    if (f.startsWith(found.folder)) return false;
    if (cfg.driftIgnore.some((ig) => f === ig.replace(/\/+$/, "") || (ig.endsWith("/") ? f.startsWith(ig) : f.startsWith(`${ig}/`)))) return false;
    return !matchers.some((re) => re.test(f));
  });
  if (!outside.length) return;
  const shown = outside.slice(0, 6).join(", ");
  const more = outside.length > 6 ? ` (+${outside.length - 6} more)` : "";
  report("drift", ticket, key, `${label} changed ${outside.length} file(s) outside its Affected areas: ${shown}${more}`);
}

// ---------- app health ----------

async function checkApp(cfg, report) {
  const base = String(cfg.appUrl).replace(/\/+$/, "");
  const paths = cfg.healthPaths;
  if (!paths.length) return; // no server to check (CLI or library)
  for (let i = 0; i < paths.length; i++) {
    const p = paths[i].startsWith("/") ? paths[i] : `/${paths[i]}`;
    try {
      const res = await fetch(base + p, {
        redirect: "follow",
        signal: AbortSignal.timeout(cfg.healthTimeoutSeconds * 1000),
      });
      try {
        await res.arrayBuffer();
      } catch {
        // body read failure doesn't change the status we got
      }
      if (res.status !== 200) {
        report("app-down", "", `app${p}`, `${base}${p} returned HTTP ${res.status}`);
      }
    } catch (err) {
      const code = err?.cause?.code || err?.code || "";
      if (i === 0 && NOT_RUNNING_CODES.has(code)) {
        report("app-not-running", "", "app", `nothing is answering at ${base} (${code}); health checks skipped`);
        return;
      }
      const reason = err?.name === "TimeoutError" ? `no response within ${cfg.healthTimeoutSeconds}s` : code || err?.message || "request failed";
      report("app-down", "", `app${p}`, `${base}${p} failed: ${reason}`);
    }
  }
}

// ---------- main ----------

async function main() {
  const cfg = loadConfig();
  const worktrees = listWorktrees();
  const mainEntry = worktrees && worktrees.length ? worktrees[0] : null;
  const mainRoot = mainEntry ? mainEntry.dir : process.cwd();
  const base = mainEntry?.branch || "main";
  const stateFile = path.join(mainRoot, ".job", "watchdog-state.json");
  const state = loadState(stateFile);

  // Round counter. Saved straight away, so the round still counts even if a
  // later check throws. The tick line itself is printed at the end, together
  // with the problem lines, so the Monitor delivers them as one event (it only
  // batches lines that arrive within 200 ms of each other). If a check throws,
  // the catch handler below still prints it.
  if (TICK) {
    const prevRound = Number(state.round);
    state.round = Number.isInteger(prevRound) && prevRound > 0 ? prevRound + 1 : 1;
    saveState(stateFile, state);
    pendingTick = JSON.stringify({ kind: "tick", round: state.round }) + "\n";
  }

  // Tickets marked done on the board. A team status file left behind by a
  // finished team ticket must not hold back app health forever.
  const doneTickets = new Set();
  try {
    const board = fs.readFileSync(path.join(mainRoot, "specs", "tickets", "BOARD.md"), "utf8");
    for (const line of board.split("\n")) {
      const cells = line.split("|").map((c) => c.trim());
      if (cells.length > 3 && /^\d+$/.test(cells[1]) && /^done$/i.test(cells[3])) doneTickets.add(cells[1].padStart(3, "0"));
    }
  } catch {
    // no board yet
  }

  const { report, finish } = makeReporter(state);
  const nextWorkers = {};

  if (worktrees === null) warn("not a git repository (or git failed); worktree checks skipped.");

  // Worker worktrees (everything except the main checkout).
  for (const wt of (worktrees || []).slice(1)) {
    if (wt.bare || wt.prunable || !fs.existsSync(wt.dir)) continue;
    const key = wt.dir;
    const dirName = path.basename(wt.dir);
    const r = readJson(path.join(wt.dir, ".job", "status.json"));
    if (!r.ok) {
      const ticket = guessTicket(wt.branch, dirName);
      const label = `worktree ${dirName}${wt.branch ? ` (branch ${wt.branch})` : ""}`;
      if (r.missing) {
        let created = NOW;
        try {
          const st = fs.statSync(wt.dir);
          created = st.birthtimeMs || st.mtimeMs;
        } catch {
          // keep NOW
        }
        if (NOW - created > cfg.staleMinutes * MIN) {
          report("stale", ticket, key, `${label} has no .job/status.json, ${minutes(NOW - created)} min after it was created`);
        }
      } else {
        report("stale", ticket, key, `${label} has a .job/status.json that is not valid JSON`);
      }
      continue;
    }
    const status = r.value && typeof r.value === "object" ? r.value : {};
    const ticket = normTicket(status.ticket, status.slug, wt.branch, dirName);
    status.ticket = ticket;
    const label = ticket ? `ticket ${ticket}` : `worktree ${dirName}`;
    nextWorkers[key] = checkStatus({ key, label, status, prev: state.workers[key], cfg, report });
    checkDrift({ key, label, root: wt.dir, status, ticket, base, cfg, report });
  }

  // Team members' status files in the main checkout.
  const jobDir = path.join(mainRoot, ".job");
  let teamFiles = [];
  try {
    teamFiles = fs.readdirSync(jobDir).filter((f) => /^status-.+\.json$/.test(f));
  } catch {
    // no .job folder yet
  }
  // A team is in progress while any team status file has a step other than "done".
  const teamActive = []; // { name, ticket }
  const teamStale = []; // names of active teammates whose status file is stale or unreadable
  for (const file of teamFiles.sort()) {
    const name = file.slice("status-".length, -".json".length);
    const key = `team:${name}`;
    const r = readJson(path.join(jobDir, file));
    if (!r.ok) {
      if (!r.missing) {
        report("stale", guessTicket(name), key, `team member ${name}: .job/${file} is not valid JSON`);
        teamActive.push({ name, ticket: guessTicket(name) });
        teamStale.push(name);
      }
      continue;
    }
    const status = r.value && typeof r.value === "object" ? r.value : {};
    const ticket = normTicket(status.ticket, status.slug, name);
    status.ticket = ticket;
    if (ticket && doneTickets.has(ticket)) continue; // finished team ticket: leftover file
    const label = ticket ? `ticket ${ticket} team member ${name}` : `team member ${name}`;
    nextWorkers[key] = checkStatus({ key, label, status, prev: state.workers[key], cfg, report });
    if (status.step !== "done") {
      teamActive.push({ name, ticket });
      if (isStale(status, cfg)) teamStale.push(name);
    }
  }

  if (!teamActive.length) {
    await checkApp(cfg, report);
  } else {
    const tickets = [...new Set(teamActive.map((t) => t.ticket).filter(Boolean))].join(", ") || "?";
    const members = teamActive.map((t) => t.name).join(", ");
    problems.push({
      kind: "team-active",
      ticket: tickets,
      detail: `team ticket ${tickets} is in progress in the main checkout (members: ${members}); skip the browser walk, app health on ${cfg.appUrl} is held back`,
    });
    // Collect app-health results, and pass them on only if the team has also gone quiet.
    const held = [];
    await checkApp(cfg, (kind, ticket, key, detail) => held.push({ kind, ticket, key, detail }));
    if (teamStale.length) {
      for (const h of held) {
        const why = `while team ticket ${tickets} is in progress and ${teamStale.join(", ")} ha${teamStale.length > 1 ? "ve" : "s"} a stale status file`;
        report("app-down", h.ticket || tickets, h.key, `${h.detail.replace(/; health checks skipped$/, "")} (${why})`);
      }
    }
  }

  state.workers = nextWorkers;
  finish();
  saveState(stateFile, state);

  flushOutput();
}

function flushOutput() {
  let out = pendingTick;
  pendingTick = "";
  for (const p of problems.splice(0)) out += JSON.stringify(p) + "\n";
  if (out) process.stdout.write(out);
}

main()
  .catch((err) => {
    warn(`unexpected error: ${err?.stack || err}`);
    flushOutput();
  })
  .finally(() => {
    process.exitCode = 0;
  });
