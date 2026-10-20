"""Laya adapter: the only module that knows Laya's wire format.

Contract of `laya-serve` (pip install "laya[serve]", verified against laya 0.3.20):
  POST {endpoint}/v1/systemone
       {"model": "typed-decisions",
        "state": {...},
        "questions": {"decision": {"type": "choice", "instructions": str, "criteria": [str, ...]}}}
    -> {"answers": {"decision": {"type": "choice", "choice": str, "probabilities": {option: p},
                                 "confidence": float, "answer_confidence": float}},
        "routing": {"model": "typed-decisions", "repo": ..., "reason": ...}}
  GET  {endpoint}/health -> {"status": "ok", "loaded": [checkpoint, ...], "device": "cuda"}

Known Laya limitations handled here (model card "honest limitations", checked live 2026-09-24):
- `noul` (yes/no) follows its labels instead of the input: it called `rm -rf`, `DROP TABLE` and a force
  push "safe" (4/8 right). Free-form questions are therefore asked as a two-option choice, yes/no (7/8).
- More than ~20 options exhausts the decision head's token budget (Banking77: 0.425), so they're refused.
- English-only checkpoints answer non-Latin text with ~95% confidence and 0% accuracy, which no threshold
  can catch, so such text is abstained on. Italian and other Latin-script text is unaffected.
- Raw probabilities are over-confident; the gateway's calibration layer rescales them.
Laya never abstains on its own; the gateway's min_confidence threshold does that.
"""

import json
import unicodedata

from .base import MalformedResponse, ProviderError, System1Provider
from .http import LocalHTTP

DEFAULT_ENDPOINT = "http://127.0.0.1:8765"
# laya-typed-decisions is the checkpoint fine-tuned for typed decisions (0.766 vs 0.362 for the base).
DEFAULT_MODEL = "typed-decisions"
CHECKPOINTS = ("english", "multilingual", "typed-decisions")
ENGLISH_ONLY = ("english", "typed-decisions")
QUESTION = "decision"
MAX_OPTIONS = 20
YES_NO = ["yes", "no"]


def _non_latin_share(text: str) -> float:
    """Share of letters outside the Latin script (0.0 for English or Italian, ~1.0 for Hindi or Khmer)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    # ponytail: script check only, no language ID. Laya's Router does full detection, but only when not pinned.
    other = sum(1 for c in letters if not unicodedata.name(c, "").startswith("LATIN"))
    return other / len(letters)


class LayaProvider(System1Provider):
    name = "laya"

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._http = LocalHTTP("Laya", self.settings.get("endpoint", DEFAULT_ENDPOINT),
                               self.settings.get("allow_remote", False), self.settings.get("api_key", ""))
        self.endpoint = self._http.endpoint
        # "" lets Laya's router pick a checkpoint per request.
        self.model = str(self.settings.get("model", DEFAULT_MODEL)).strip()
        if self.model and self.model not in CHECKPOINTS:
            raise ValueError(f"laya model {self.model!r} must be one of {', '.join(CHECKPOINTS)} or empty")
        # api_key: via SYSTEM1_LAYA_API_KEY only, never in the config file. Matches laya-serve's LAYA_API_KEY.

    def _question(self, request) -> dict:
        options = request.options or YES_NO
        if len(options) > MAX_OPTIONS:
            raise ProviderError(f"Laya handles at most {MAX_OPTIONS} options (got {len(options)}); "
                                "split the question into a coarse-to-fine hierarchy")
        return {"type": "choice", "instructions": request.question, "criteria": options}

    def _script_abstain(self, request):
        if self.model in ENGLISH_ONLY:
            share = _non_latin_share(request.question + " " + json.dumps(request.context, ensure_ascii=False))
            if share > 0.3:
                return {"abstain": True, "rationale": f"laya {self.model}: {share:.0%} non-Latin text; this "
                        "English-only checkpoint is confidently wrong on it (use model = \"multilingual\")"}
        return None

    def _post(self, state, questions: dict, timeout_s: float):
        body = {"state": state, "questions": questions}
        if self.model:
            body["model"] = self.model
        native = self._http.call("POST", "/v1/systemone", body, timeout_s)
        # An unknown or unavailable `model` is silently replaced by auto-routing (usually the base
        # English checkpoint), so check that the pinned checkpoint really answered.
        routed = (native.get("routing") or {}).get("model")
        if self.model and routed != self.model:
            raise MalformedResponse(f"Laya answered with checkpoint {routed!r}, expected {self.model!r}")
        return native.get("answers") or {}, routed

    @staticmethod
    def _map(answer, key: str, routed) -> dict:
        if not isinstance(answer, dict):
            raise MalformedResponse(f"Laya response has no answers.{key} object")
        # answer_confidence is the probability of the returned answer, which is what the gateway
        # thresholds on. Laya's own `confidence` is 1 - normalised entropy for choice questions
        # (0.001 for a 48/52 split), a different scale.
        probs = answer.get("probabilities")
        if not isinstance(probs, dict):
            raise MalformedResponse("Laya answer has no probabilities object")
        ranked = ", ".join(f"{k}={v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1])
                           if isinstance(v, (int, float)))
        return {"decision": answer.get("choice"), "confidence": answer.get("answer_confidence"),
                "probabilities": probs, "rationale": f"laya {routed or 'auto'}: {ranked}"}

    def decide(self, request, timeout_s: float) -> dict:
        question = self._question(request)
        abstain = self._script_abstain(request)
        if abstain:
            return abstain
        answers, routed = self._post(request.context, {QUESTION: question}, timeout_s)
        return self._map(answers.get(QUESTION), QUESTION, routed)

    def decide_many(self, requests: dict, timeout_s: float) -> dict:
        """One laya-serve pass for several questions about the same state (the first request's context)."""
        first = next(iter(requests.values()))
        abstain = self._script_abstain(first)
        if abstain:
            return {k: abstain for k in requests}
        questions = {k: self._question(r) for k, r in requests.items()}
        answers, routed = self._post(first.context, questions, timeout_s)
        return {k: self._map(answers.get(k), k, routed) for k in requests}

    def health(self, timeout_s: float) -> dict:
        native = self._http.call("GET", "/health", None, timeout_s)
        status, loaded = native.get("status"), native.get("loaded")
        detail = f"{self.endpoint} status={status!r} loaded={loaded} device={native.get('device')!r}"
        if self.model and isinstance(loaded, list) and self.model not in loaded:
            detail += f"; {self.model!r} not preloaded, the first decision will be slow"
        return {"ok": status == "ok", "detail": detail}

    def capabilities(self) -> dict:
        return {"name": self.name, "endpoint": self.endpoint, "contract": "laya-serve /v1/systemone",
                "model": self.model or "auto", "supports_options": True, "max_options": MAX_OPTIONS,
                "supports_free_form": True, "free_form_answers": YES_NO}
