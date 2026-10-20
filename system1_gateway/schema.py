"""Versioned, provider-neutral request/response schema.

Bump SCHEMA_VERSION only for breaking changes; add new optional fields without a bump.
"""

import math
import uuid
from dataclasses import dataclass, field

SCHEMA_VERSION = "1"
SUPPORTED_SCHEMA_VERSIONS = ("1",)

MAX_QUESTION_CHARS = 8000
MAX_OPTION_CHARS = 500
MIN_OPTIONS, MAX_OPTIONS = 2, 256  # room for a skill list; each provider enforces its own max_options
MAX_REQUEST_ID_CHARS = 128

# Error codes (stable, part of the v1 contract).
INVALID_REQUEST = "invalid_request"
CONFIG_ERROR = "config_error"
PROVIDER_TIMEOUT = "provider_timeout"
PROVIDER_ERROR = "provider_error"
MALFORMED_RESPONSE = "malformed_response"


class InvalidRequest(ValueError):
    pass


@dataclass(frozen=True)
class DecideRequest:
    question: str
    request_id: str
    options: list | None = None
    context: dict = field(default_factory=dict)
    min_confidence: float | None = None


REQUEST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": list(SUPPORTED_SCHEMA_VERSIONS), "default": SCHEMA_VERSION},
        "request_id": {"type": "string", "minLength": 1, "maxLength": MAX_REQUEST_ID_CHARS,
                       "description": "Optional caller-supplied id, echoed back. Generated if omitted."},
        "question": {"type": "string", "minLength": 1, "maxLength": MAX_QUESTION_CHARS,
                     "description": "The decision to make, phrased as a question."},
        "options": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": MAX_OPTION_CHARS},
                    "minItems": MIN_OPTIONS, "maxItems": MAX_OPTIONS, "uniqueItems": True,
                    "description": "Candidate answers. If given, the decision is exactly one of them."},
        "context": {"type": "object", "description": "Free-form structured context passed to the provider."},
        "min_confidence": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": "Abstain below this confidence. Defaults to the configured threshold."},
    },
    "required": ["question"],
    "additionalProperties": False,
}

RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "request_id": {"type": "string"},
        "status": {"type": "string", "enum": ["decided", "abstained", "error"]},
        "decision": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"]},
        "rationale": {"type": ["string", "null"]},
        "provider": {"type": ["string", "null"]},
        "probabilities": {"type": ["object", "null"], "additionalProperties": {"type": "number"},
                          "description": "Per-answer probabilities, when the provider reports them."},
        "calibrated": {"type": "boolean",
                       "description": "True when a fitted temperature was applied to probabilities and confidence."},
        "latency_ms": {"type": "integer"},
        "attempts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "outcome": {"type": "string", "enum": ["ok", "abstained", "timeout", "error", "malformed"]},
                "latency_ms": {"type": "integer"},
                "detail": {"type": ["string", "null"]},
            },
        }},
        "error": {"type": ["object", "null"], "properties": {
            "code": {"type": "string", "enum": [INVALID_REQUEST, CONFIG_ERROR, PROVIDER_TIMEOUT,
                                                PROVIDER_ERROR, MALFORMED_RESPONSE]},
            "message": {"type": "string"},
        }},
    },
    "required": ["schema_version", "request_id", "status", "latency_ms", "attempts", "error"],
}


def request_id_of(args) -> str:
    """The caller's request_id if usable, else a fresh one (so even invalid requests get an id)."""
    rid = args.get("request_id") if isinstance(args, dict) else None
    if isinstance(rid, str) and 0 < len(rid) <= MAX_REQUEST_ID_CHARS:
        return rid
    return uuid.uuid4().hex


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_request(args) -> DecideRequest:
    if not isinstance(args, dict):
        raise InvalidRequest("arguments must be an object")
    unknown = set(args) - set(REQUEST_JSON_SCHEMA["properties"])
    if unknown:
        raise InvalidRequest(f"unknown field(s): {', '.join(sorted(unknown))}")

    version = args.get("schema_version", SCHEMA_VERSION)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise InvalidRequest(f"unsupported schema_version {version!r}; supported: {list(SUPPORTED_SCHEMA_VERSIONS)}")

    rid = args.get("request_id")
    if rid is not None and not (isinstance(rid, str) and 0 < len(rid) <= MAX_REQUEST_ID_CHARS):
        raise InvalidRequest(f"request_id must be a string of 1-{MAX_REQUEST_ID_CHARS} characters")

    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        raise InvalidRequest("question must be a non-empty string")
    if len(question) > MAX_QUESTION_CHARS:
        raise InvalidRequest(f"question exceeds {MAX_QUESTION_CHARS} characters")

    options = args.get("options")
    if options is not None:
        if not isinstance(options, list) or not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise InvalidRequest(f"options must be a list of {MIN_OPTIONS}-{MAX_OPTIONS} strings")
        if not all(isinstance(o, str) and o.strip() and len(o) <= MAX_OPTION_CHARS for o in options):
            raise InvalidRequest(f"each option must be a non-empty string of at most {MAX_OPTION_CHARS} characters")
        if len(set(options)) != len(options):
            raise InvalidRequest("options must be unique")

    context = args.get("context", {})
    if not isinstance(context, dict):
        raise InvalidRequest("context must be an object")

    min_conf = args.get("min_confidence")
    if min_conf is not None and not (is_number(min_conf) and 0 <= min_conf <= 1):
        raise InvalidRequest("min_confidence must be a number between 0 and 1")

    return DecideRequest(
        question=question,
        request_id=request_id_of(args),
        options=list(options) if options is not None else None,
        context=context,
        min_confidence=float(min_conf) if min_conf is not None else None,
    )


def make_response(request_id, status, *, latency_ms, attempts=(), decision=None, confidence=None,
                  rationale=None, provider=None, probabilities=None, calibrated=False, error_code=None,
                  error_message=None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": status,
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale,
        "provider": provider,
        "probabilities": probabilities,
        "calibrated": calibrated,
        "latency_ms": latency_ms,
        "attempts": list(attempts),
        "error": {"code": error_code, "message": error_message} if error_code else None,
    }
