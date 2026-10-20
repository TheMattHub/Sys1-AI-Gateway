"""Provider-neutral decision flow: validate -> select -> timeout -> threshold/abstain -> fallback."""

import logging
import threading
import time

from . import __version__
from . import calibration as calibration_lib
from .config import Config, ConfigError, load_config
from .providers import REGISTRY, MalformedResponse
from .schema import (CONFIG_ERROR, INVALID_REQUEST, MALFORMED_RESPONSE, PROVIDER_ERROR, PROVIDER_TIMEOUT,
                     REQUEST_JSON_SCHEMA, RESPONSE_JSON_SCHEMA, SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS,
                     InvalidRequest, is_number, make_response, parse_request, request_id_of)

log = logging.getLogger("system1_gateway")

TOOL_NAMES = ("system1_decide", "system1_health", "system1_capabilities")


def _ms(since: float) -> int:
    return int((time.monotonic() - since) * 1000)


def call_with_timeout(fn, timeout_s: float):
    """Run fn() in a daemon thread; raise TimeoutError if it doesn't finish in time.

    ponytail: a Python thread can't be killed, so a timed-out call keeps running in the
    background until its own I/O timeout fires. Adapters must pass timeout_s to their I/O.
    Switch to a subprocess runner if an adapter ever blocks without one.
    """
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # re-raised in the caller's thread
            box["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise TimeoutError(f"no answer within {timeout_s}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def check_provider_output(raw, request) -> dict:
    """Gateway-side validation, so no adapter can leak a malformed answer to Claude."""
    if not isinstance(raw, dict):
        raise MalformedResponse(f"expected an object, got {type(raw).__name__}")
    rationale = raw.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise MalformedResponse("rationale must be a string")
    if raw.get("abstain") is True:
        return {"abstain": True, "rationale": rationale}
    decision, confidence = raw.get("decision"), raw.get("confidence")
    if not isinstance(decision, str) or not decision.strip():
        raise MalformedResponse("decision must be a non-empty string")
    if not (is_number(confidence) and 0 <= confidence <= 1):
        raise MalformedResponse(f"confidence must be a number in [0, 1], got {confidence!r}")
    if request.options is not None and decision not in request.options:
        raise MalformedResponse(f"decision {decision!r} is not one of the options")
    probs = raw.get("probabilities")
    if probs is not None:
        if not isinstance(probs, dict) or decision not in probs \
                or not all(isinstance(k, str) and is_number(v) and 0 <= v <= 1 for k, v in probs.items()):
            raise MalformedResponse("probabilities must map each answer (including the decision) to a number in [0, 1]")
        if request.options is not None and set(probs) != set(request.options):
            raise MalformedResponse("probabilities must cover exactly the options")
        probs = {k: float(v) for k, v in probs.items()}
    return {"abstain": False, "decision": decision, "confidence": float(confidence), "rationale": rationale,
            "probabilities": probs}


class Gateway:
    def __init__(self, config: Config | None = None, calibration: list | None = None):
        """calibration: entries as in calibration.load() (the default); [] turns calibration off."""
        self.calibration = calibration_lib.load() if calibration is None else calibration
        # Never raise here: a broken config must surface as config_error / health "down",
        # not as an MCP server that fails to start.
        self.config_errors = []
        if config is None:
            try:
                config = load_config()
            except ConfigError as e:
                self.config_errors.append(str(e))
                config = Config()
        self.config = config
        self.chain = []
        for name in [config.provider, *config.fallback]:
            cls = REGISTRY.get(name)
            if cls is None:
                self.config_errors.append(f"unknown provider {name!r}; available: {', '.join(sorted(REGISTRY))}")
                continue
            try:
                self.chain.append(cls(config.providers.get(name, {})))
            except (ValueError, TypeError) as e:
                self.config_errors.append(f"{name}: {e}")

    def decide(self, args, timeout_s: float | None = None) -> dict:
        """timeout_s: this call's limit per attempt; defaults to the configured one (decide_many passes what's left)."""
        started = time.monotonic()
        rid = request_id_of(args)
        if self.config.paused():
            return make_response(rid, "abstained", latency_ms=_ms(started),
                                 rationale="System-1 is paused (/system1:toggle on resumes it)")
        if self.config_errors:
            return make_response(rid, "error", latency_ms=_ms(started), error_code=CONFIG_ERROR,
                                 error_message="; ".join(self.config_errors))
        try:
            request = parse_request(args)
        except InvalidRequest as e:
            log.info("[%s] invalid request: %s", rid, e)
            return make_response(rid, "error", latency_ms=_ms(started), error_code=INVALID_REQUEST,
                                 error_message=str(e))
        log.debug("[%s] question=%r options=%r", rid, request.question, request.options)

        timeout_s = timeout_s or self.config.timeout_s
        threshold = request.min_confidence if request.min_confidence is not None else self.config.min_confidence
        attempts, last_error = [], None
        for provider in self.chain:
            attempt_started = time.monotonic()
            try:
                raw = call_with_timeout(lambda: provider.decide(request, timeout_s), timeout_s)
                result = check_provider_output(raw, request)
            except TimeoutError as e:
                outcome, code, detail = "timeout", PROVIDER_TIMEOUT, str(e)
            except MalformedResponse as e:
                outcome, code, detail = "malformed", MALFORMED_RESPONSE, str(e)
            except Exception as e:  # any adapter failure is a provider failure, never a server crash
                outcome, code, detail = "error", PROVIDER_ERROR, f"{type(e).__name__}: {e}"
            else:
                return self._finish(rid, provider, request, result, threshold, started, attempt_started, attempts)
            attempts.append({"provider": provider.name, "outcome": outcome,
                             "latency_ms": _ms(attempt_started), "detail": detail})
            last_error = (code, f"{provider.name}: {detail}")
            log.warning("[%s] %s %s: %s", rid, provider.name, outcome, detail)

        log.error("[%s] all providers failed", rid)
        return make_response(rid, "error", latency_ms=_ms(started), attempts=attempts,
                             error_code=last_error[0], error_message=last_error[1])

    def _finish(self, rid, provider, request, result, threshold, started, attempt_started, attempts) -> dict:
        """Calibrate and threshold one validated provider answer (shared by decide and decide_many)."""
        calibrated = self._calibrate(provider, request, result)
        # Low confidence is an answer ("I don't know"), not a failure: no fallback.
        confident = not result["abstain"] and result["confidence"] >= threshold
        detail = None if confident else (
            "provider abstained" if result["abstain"]
            else f"confidence {result['confidence']:.2f} < threshold {threshold:.2f}")
        attempts.append({"provider": provider.name, "outcome": "ok" if confident else "abstained",
                         "latency_ms": _ms(attempt_started), "detail": detail})
        log.info("[%s] %s by %s in %d ms%s", rid, "decided" if confident else "abstained",
                 provider.name, _ms(started), "" if confident else f" ({detail})")
        return make_response(
            rid, "decided" if confident else "abstained", latency_ms=_ms(started), attempts=attempts,
            decision=result["decision"] if confident else None,
            confidence=result.get("confidence"), rationale=result["rationale"], provider=provider.name,
            probabilities=result.get("probabilities"), calibrated=calibrated)

    def _one_by_one(self, requests: dict) -> dict:
        """decide() per question, within one timeout_s budget for all of them: once it is spent, the remaining
        questions are answered provider_timeout unasked, so a slow engine can't multiply a hook's wait."""
        out, started = {}, time.monotonic()
        for k, a in requests.items():
            left = self.config.timeout_s - (time.monotonic() - started)
            if out and left < 0.05:
                out[k] = make_response(request_id_of(a), "error", latency_ms=_ms(started), error_code=PROVIDER_TIMEOUT,
                                       error_message=f"question budget of {self.config.timeout_s}s spent")
            else:
                out[k] = self.decide(a, timeout_s=left)  # only what's left, so the loop never overruns
        return out

    def decide_many(self, requests: dict) -> dict:
        """Several questions about one state: key -> response, each shaped like decide()'s.

        A primary provider with its own decide_many() answers all of them in one call (one engine pass).
        Otherwise, and on a config error, a pause or an invalid request, each question goes through decide().
        ponytail: a failed batch is reported for every question without trying the fallback chain, so a down
        engine costs one timeout, not one per question. Add per-question fallback if a chain is ever configured.
        """
        provider = self.chain[0] if self.chain else None
        if self.config_errors or self.config.paused() or not hasattr(provider, "decide_many"):
            return self._one_by_one(requests)
        try:
            parsed = {k: parse_request(a) for k, a in requests.items()}
        except InvalidRequest:
            return self._one_by_one(requests)  # decide() reports which one is invalid
        rids = {k: request_id_of(a) for k, a in requests.items()}
        started, timeout_s = time.monotonic(), self.config.timeout_s
        try:
            raws = call_with_timeout(lambda: provider.decide_many(parsed, timeout_s), timeout_s)
            if not isinstance(raws, dict) or set(raws) != set(parsed):
                raise MalformedResponse("the batch answer must cover every question")
            results = {k: check_provider_output(raws[k], parsed[k]) for k in parsed}
        except TimeoutError as e:
            code, outcome, detail = PROVIDER_TIMEOUT, "timeout", str(e)
        except MalformedResponse as e:
            code, outcome, detail = MALFORMED_RESPONSE, "malformed", str(e)
        except Exception as e:  # any adapter failure is a provider failure, never a crash
            code, outcome, detail = PROVIDER_ERROR, "error", f"{type(e).__name__}: {e}"
        else:
            return {k: self._finish(rids[k], provider, req, results[k],
                                    req.min_confidence if req.min_confidence is not None else self.config.min_confidence,
                                    started, started, [])
                    for k, req in parsed.items()}
        log.warning("[batch] %s %s: %s", provider.name, outcome, detail)
        attempts = [{"provider": provider.name, "outcome": outcome, "latency_ms": _ms(started), "detail": detail}]
        return {k: make_response(rids[k], "error", latency_ms=_ms(started), attempts=list(attempts),
                                 error_code=code, error_message=f"{provider.name}: {detail}") for k in parsed}

    def _calibrate(self, provider, request, result: dict) -> bool:
        """Apply a matching temperature to result in place. The argmax is unchanged; confidence becomes trustworthy."""
        probs = result.get("probabilities")
        if result["abstain"] or not probs:
            return False
        entry = calibration_lib.find(self.calibration, provider.name, provider.capabilities().get("model"),
                                     request.question, len(probs))
        if entry is None:
            return False
        scaled = calibration_lib.scale(probs, entry["temperature"])
        result["probabilities"] = {k: round(v, 4) for k, v in scaled.items()}
        result["decision"] = max(scaled, key=scaled.get)
        result["confidence"] = round(scaled[result["decision"]], 4)
        return True

    def max_options(self) -> int | None:
        """The primary provider's option limit, or None when it declares none."""
        value = self.chain[0].capabilities().get("max_options") if self.chain else None
        return value if isinstance(value, int) else None

    def health(self) -> dict:
        providers = []
        for i, provider in enumerate(self.chain):
            started = time.monotonic()
            try:
                h = call_with_timeout(lambda: provider.health(self.config.timeout_s), self.config.timeout_s)
                ok = isinstance(h, dict) and h.get("ok") is True
                detail = h.get("detail") if isinstance(h, dict) else f"malformed health response: {h!r}"
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {e}"
            providers.append({"name": provider.name, "role": "primary" if i == 0 else "fallback",
                              "ok": ok, "latency_ms": _ms(started), "detail": detail})
        if self.config_errors or not providers:
            status = "down"
        elif providers[0]["ok"]:
            status = "ok"
        else:
            status = "degraded" if any(p["ok"] for p in providers) else "down"
        if self.config.paused():
            status = "paused"
        return {"status": status, "gateway_version": __version__, "schema_version": SCHEMA_VERSION,
                "config_file": self.config.source or None, "config_errors": self.config_errors,
                "providers": providers}

    def capabilities(self) -> dict:
        return {
            "gateway_version": __version__,
            "schema_versions": list(SUPPORTED_SCHEMA_VERSIONS),
            "tools": list(TOOL_NAMES),
            "provider": self.config.provider,
            "fallback": self.config.fallback,
            "timeout_s": self.config.timeout_s,
            "min_confidence": self.config.min_confidence,
            "providers": {p.name: p.capabilities() for p in self.chain},
            "calibration": [{k: e.get(k) for k in ("provider", "model", "question", "n_options", "temperature",
                                                   "n_samples", "fitted_at")} for e in self.calibration],
            "available_providers": sorted(REGISTRY),
            "config_errors": self.config_errors,
            "request_schema": REQUEST_JSON_SCHEMA,
            "response_schema": RESPONSE_JSON_SCHEMA,
        }
