# XFYUN Workflow API Integration Contract

This document is the source of truth for this repository's XFYUN workflow integration.
All future frontend/backend changes must remain compatible with this contract.

Companion runtime/context notes:
- `docs/XFYUN_WORKFLOW_CURRENT_CONTEXT.md` (current workflow snapshot, topology, and diagnostics)

## 1) Chat Workflow Endpoint

- Method: `POST`
- URL: `https://xingchen-api.xf-yun.com/workflow/v1/chat/completions`
- Auth header: `Authorization: Bearer {API_KEY}:{API_SECRET}`
- `stream` supports both `true` and `false`

Core request fields:
- `flow_id` (required)
- `uid` (optional)
- `parameters` (required)
- `ext` (optional)
- `stream` (required)
- `chat_id` (optional)
- `history` (optional)

## 2) Start Node Input Contract

User message must be passed via:
- `parameters.AGENT_USER_INPUT`

Example:

```json
{
  "flow_id": "...",
  "parameters": {
    "AGENT_USER_INPUT": "你好"
  },
  "stream": true
}
```

## 3) History Contract

- `history` is an array of message objects
- Each item includes:
  - `role`: `user` | `assistant`
  - `content_type`: `text` | `image`
  - `content`: string
- First item must be `user`
- Sequence must follow alternating dialogue order: `user -> assistant -> user -> assistant`

## 4) Response Contract

Common top-level fields:
- `code`
- `message`
- `id`
- `created`
- `workflow_step`
- `choices`
- `usage` (optional; usually in final frame)
- `event_data` (optional; used for interrupts)

Main model output location:
- `choices[0].delta.content`

`finish_reason` values:
- `stop`
- `interrupt`
- `ping`

## 5) Streaming Behavior (`stream=true`)

- Response arrives as incremental frames
- Final frame should include `finish_reason="stop"` and `usage`
- Parsers must support frame-based merge and finalization logic

## 6) Non-Streaming Behavior (`stream=false`)

- Final content is returned in:
  - `choices[0].delta.content`

## 7) Interrupt Behavior

Workflow can pause on Q&A nodes. Interrupt payload contains:
- `event_data.event_id`
- `event_data.event_type = "interrupt"`
- `event_data.need_reply`
- `event_data.value.type = direct | option`
- `event_data.value.content`
- `event_data.value.option` (for option mode)

## 8) Resume Endpoint

- Method: `POST`
- URL: `https://xingchen-api.xf-yun.com/workflow/v1/resume`
- Auth header: `Authorization: Bearer {API_KEY}:{API_SECRET}`

Request body:
- `event_id`
- `event_type` (`resume` / `ignore` / `abort`)
- `content`

This endpoint is required to continue execution after interrupts.

## 9) File Upload Endpoint

- Method: `POST`
- URL: `https://xingchen-api.xf-yun.com/workflow/v1/upload_file`
- Auth header: `Authorization: Bearer {API_KEY}:{API_SECRET}`
- Content type: `multipart/form-data`

Used to upload files and consume returned `data.url`.

## 10) Error Handling Rules

### Workflow errors
- `20201`, `20202`, `20204`, `20207`

### Auth / rate-limit errors
- `20900`, `20901`, `20902`, `20903`

### Model / service errors
- `20303`, `20357`, `20358`, `20363`, `20364`, `20369`, `20372`, `20373`, `20374`, `20375`, `20376`, `20380`

### Node execution errors
- `22600`, `22601`, `22701`, `21900`, `21600`, `22801`, `23100`, `23300`, `23800`

### Session errors
- `20804`, `23900`

Implementation guidance:
- Preserve raw error `code` + `message`
- Do not collapse all failures into generic text
- Keep retry logic scoped to transient network/timeout classes, not protocol/business contract errors

## 11) Project Integration Guidance (Required)

For this repository:
- Workflow response is the source of truth
- Parse `choices[0].delta.content` carefully and defensively
- If published workflow returns structured JSON, frontend should parse it safely
- Interrupt events must not be ignored; they require resume handling
- Future changes must preserve compatibility with this API structure

## 12) Required Constraints for Future Changes

- Do not invent incompatible request/response assumptions
- Do not replace workflow content with ad-hoc mock/fallback output in normal flow
- Keep `AGENT_USER_INPUT` contract intact unless workflow start-node contract is intentionally versioned and documented
- Any contract change must update this file and relevant implementation notes together

---

## Appendix A: Original Raw Protocol Notes

The following raw notes are preserved for verification and traceability.

```text
XFYUN WORKFLOW API SOURCE OF TRUTH

1. Chat workflow endpoint
- Method: POST
- URL: https://xingchen-api.xf-yun.com/workflow/v1/chat/completions
- Auth: Bearer {API_KEY}:{API_SECRET}
- stream: true or false supported
- Core request fields:
  - flow_id
  - uid (optional)
  - parameters (required)
  - ext (optional)
  - stream (required)
  - chat_id (optional)
  - history (optional)

2. Start-node input contract
- Workflow requests must send the user message into the start node via:
  parameters.AGENT_USER_INPUT
- Example:
  {
    "flow_id": "...",
    "parameters": {
      "AGENT_USER_INPUT": "你好"
    },
    "stream": true
  }

3. History contract
- history is an array of message objects
- each object includes:
  - role: user | assistant
  - content_type: text | image
  - content: string
- first history item must be user
- sequence must follow user -> assistant -> user -> assistant

4. Response contract
- Common top-level fields:
  - code
  - message
  - id
  - created
  - workflow_step
  - choices
  - usage (optional, usually final frame)
  - event_data (optional for interrupts)
- Main response payload is in:
  choices[0].delta.content
- finish_reason can be:
  - stop
  - interrupt
  - ping

5. Streaming behavior
- Streaming returns incremental frames
- Final frame includes finish_reason="stop" and usage
- Frontend/backend must support stream parsing correctly if stream=true

6. Non-stream behavior
- Non-stream returns final content in:
  choices[0].delta.content

7. Interrupt behavior
- Workflow may be interrupted when a Q&A node is reached
- Interrupt response contains:
  - event_data.event_id
  - event_data.event_type = "interrupt"
  - event_data.need_reply
  - event_data.value.type = direct | option
  - event_data.value.content
  - event_data.value.option (if option mode)

8. Resume endpoint
- Method: POST
- URL: https://xingchen-api.xf-yun.com/workflow/v1/resume
- Auth: Bearer {API_KEY}:{API_SECRET}
- Request body:
  - event_id
  - event_type (resume / ignore / abort)
  - content
- This endpoint is required to continue execution after interrupt events

9. File upload endpoint
- Method: POST
- URL: https://xingchen-api.xf-yun.com/workflow/v1/upload_file
- Auth: Bearer {API_KEY}:{API_SECRET}
- Content-Type: multipart/form-data
- Used for uploading files and receiving data.url

10. Error handling rules
Document and preserve important error classes, especially:
- workflow errors:
  - 20201, 20202, 20204, 20207
- auth/rate limit errors:
  - 20900, 20901, 20902, 20903
- model/service errors:
  - 20303, 20357, 20358, 20363, 20364, 20369, 20372, 20373, 20374, 20375, 20376, 20380
- node execution errors:
  - 22600, 22601, 22701, 21900, 21600, 22801, 23100, 23300, 23800
- session errors:
  - 20804, 23900

11. Integration guidance for this project
Please explicitly document that:
- The workflow response should be treated as the source of truth
- Frontend/backend should parse choices[0].delta.content carefully
- If the workflow is published with structured JSON output, the frontend should parse that JSON safely
- Interrupt events must not be ignored; they require resume handling
- Future code changes must preserve compatibility with this workflow API structure

12. Repo instruction update
Update AGENTS.md (or equivalent repo instruction file) with a short but clear rule such as:
- This project integrates with XFYUN workflow API
- Future code must follow the documented workflow contract
- Respect AGENT_USER_INPUT, response parsing, interrupt/resume handling, and error semantics
- Do not invent incompatible request/response assumptions
```

---

## Appendix B: Spark X Deep Reasoning HTTP API Contract (Updated: 2026-02-09)

This section is a required contract when this repo runs in `spark_local` recommendation mode.

### B.1 Endpoint and Model Mapping

- X2 endpoint: `https://spark-api-open.xf-yun.com/x2/chat/completions`
- X1.5 endpoint: `https://spark-api-open.xf-yun.com/v2/chat/completions`
- For both endpoints, current model value must be:
  - `model = "spark-x"`

OpenAI SDK compatible base URLs:
- X2: `https://spark-api-open.xf-yun.com/x2/`
- X1.5: `https://spark-api-open.xf-yun.com/v2/`

### B.2 Authentication

- Header:
  - `Authorization: Bearer {APIpassword}`
  - `Content-Type: application/json`
- `APIpassword` is from Spark HTTP service console.
- Compatibility note: `Bearer {APIKey}:{APISecret}` may also work in some environments, but project standard for Spark HTTP is `APIpassword`.

### B.3 Request Body (Non-stream/Stream)

Required:
- `model` (`spark-x`)
- `messages` (array)

Common optional:
- `user`
- `stream`
- `temperature`
- `top_p`
- `top_k`
- `presence_penalty`
- `frequency_penalty`
- `max_tokens`
- `tools`
- `tool_choice`
- `thinking` (`enabled | disabled | auto`)

Reference request:

```json
{
  "model": "spark-x",
  "user": "user_id",
  "messages": [
    {
      "role": "user",
      "content": "推荐两个国内适合自驾的景点"
    }
  ],
  "stream": true,
  "thinking": { "type": "enabled" }
}
```

### B.4 Response Contract

Top-level fields:
- `code` (0 means success)
- `message`
- `sid` (request trace id)
- `choices`
- `usage` (usually final)

Non-stream content path:
- `choices[0].message.content`
- Reasoning model may also include:
  - `choices[0].message.reasoning_content`

Stream content path (SSE):
- `choices[0].delta.content`
- Reasoning stream:
  - `choices[0].delta.reasoning_content`

### B.5 FunctionCall / Tools

When function call is enabled, model may return:
- `choices[0].message.tool_calls[]`
  - `id`
  - `type = "function"`
  - `function.name`
  - `function.arguments`

Streaming tool-calls may arrive in `choices[0].delta.tool_calls[]` chunks.

### B.6 Error Codes to Preserve

- `0`: success
- `10007`: request overlap (must wait previous completion)
- `10013`: input moderation blocked
- `10014`: output moderation blocked
- `10019`: risky/violation tendency
- `10907`: token over limit
- `11200`: no auth or quota exceeded
- `11201`: daily limit exceeded
- `11202`: QPS/second-level limit exceeded
- `11203`: concurrency limit exceeded

### B.7 Project Integration Rules (Spark Mode Required)

When `RECOMMEND_PROVIDER=spark_local`:
- Use Spark endpoint + `model="spark-x"` as mandatory contract.
- Preserve `sid` in backend response `raw.sid` for troubleshooting.
- Parse model output defensively (`choices[0].message.content` first, fallback to delta when needed).
- If model outputs fenced JSON, strip fences before frontend parsing.
- Keep UTF-8 end-to-end; Chinese input/output corruption (`???`, mojibake) is a blocker.
- Keep workflow and spark contracts separated; do not mix field assumptions across APIs.
