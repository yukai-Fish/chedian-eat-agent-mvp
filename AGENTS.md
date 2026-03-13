# AGENTS.md

## Local Skill Convention

This repository uses repo-local skills under:

- `.agents/skills`

Do not use or create a competing `.codex/skills` folder inside this repo.

## Skill Preference

For frontend and UI work, prefer these local skills first:

1. `vercel-react-best-practices`
- React frontend architecture
- React/Next performance patterns
- data fetching and rendering efficiency

2. `vercel-composition-patterns`
- component composition and page structure
- compound components and scalable component APIs
- avoiding boolean-prop anti-patterns

3. `next-best-practices`
- Next.js best practices and app/router conventions
- use this if present; otherwise fall back to `vercel-react-best-practices`

4. `webapp-testing`
- web app testing and UI testing
- behavior checks, interaction regression checks, and browser-based validation

5. `interaction-design`
- UI behavior refinement
- motion/hover/focus states, dropdowns/popovers, transitions, skeleton/loading polish

When tasks match these areas, load and follow the relevant skill `SKILL.md` before implementation.

## XFYUN Workflow Contract (Required)

This project integrates with the XFYUN Workflow API as a core backend contract.

All future code changes must follow:
- [docs/XFYUN_WORKFLOW_API.md](docs/XFYUN_WORKFLOW_API.md)

Required constraints:
- Respect `parameters.AGENT_USER_INPUT` start-node input contract.
- Parse workflow output from `choices[0].delta.content` with protocol-compatible logic.
- Preserve interrupt/resume semantics (`interrupt` -> `/workflow/v1/resume`).
- Preserve error code semantics; do not replace contract-level failures with incompatible assumptions.
- Do not invent request/response shapes that conflict with the documented API contract.
