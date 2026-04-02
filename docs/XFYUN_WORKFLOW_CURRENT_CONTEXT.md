# XFYUN Workflow Current Context (Working Notes)

Last updated: 2026-03-16 (Asia/Shanghai)

Purpose: keep a durable, project-local snapshot of the currently used workflow setup so future debugging and development can quickly align with the same assumptions.

## 1) Active Integration Identity (non-secret)

- App name: `成电吃什么`
- Bound APPID: `7b367536`
- API endpoint: `https://xingchen-api.xf-yun.com/workflow/v1/chat/completions`
- Current Flow ID in project env: `7436739079683477504`

Security note:
- Do **not** store `API_KEY` / `API_SECRET` plaintext in repo docs.
- Secrets must stay in runtime env only (`backend/.env` locally, Render env in production).

## 2) Workflow Topology Snapshot

Observed graph (from current screenshots):
- `开始` (input: `AGENT_USER_INPUT`)
- `大模型_1`
- `变量提取器_1` (extracts: `campus`, `area`, `budget`, `people_count`, `scene`, `taste`, `dining_time`, `meal_type`, `preference`)
- `数据库_1` (SQL query against `canteen_agent_db`)
- `分支器_1`
- Branch A: `大模型_2` -> `结束`
- Branch B: `消息_1` -> `结束`

## 3) Start Node Contract Used by This Workflow

- Required input variable on start node: `AGENT_USER_INPUT` (String)
- Backend should always provide:
  - `parameters.AGENT_USER_INPUT = user_query`
- Optional compatibility alias supported by backend:
  - `parameters.query = user_query`

## 4) SQL/Branch Behavior (from screenshots)

`数据库_1` input references extracted fields (`campus`, `area`, `budget`, etc.) and outputs:
- `isSuccess` (Boolean)
- `message` (String)
- `outputList` (Array<Object>)

`分支器_1` appears to route by whether database output is empty:
- If empty -> `消息_1`
- Else -> `大模型_2`

`消息_1` content currently matches the repeated fallback text:
- “暂时没有找到完全符合你条件的店铺...（放宽条件建议）”

## 5) Important Diagnostic Finding

During direct API and backend tests, responses repeatedly showed:
- `code = 0`
- `finish_reason = stop`
- `workflow_step.seq = 1`
- output content equals `消息_1` fallback text

This suggests API calls are likely landing on a path/version that exits early (or immediately reaches the fallback path), rather than the expected full multi-node route seen in editor debug.

## 6) Reconciliation Checklist (when “editor debug success” but API output wrong)

1. Confirm API is using the **published** version of the same workflow (not editor draft runtime).
2. Confirm `Flow ID` in env exactly matches the published workflow.
3. Confirm start-node variable name exactly `AGENT_USER_INPUT`.
4. Confirm branch condition in `分支器_1` is correct and not inverted.
5. Confirm `消息_1` is only fallback branch output, not accidentally default route.
6. Confirm database node actually returns non-empty `outputList` for test query.
7. Validate with direct OpenAPI request (same `flow_id`, same input) and compare to editor run.

## 7) Project Implementation Status (code side)

Implemented in repository:
- Chat call: `/workflow/v1/chat/completions`
- Resume call: `/workflow/v1/resume`
- Upload call: `/workflow/v1/upload_file`
- History validation with role alternation and `content_type` support
- Stream and non-stream response parsing
- Frontend interrupt/resume interaction UI
- Request `parameters` passthrough support

If behavior still differs, prioritize workflow-side publish/version/branch checks.

## 8) Chinese Input Integrity Rule (Mandatory)

This project must preserve Chinese user input end-to-end without mojibake or replacement characters.

Required practices:
- Frontend JSON POST must use `Content-Type: application/json; charset=utf-8`.
- Backend workflow requests must use UTF-8 JSON semantics and must not intentionally degrade Chinese text.
- Primary workflow input must be passed through `parameters.AGENT_USER_INPUT` in original Chinese.
- Any debugging script used by the agent must avoid shell locale corruption:
  - Prefer Unicode literals / escaped Unicode strings in scripts when needed.
  - Avoid relying on terminal visual rendering as proof of payload correctness.
- If workflow trace shows `???` or replacement symbols, treat as a blocking issue and verify encoding path before other logic diagnosis.

Operational reminder for future runs:
- Use the exact Chinese query from user when reproducing.
- Record request `id` from API response and verify the same call in workflow trace.
