# AGENTS.md — driving app-insight from a coding agent

This file is for any coding agent (Claude Code, Codex CLI, Gemini CLI, Cursor, ...). The tool is deterministic:
**you run it, read its summary, and report what it says. You never decide a fact, a state or a severity yourself.**

## What it does

`app-insight` reads an organisation's application repositories and produces, per application, the AS-IS
inventory and an aspect trace: aspect → control → state → evidence → finding → remedy. It also builds a portfolio
report (`report.html`). Nothing is built, run or queried in the target repositories; no model is used.

## Commands

Run from this folder with `bin/app-insight` (or `python3 -m app_insight` with this folder on `PYTHONPATH`).

| Goal | Command |
|---|---|
| Check prerequisites | `bin/app-insight doctor` |
| See how inputs will be read (no fetching) | `bin/app-insight sources <inputs...>` |
| Scan | `bin/app-insight scan <inputs...> --client <name> [--remedies modernise-plugin,generic]` |
| Summary of the latest run | `bin/app-insight summary ~/app-insight-workspaces/<client> [--json]` |
| Rebuild after changing packs | `bin/app-insight aspects <run-dir or workspace> [--remedies ...]` |
| Rebuild the HTML only | `bin/app-insight report <run-dir or workspace>` |

Inputs can be mixed: repository paths, a folder holding repositories, remote URLs (`https://`, `ssh://`, `git@host:`),
or list files (`.csv`, `.tsv`, `.xlsx`, `.txt`). In lists, the repository column is the first one named url, repo,
repository, git, clone_url, path or location; optional columns are name, branch, team, criticality.

## Rules for agents

1. **Ask for the client name** if the user did not give one; it selects an isolated workspace. Never mix clients.
2. **Never put credentials on the command line or in a list file.** Remote clones use the user's own git setup (SSH
   agent or credential helper). If a clone fails for authentication, report it and ask the user to fix access.
3. **Read the `━━ APP-INSIGHT-SUMMARY ━━` block** (or `summary --json`) and report from it. Quote states as written:
   `ABSENT` means "not found in the files read", not "missing in production"; `NOT_ASSESSED` and `UNKNOWN` are never
   a pass.
4. **Do not invent remedies, effort, dates or business value.** Remedies come from the client's remedy packs.
5. **Do not edit the target repositories** while scanning. Fixing a gap is a separate task the user asks for.
6. Point the user to `report.html` for the full trace; open it only if asked.

## Where things are

| Path | What |
|---|---|
| `app_insight/cli.py` | Commands and workspace layout |
| `app_insight/sources.py` | Reading list files, cloning and refreshing remotes |
| `app_insight/aspects.py` | Builds `aspects.json` (the trace) from the engine's outputs |
| `app_insight/packs/aspects.v1.json` | Aspect and control catalogue: what is checked, where the answer comes from, when it applies |
| `app_insight/packs/remedies/*.json` | Remedy packs, one per organisation or tool set |
| `app_insight/report.py`, `app_insight/ui/` | The HTML report |
| `engine/` | Analysis engine (discovery, relationship graph, resilience, safety net, dimensions), copied from app-modernise `skills/app-discovery` at `1eeaad1` |

## Workspace layout (per client)

```
~/app-insight-workspaces/<client>/
  client.json            remedy packs for this client
  repos/<slug>/          shallow clones of remote repositories
  runs/<timestamp>/      run.json (inputs, per-source status), analysis/ (engine output + aspects.json), report.html
  latest                 name of the latest run
```

## Changing the product

- Run `python3 -m unittest discover -s tests` and `(cd engine && python3 -m unittest discover -s tests)` before and after.
- A new control goes in `packs/aspects.v1.json`; if it needs new evidence, add a detector to the engine first and
  keep the control `pending` (NOT_ASSESSED) until it exists.
- Do not add a dependency outside the Python standard library without agreement.
