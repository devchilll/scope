"""Pre-model text safety check (Layer 2a).

A thin wrapper around ``unitary/toxic-bert`` (via Detoxify) that is shared by:

- ``scope.callbacks.fast_guardrail_callback`` - the ``before_model_callback``
  that screens every user turn *before* the LLM runs, and
- ``scope.observability_tools.safety_check_layer1`` - the explicit tool call
  that makes the same check visible in the ADK trace viewer.

The classifier is loaded lazily on first use so importing this module (and the
callback) stays cheap, and so unit tests can inject a fake model.

toxic-bert reads at most 512 tokens, and Detoxify silently truncates longer
input. So that the whole message is classified, longer text is split into
overlapping windows that each fit, every window is classified, and the
highest score per category is used.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "unitary/toxic-bert"

# Detoxify score keys, in the order we report a risk category.
_RISK_LABELS = (
    "severe_toxicity",
    "threat",
    "identity_attack",
    "insult",
    "obscene",
    "toxicity",
)

# toxic-bert (bert-base-uncased) reads at most 512 tokens including [CLS] and
# [SEP]; Detoxify truncates anything after that. Text longer than
# _MAX_TOKENS is classified in windows of _CHUNK_TOKENS tokens that overlap by
# _CHUNK_OVERLAP_TOKENS, so a phrase that straddles a window boundary is
# still seen whole by one window. The window is kept well under the limit
# because turning tokens back into text and re-tokenizing it can shift the
# count slightly.
_MAX_TOKENS = 510
_CHUNK_TOKENS = 400
_CHUNK_OVERLAP_TOKENS = 100

# Fallback for a model without an accessible tokenizer: split by characters.
# BERT's WordPiece yields at most about one token per character for most
# scripts, so 500-character windows stay under 512 tokens.
_CHUNK_CHARS = 500
_CHUNK_OVERLAP_CHARS = 100


def _windows(items, size: int, overlap: int) -> list:
    """Split a sequence into windows of ``size`` that overlap by ``overlap``."""
    step = size - overlap
    windows = []
    for start in range(0, len(items), step):
        windows.append(items[start:start + size])
        if start + size >= len(items):
            break
    return windows


class TextSafetyTool:
    """Fast ML text-safety classifier with configurable block threshold.

    Args:
        threshold_high: Score at or above which input is blocked
            (``SafetyPolicy.threshold_high``).
        threshold_severe: Separate, lower threshold for ``severe_toxicity``.
        model: Optional pre-built object exposing ``predict(text) -> dict``.
            Used for tests; when omitted, Detoxify is loaded on first ``check``.
    """

    def __init__(
        self,
        threshold_high: float = 0.8,
        threshold_severe: float = 0.5,
        model: Optional[Any] = None,
    ):
        self.threshold_high = threshold_high
        self.threshold_severe = threshold_severe
        self._model = model
        self._load_error: Optional[str] = None

    # ------------------------------------------------------------------ model
    @property
    def model(self):
        """Return the Detoxify model, loading it on first access.

        Returns ``None`` (and records ``load_error``) if loading fails.
        """
        if self._model is None and self._load_error is None:
            try:
                from detoxify import Detoxify

                logger.info("Loading text safety model (%s)...", MODEL_NAME)
                # model_type='original' is unitary/toxic-bert
                self._model = Detoxify("original", device="cpu")
                logger.info("Text safety model loaded.")
            except Exception as exc:  # pragma: no cover - depends on env
                self._load_error = f"{type(exc).__name__}: {exc}"
                logger.error("Failed to load text safety model: %s", self._load_error)
        return self._model

    @property
    def available(self) -> bool:
        return self.model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ------------------------------------------------------------------ check
    def chunks(self, text: str) -> list:
        """Split ``text`` into pieces the classifier reads in full.

        Text that fits in the model's 512-token input is returned as is.
        Longer text is split into overlapping windows: by tokens when the
        model exposes its tokenizer (Detoxify does), otherwise by characters.
        """
        model = self.model
        tokenizer = getattr(model, "tokenizer", None)
        if tokenizer is not None and hasattr(tokenizer, "tokenize") and hasattr(
            tokenizer, "convert_tokens_to_string"
        ):
            tokens = tokenizer.tokenize(text)
            if len(tokens) <= _MAX_TOKENS:
                return [text]
            return [
                tokenizer.convert_tokens_to_string(window)
                for window in _windows(tokens, _CHUNK_TOKENS, _CHUNK_OVERLAP_TOKENS)
            ]
        if len(text) <= _CHUNK_CHARS:
            return [text]
        return _windows(text, _CHUNK_CHARS, _CHUNK_OVERLAP_CHARS)

    def check(self, text: str) -> dict:
        """Classify ``text``.

        Returns a dict with:
            is_safe (bool), risk_category (str), confidence (float),
            scores (dict[str, float]), model (str), checked (bool),
            chunks (int: how many windows were classified).

        Long text is classified in overlapping windows (see ``chunks``); each
        category's score is its highest score over all windows.

        ``checked`` is False when the classifier could not be loaded; callers
        decide whether to fail open or closed. Errors raised while classifying
        propagate to the caller.
        """
        if not text or not text.strip():
            return self._result(True, "none", 0.0, {}, checked=True)

        model = self.model
        if model is None:
            return self._result(
                True, "none", 0.0, {}, checked=False, error=self._load_error
            )

        pieces = self.chunks(text)
        scores: dict = {}
        for piece in pieces:
            raw: Mapping[str, Any] = model.predict(piece)
            for label, value in raw.items():
                scores[label] = max(scores.get(label, 0.0), float(value))

        is_safe = True
        risk_category = "none"
        confidence = 0.0

        severe = scores.get("severe_toxicity", 0.0)
        if severe >= self.threshold_severe:
            is_safe, risk_category, confidence = False, "severe_toxicity", severe
        else:
            for label in _RISK_LABELS:
                score = scores.get(label, 0.0)
                if score >= self.threshold_high:
                    is_safe, risk_category, confidence = False, label, score
                    break

        if is_safe:
            confidence = max(scores.values()) if scores else 0.0

        return self._result(
            is_safe, risk_category, confidence, scores, checked=True,
            chunks=len(pieces),
        )

    @staticmethod
    def _result(
        is_safe: bool,
        risk_category: str,
        confidence: float,
        scores: dict,
        *,
        checked: bool,
        error: Optional[str] = None,
        chunks: int = 0,
    ) -> dict:
        result = {
            "is_safe": is_safe,
            "risk_category": risk_category,
            "confidence": round(float(confidence), 4),
            "scores": scores,
            "model": MODEL_NAME,
            "checked": checked,
            "chunks": chunks,
        }
        if error:
            result["error"] = error
        return result


# ---------------------------------------------------------------- singleton
_TEXT_TOOL: Optional[TextSafetyTool] = None


def get_text_tool() -> TextSafetyTool:
    """Return the process-wide ``TextSafetyTool`` configured from ``Config``."""
    global _TEXT_TOOL
    if _TEXT_TOOL is None:
        from ..config import Config

        policy = Config().current_policy.safety
        _TEXT_TOOL = TextSafetyTool(threshold_high=policy.threshold_high)
    return _TEXT_TOOL


def set_text_tool(tool: Optional[TextSafetyTool]) -> None:
    """Replace the shared tool (tests / custom models). ``None`` resets it."""
    global _TEXT_TOOL
    _TEXT_TOOL = tool
