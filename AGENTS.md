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
- Preserve Chinese input integrity end-to-end (UTF-8/Unicode-safe handling); treat any `???`/mojibake in workflow trace as a blocker before business-logic debugging.

## XFYUN Spark X HTTP Contract (Required in spark_local mode)

When recommendation provider is Spark direct mode (`RECOMMEND_PROVIDER=spark_local`), all future changes must follow:
- [docs/XFYUN_WORKFLOW_API.md](docs/XFYUN_WORKFLOW_API.md) Appendix B

Mandatory constraints:
- Endpoint/model pairing must be protocol-correct:
  - X2: `https://spark-api-open.xf-yun.com/x2/chat/completions`
  - X1.5: `https://spark-api-open.xf-yun.com/v2/chat/completions`
  - model: `spark-x`
- Use Spark HTTP `APIpassword` auth (`Authorization: Bearer {APIpassword}`) by default.
- Preserve `sid` in backend raw payload for traceability.
- Parse non-stream output from `choices[0].message.content` (with defensive fallbacks).
- Preserve UTF-8 Chinese integrity end-to-end; any mojibake is a release blocker.

## Identity Baseline (Required)

Current product baseline is anonymous identity first:
- Generate and persist a stable `anonymousId` per browser/device.
- Do not require login for recommendation, feedback, or ranking interactions.
- Pass identity metadata through writes/events where supported.

Future authentication upgrades must preserve backward compatibility:
- Keep historical anonymous feedback/event records queryable after auth is introduced.
- Avoid breaking schema/API assumptions that currently rely on `anonymousId`.
