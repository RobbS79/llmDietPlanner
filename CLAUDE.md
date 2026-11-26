# Claude working rules for llmDietPlanner (Uvařto)

## Model routing

Pick the model by how hard the task is to get wrong. Use the Agent tool's `model` parameter for subagents. For agent definitions in `.claude/agents/`, set the `model:` frontmatter.

| Model | Use for |
|---|---|
| **fable** (Fable 5.2) | Judgment-heavy work where a wrong call is expensive: architecture and design decisions, security review, correctness review of risky diffs, production QA verdicts (`qa-tester`), recipe/nutrition/pricing logic with safety or money impact, debugging subtle or cross-system failures. |
| **opus** (Opus 5.5) | Complex implementation: multi-file features, refactors across Django + React, non-trivial migrations, writing implementation plans, tricky bug fixes after a root cause is known. |
| **sonnet** (Sonnet 5.5) | Routine feature work and bug fixes within one area, writing and updating tests, frontend component work, copy edits, most day-to-day coding. |
| **haiku** (Haiku 5.5) | Fast lookups, broad file/symbol search, log and output summarising, mechanical edits (renames, formatting, bulk find-and-replace), commit message drafts. |

Rules:
- Do not default to the most capable model. Start at the lowest tier that can do the task, and move up if the result is shaky.
- The main session runs on whatever model the user chose. Routing applies to subagents and delegated work.
- Name the model you chose and why when you spawn a subagent.

## Skills and tools

- Before starting a task, check whether a listed skill covers it, and use it. Examples: `superpowers:systematic-debugging` for bugs, `superpowers:test-driven-development` for features and bugfixes, `superpowers:verification-before-completion` before claiming done, `qa-prod` after a production deploy.
- If the work repeats and no skill exists, propose creating one (`anthropic-skills:skill-creator`) instead of re-explaining it each time.
- If a needed tool is deferred, load its schema with ToolSearch before calling it.
- Skip skills for small docs edits and one-line fixes.

## Project basics

- Stack and deployment details are in memory (`project-overview`, `deployment`, `tech-stack`). Production deploys from the `prod` branch, not `develop`.
- Never push `.do/app.yaml` (see memory `recipe-curation-trigger`).
- Commit and push only when asked.
