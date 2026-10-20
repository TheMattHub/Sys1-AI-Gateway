# Tools and schema

The gateway exposes three MCP tools over stdio, and their contract is schema version `"1"`. New optional
fields can be added without a version bump; a breaking change bumps it. The request and response JSON
Schemas are published at [schema/request.json](https://thematthub.github.io/Sys1-AI-Gateway/schema/request.json)
and [schema/response.json](https://thematthub.github.io/Sys1-AI-Gateway/schema/response.json), written from
[schema.py](../../system1_gateway/schema.py) at build time, and `system1_capabilities` returns the same.

## system1_decide

Asks the configured provider for one decision.

| Field | Required | Notes |
|---|---|---|
| `question` | yes | non-empty string, at most 8,000 characters |
| `options` | no | 2 to 256 unique non-empty strings of at most 500 characters; the decision is exactly one of them. Without options the question is answered yes or no. Each provider may set a lower limit (Laya: 20) |
| `context` | no | object, passed to the provider |
| `min_confidence` | no | number in [0, 1]; overrides the configured threshold |
| `request_id` | no | 1 to 128 characters, echoed back; generated if omitted |
| `schema_version` | no | `"1"` |

Unknown fields are rejected with `invalid_request`.

| Response field | Meaning |
|---|---|
| `status` | `decided`, `abstained` or `error` |
| `decision` | one of the options, or `null` when abstained or on error |
| `confidence` | probability of the decision, after calibration when one matches |
| `probabilities` | per-option probabilities, when the provider reports them |
| `calibrated` | `true` when a fitted temperature was applied |
| `rationale`, `provider` | the provider's explanation and name |
| `latency_ms` | total time |
| `attempts` | every provider tried: `provider`, `outcome` (`ok`, `abstained`, `timeout`, `error`, `malformed`), `latency_ms`, `detail` |
| `error` | `null`, or `{"code", "message"}` |
| `schema_version`, `request_id` | as sent, or generated |

Error codes: `invalid_request`, `config_error`, `provider_timeout`, `provider_error`, `malformed_response`.

## system1_health

Returns `status` (`ok`; `degraded` when the primary is down and a fallback is up; `down`; or `paused`), the
gateway and schema versions, the config file read, any `config_errors`, and a probe for each provider in the
chain (`name`, `role`, `ok`, `latency_ms`, `detail`).

## system1_capabilities

Returns the gateway version, schema versions, tool names, provider chain, timeout and threshold, each
provider's capabilities (for example `max_options`), the calibration fits loaded, the available providers,
any config errors, and the full request and response JSON Schemas.

## Behaviour

- **Validation on both sides:** requests are checked before any provider runs, and provider answers are
  checked by the gateway: a non-object, a confidence outside [0, 1], or a decision not in `options` is
  `malformed_response`.
- **Abstention:** if the provider abstains, or its confidence is below the threshold, `status` is
  `abstained` and `decision` is `null`. It means "reason it through yourself", and it does not trigger a
  fallback.
- **Fallback:** runs only on a timeout, an error or a malformed answer, trying providers in order; every try
  is recorded in `attempts`.
- **Timeouts** apply to each attempt.
- **Paused:** while `/system1:toggle off` is in effect, `system1_decide` abstains with a rationale saying so.
- **Logs** go to stderr, since stdout carries the protocol; every line carries the request id.
