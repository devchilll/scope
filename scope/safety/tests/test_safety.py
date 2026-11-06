"""Unit tests for Safety Pillar (Image safety tool).

Note: Text safety checking is handled by unitary/toxic-bert via Detoxify
in scope/safety/text.py (TextSafetyTool); see test_text_safety.py.
"""

import pytest
from scope.safety import ImageSafetyTool


class TestImageSafetyTool:
    """Test image safety checking."""

    def test_initialization(self):
        """Test tool initializes correctly."""
        tool = ImageSafetyTool()
        assert tool.processor is not None
        assert tool.model is not None

    @pytest.mark.parametrize("logits,is_safe", [
        ([2.0, 0.0], True),    # NSFW probability ~0.12 -> safe
        ([0.0, 2.0], False),   # NSFW probability ~0.88 -> not safe
    ])
    def test_check_scores_nsfw_probability(self, logits, is_safe):
        """check() returns the softmax NSFW probability and is_safe = score <= 0.5.

        Stub processor and model (no download); a real PIL image goes through
        the same code path as an image path or URL after loading.
        """
        import torch
        from types import SimpleNamespace
        from PIL import Image

        tool = ImageSafetyTool.__new__(ImageSafetyTool)
        tool.processor = lambda images, return_tensors: {"pixel_values": torch.zeros(1, 3, 2, 2)}

        class StubModel:
            config = SimpleNamespace(id2label={0: "SFW", 1: "NSFW"}, label2id={"SFW": 0, "NSFW": 1})

            def __call__(self, **inputs):
                assert "pixel_values" in inputs
                return SimpleNamespace(logits=torch.tensor([logits]))

        tool.model = StubModel()

        result = tool.check(Image.new("RGB", (4, 4)))

        expected = torch.softmax(torch.tensor(logits), dim=-1)[1].item()
        assert result == {"is_safe": is_safe, "nsfw_score": pytest.approx(expected), "checked": True}

    def test_failed_check_is_not_reported_safe(self, tmp_path):
        """An image that can't be checked yields an unknown result, never is_safe=True."""
        # Skip __init__ so no model is downloaded; the failure happens before the model runs.
        tool = ImageSafetyTool.__new__(ImageSafetyTool)

        result = tool.check(str(tmp_path / "missing.png"))

        assert result["is_safe"] is None
        assert result["nsfw_score"] is None
        assert result["checked"] is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
