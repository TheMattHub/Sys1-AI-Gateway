"""Von adapter (wfzyx/von, `von serve`), verified against von-sdk 1.3.1 on 2026-09-30.

Contract:
  POST {endpoint}/v1/systemone
       {"model": "von-1.3", "state": {...},
        "questions": {key: {"type": "choice", "instructions": str, "criteria": {option: description}}}}
    -> {"model": "von-1.3.0", "answers": {key: {"type": "choice", "choice": str,
                                                 "probabilities": {option: p}, "confidence": float}}}
  GET  {endpoint}/health -> {"status": "ok", "engine": "von-1.3", ...}
Unlike Laya, criteria is a {name: description} map; the option text serves as both. Von's `confidence` is its
own scale, so the probability of the chosen option is returned instead, which is what the gateway thresholds on.
Von scores all options in one encoder pass over an 8192-token window; no option limit is declared.
"""

from .base import MalformedResponse, System1Provider
from .http import LocalHTTP

DEFAULT_ENDPOINT = "http://127.0.0.1:8777"  # 8765 is Laya's; the launcher binds loopback
DEFAULT_MODEL = "von-1.3"
YES_NO = ["yes", "no"]


class VonProvider(System1Provider):
    name = "von"

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._http = LocalHTTP("Von", self.settings.get("endpoint", DEFAULT_ENDPOINT),
                               self.settings.get("allow_remote", False), self.settings.get("api_key", ""))
        self.endpoint = self._http.endpoint
        self.model = str(self.settings.get("model", DEFAULT_MODEL)).strip()

    def _ask(self, state, requests: dict, timeout_s: float) -> dict:
        questions = {k: {"type": "choice", "instructions": r.question,
                         "criteria": {o: o for o in (r.options or YES_NO)}} for k, r in requests.items()}
        body = {"state": state, "questions": questions}
        if self.model:
            body["model"] = self.model
        answers = self._http.call("POST", "/v1/systemone", body, timeout_s).get("answers") or {}
        return {k: self._map(answers.get(k), k) for k in requests}

    @staticmethod
    def _map(answer, key: str) -> dict:
        if not isinstance(answer, dict) or not isinstance(answer.get("probabilities"), dict):
            raise MalformedResponse(f"Von response has no answers.{key} with probabilities")
        probs, choice = answer["probabilities"], answer.get("choice")
        ranked = ", ".join(f"{k}={v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1])
                           if isinstance(v, (int, float)))
        return {"decision": choice, "confidence": probs.get(choice), "probabilities": probs,
                "rationale": f"von: {ranked}"}

    def decide(self, request, timeout_s: float) -> dict:
        return self._ask(request.context, {"decision": request}, timeout_s)["decision"]

    def decide_many(self, requests: dict, timeout_s: float) -> dict:
        """One Von pass for several questions about the same state (the first request's context)."""
        return self._ask(next(iter(requests.values())).context, requests, timeout_s)

    def health(self, timeout_s: float) -> dict:
        native = self._http.call("GET", "/health", None, timeout_s)
        return {"ok": native.get("status") == "ok", "detail": f"{self.endpoint} engine={native.get('engine')!r}"}

    def capabilities(self) -> dict:
        return {"name": self.name, "endpoint": self.endpoint, "contract": "von serve /v1/systemone",
                "model": self.model, "supports_options": True}
