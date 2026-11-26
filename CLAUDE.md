# Claude working rules — llmDietPlanner (Uvařto)

## Model routing

Start at the lowest tier that can do the job; move up only if the result is shaky. The main session runs on the user's chosen model. These tiers apply to subagents and delegated work.

| Tier | Use for |
|---|---|
| **fable** | Expensive-if-wrong judgment: architecture and design, security review, correctness review of risky diffs, `qa-tester` verdicts, recipe/nutrition/pricing logic with safety or money impact, subtle or cross-system bugs |
| **opus** | Multi-file features, Django + React refactors, non-trivial migrations, implementation plans, tricky fixes once the root cause is known |
| **sonnet** | Routine feature and bug work within one area, tests, frontend components, copy edits |
| **haiku** | Lookups, broad search, log summaries, mechanical edits (renames, formatting, bulk replace), commit message drafts |

- When spawning a subagent, set its `model` parameter and state the choice and why. For agents in `.claude/agents/`, set the `model:` frontmatter.

## Skills and tools

- Check for a matching skill before starting and use it. Examples: `superpowers:systematic-debugging` for bugs, `superpowers:test-driven-development` for features and bugfixes, `superpowers:verification-before-completion` before claiming done, `qa-prod` after a production deploy.
- Skip skills for small docs edits and one-line fixes.
- If work repeats and no skill exists, propose `anthropic-skills:skill-creator` rather than re-explaining it.
- Load a deferred tool's schema with ToolSearch before calling it.

## Project basics

- Production deploys from the `prod` branch, not `develop`.
- Never push `.do/app.yaml`. It is a stale placeholder and would break prod.
- Commit and push only when asked.
- Deeper stack and deploy details live in the personal memory index, not in this repo. Keep that data out of this file.
