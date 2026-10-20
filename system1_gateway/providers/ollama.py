"""Ollama adapter: any local chat model as a decision engine, via POST /api/chat with logprobs.

Options are shown as letters and the model answers with one letter (num_predict 1, temperature 0, think off);
probabilities are the letters' shares of top_logprobs, renormalised over the option letters. Verified against
Ollama 0.34.4 on 2026-09-30 (logprobs need Ollama >= 0.12). An LLM's letter probabilities are over-confident
(Gemma 4 E4B on routing: 72% of answers at >= 0.9, 65% of those right), so fit a calibration before trusting
a threshold.
"""

import json
import math

from .base import MalformedResponse, ProviderError, System1Provider
from .http import LocalHTTP

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
YES_NO = ["yes", "no"]


class OllamaProvider(System1Provider):
    name = "ollama"

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._http = LocalHTTP("Ollama", self.settings.get("endpoint", DEFAULT_ENDPOINT),
                               self.settings.get("allow_remote", False))
        self.endpoint = self._http.endpoint
        self.model = str(self.settings.get("model", "")).strip()
        if not self.model:
            raise ValueError('ollama needs a model, e.g. model = "gemma4:e4b" (see `ollama list`)')

    def decide(self, request, timeout_s: float) -> dict:
        options = request.options or YES_NO
        if len(options) > len(LETTERS):
            raise ProviderError(f"the ollama adapter handles at most {len(LETTERS)} options")
        letters = LETTERS[:len(options)]
        system = (request.question + "\n" + "\n".join(f"{l} = {o}" for l, o in zip(letters, options))
                  + f"\nReply with one letter only: {', '.join(letters)}.")
        ctx = request.context or {}
        text = ctx["task"] if set(ctx) == {"task"} and isinstance(ctx["task"], str) else json.dumps(ctx, ensure_ascii=False)
        body = {"model": self.model, "stream": False, "think": False, "logprobs": True, "top_logprobs": 20,
                "options": {"temperature": 0, "num_predict": 1, "num_ctx": 4096},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
        native = self._http.call("POST", "/api/chat", body, timeout_s)
        weights = dict.fromkeys(letters, 0.0)
        first = (native.get("logprobs") or [{}])[0] or {}
        for lp in first.get("top_logprobs") or []:
            token = str(lp.get("token", "")).strip().upper()
            if token in weights and isinstance(lp.get("logprob"), (int, float)):
                weights[token] += math.exp(lp["logprob"])
        total = sum(weights.values())
        answer = str((native.get("message") or {}).get("content") or "").strip()
        # At temperature 0 the answer is the top token; if that isn't an option letter the model ignored the
        # format, and whatever residual mass the letters got would be a confident-looking guess.
        if total <= 0 or answer.upper() not in weights:
            answer = answer[:20]
            raise MalformedResponse(f"Ollama gave no option-letter logprobs (answer {answer!r}); "
                                    "needs Ollama >= 0.12 and a model that follows the one-letter format")
        probs = {o: weights[l] / total for l, o in zip(letters, options)}
        decision = max(probs, key=probs.get)
        ranked = ", ".join(f"{k}={v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1]))
        return {"decision": decision, "confidence": probs[decision], "probabilities": probs,
                "rationale": f"ollama {self.model}: {ranked}"}

    def health(self, timeout_s: float) -> dict:
        tags = self._http.call("GET", "/api/tags", None, timeout_s)
        names = {m.get("name") for m in tags.get("models") or [] if isinstance(m, dict)}
        ok = self.model in names or f"{self.model}:latest" in names
        return {"ok": ok, "detail": f"{self.endpoint} model {self.model!r} {'installed' if ok else 'not installed'}"}

    def capabilities(self) -> dict:
        return {"name": self.name, "endpoint": self.endpoint, "contract": "ollama /api/chat + logprobs",
                "model": self.model, "supports_options": True, "max_options": len(LETTERS)}
