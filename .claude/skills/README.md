# Installed Skills

Project-level skills for Claude Code, vendored from five open-source skill collections. Claude Code auto-discovers every directory here that contains a `SKILL.md`.

## Sources

| Source | Skills | License |
|---|---|---|
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | `find-skills` | MIT |
| [obra/superpowers](https://github.com/obra/superpowers) | `brainstorming`, `writing-plans`, `executing-plans`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch`, `using-git-worktrees`, `dispatching-parallel-agents`, `subagent-driven-development`, `using-superpowers`, `writing-skills` | MIT |
| [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | `babysit`, `design-is`, `do`, `learn-codebase`, `make-plan`, `pathfinder`, `what-the`, `wowerpoint` | AGPL-3.0 |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | `impeccable` | Apache-2.0 |
| [rebelytics/one-skill-to-rule-them-all](https://github.com/rebelytics/one-skill-to-rule-them-all) | `task-observer` | MIT |

## When each skill is used

**Development workflow (superpowers)**
- `brainstorming` — refine an idea into a validated design before coding
- `writing-plans` / `executing-plans` — turn designs into step-by-step plans and execute them
- `test-driven-development` — RED/GREEN/REFACTOR discipline for new features and fixes
- `systematic-debugging` — root-cause process for any bug or unexpected behavior
- `verification-before-completion` — evidence-based "it works" checks before claiming done
- `requesting-code-review` / `receiving-code-review` — review etiquette and response process
- `finishing-a-development-branch` — merge/PR/cleanup checklist when work completes
- `using-git-worktrees` / `dispatching-parallel-agents` / `subagent-driven-development` — parallel and agent-driven execution
- `using-superpowers` — index/introduction to the workflow skills
- `writing-skills` — author or edit skills themselves

**Frontend design (impeccable)**
- `impeccable` — design, audit, polish, animate, or harden any UI. Sub-commands (`craft`, `audit`, `polish`, …) live in `impeccable/reference/`.

**Productivity (claude-mem)**
- `do` — capture a task now, do it at the right time
- `make-plan` — generate an actionable plan document
- `learn-codebase` / `pathfinder` — build understanding of an unfamiliar codebase
- `what-the` — explain surprising code or behavior
- `babysit` — supervise long-running work
- `design-is` — design principles reference
- `wowerpoint` — build HTML slide presentations

**Meta**
- `find-skills` — discover and install more skills from the open ecosystem (`npx skills`)
- `task-observer` — observes any multi-step task for patterns worth turning into new skills

## Not vendored

claude-mem's memory skills (`mem-search`, `timeline-report`, `standup`, `weekly-digests`, `smart-explore`, `knowledge-agent`, `oh-my-issues`, `how-it-works`) depend on the claude-mem plugin runtime (session hooks + SQLite memory database) and do not work as standalone skills. To get them, install the full plugin: see https://github.com/thedotmack/claude-mem#installation. Superpowers and impeccable also ship optional hooks/agents via their plugin marketplaces; the skills vendored here work without them.

## Updating

Skills are vendored snapshots (2026-07-05). To update, re-copy from the upstream repos or install upstream plugin versions and delete the vendored copies to avoid duplicates.
