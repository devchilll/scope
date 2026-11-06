"""Unit tests for the Layer 2a text safety classifier wrapper.

Uses an injected fake model so no network / model download is required.
"""

import pytest

from scope.safety.text import TextSafetyTool, MODEL_NAME


class FakeModel:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return self.scores


SAFE = {"toxicity": 0.01, "severe_toxicity": 0.0, "obscene": 0.0,
        "threat": 0.0, "insult": 0.01, "identity_attack": 0.0}
TOXIC = {"toxicity": 0.97, "severe_toxicity": 0.1, "obscene": 0.2,
         "threat": 0.05, "insult": 0.92, "identity_attack": 0.01}


class TestTextSafetyTool:
    def test_safe_input_passes(self):
        tool = TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE))
        result = tool.check("What's my account balance?")
        assert result["checked"] is True
        assert result["is_safe"] is True
        assert result["risk_category"] == "none"
        assert result["model"] == MODEL_NAME

    def test_toxic_input_blocked(self):
        tool = TextSafetyTool(threshold_high=0.8, model=FakeModel(TOXIC))
        result = tool.check("You are stupid and I hate you.")
        assert result["checked"] is True
        assert result["is_safe"] is False
        assert result["risk_category"] == "insult"
        assert result["confidence"] == pytest.approx(0.92)

    def test_severe_toxicity_uses_lower_threshold(self):
        scores = dict(SAFE, severe_toxicity=0.6)
        tool = TextSafetyTool(threshold_high=0.8, threshold_severe=0.5,
                              model=FakeModel(scores))
        result = tool.check("...")
        assert result["is_safe"] is False
        assert result["risk_category"] == "severe_toxicity"

    def test_threshold_is_respected(self):
        scores = dict(SAFE, toxicity=0.7)
        assert TextSafetyTool(threshold_high=0.8, model=FakeModel(scores)).check("x")["is_safe"]
        assert not TextSafetyTool(threshold_high=0.6, model=FakeModel(scores)).check("x")["is_safe"]

    def test_empty_input_is_safe_without_calling_model(self):
        model = FakeModel(TOXIC)
        tool = TextSafetyTool(model=model)
        result = tool.check("   ")
        assert result["is_safe"] is True
        assert model.calls == []

    def test_unavailable_model_reports_unchecked(self):
        tool = TextSafetyTool()
        tool._load_error = "boom"  # simulate failed load
        result = tool.check("hello")
        assert result["checked"] is False
        assert result["is_safe"] is True
        assert result["error"] == "boom"
        assert tool.available is False


class SubstringModel:
    """Fake classifier: TOXIC if the part of the text it reads contains
    ``stupid idiot``, else SAFE. Like toxic-bert it truncates its input
    (here to the first 500 characters). Records every input."""

    def __init__(self):
        self.calls = []

    def _read(self, text):
        return text[:500]

    def predict(self, text):
        self.calls.append(text)
        return TOXIC if "stupid idiot" in self._read(text) else SAFE


class WordTokenizer:
    """Stand-in for Detoxify's BERT tokenizer: one token per word."""

    def tokenize(self, text):
        return text.split()

    def convert_tokens_to_string(self, tokens):
        return " ".join(tokens)


class TokenizingModel(SubstringModel):
    """Exposes a tokenizer and, like toxic-bert, reads only 510 tokens."""

    def __init__(self):
        super().__init__()
        self.tokenizer = WordTokenizer()

    def _read(self, text):
        return " ".join(text.split()[:510])


BENIGN = "Please show me the balance of my savings account. "
TAIL = "You are a stupid idiot."


class TestLongTextChunking:
    """toxic-bert reads 512 tokens; longer text is classified in windows."""

    def test_short_text_is_classified_whole(self):
        model = SubstringModel()
        text = BENIGN * 3 + TAIL
        result = TextSafetyTool(threshold_high=0.8, model=model).check(text)
        assert model.calls == [text]
        assert result["chunks"] == 1
        assert result["is_safe"] is False

    def test_toxic_tail_after_long_prefix_is_caught_by_characters(self):
        model = SubstringModel()  # no tokenizer: character windows
        text = BENIGN * 200 + TAIL  # ~10k characters
        result = TextSafetyTool(threshold_high=0.8, model=model).check(text)
        assert result["is_safe"] is False
        assert result["risk_category"] == "insult"
        assert result["chunks"] == len(model.calls) > 1
        assert all(len(c) <= 500 for c in model.calls)
        # Every character is in at least one window.
        assert model.calls[0] == text[:500] and text.endswith(model.calls[-1])

    def test_toxic_tail_after_long_prefix_is_caught_by_tokens(self):
        model = TokenizingModel()
        text = BENIGN * 200 + TAIL  # ~1600 "tokens"
        result = TextSafetyTool(threshold_high=0.8, model=model).check(text)
        assert result["is_safe"] is False
        assert len(model.calls) > 1
        assert all(len(c.split()) <= 400 for c in model.calls)
        assert model.calls[-1].endswith(TAIL)

    def test_phrase_on_a_window_boundary_is_seen_whole(self):
        model = SubstringModel()
        text = "x" * 490 + " stupid idiot " + "y" * 600  # straddles char 500
        assert TextSafetyTool(threshold_high=0.8, model=model).check(text)["is_safe"] is False

    def test_scores_are_max_per_category_over_windows(self):
        class Alternating:
            def __init__(self):
                self.n = 0

            def predict(self, text):
                self.n += 1
                return {"toxicity": 0.9 if self.n == 1 else 0.1,
                        "insult": 0.1 if self.n == 1 else 0.5}

        result = TextSafetyTool(threshold_high=0.95, model=Alternating()).check("z" * 1200)
        assert result["scores"] == {"toxicity": 0.9, "insult": 0.5}
        assert result["is_safe"] is True
