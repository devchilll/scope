"""Safety checking tool for image content.

``ImageSafetyTool`` is an NSFW image classifier that can be called directly.
It is NOT wired into the pre-model safety gate: the agent does not screen
images, only text.

Note: Text safety checking lives in ``scope/safety/text.py`` (TextSafetyTool),
which is shared by the before_model_callback and the safety_check_layer1 tool.
"""

import logging

import requests
from PIL import Image

logger = logging.getLogger(__name__)


class ImageSafetyTool:
    """Image safety checker for NSFW content detection."""
    
    def __init__(self):
        # Lazy imports
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        self.processor = AutoImageProcessor.from_pretrained("Marqo/nsfw-image-detection-384")
        self.model = AutoModelForImageClassification.from_pretrained("Marqo/nsfw-image-detection-384")

    def check(self, image_input) -> dict:
        """Check image for NSFW content.
        
        Args:
            image_input: Image path, URL, or PIL Image object
            
        Returns:
            Dict with is_safe, nsfw_score and checked. If the check fails
            (unreadable image, model error) the result is unknown, not safe:
            ``is_safe`` and ``nsfw_score`` are None, ``checked`` is False and
            ``error`` holds the reason.
        """
        import torch

        try:
            image = None
            if isinstance(image_input, str):
                if image_input.startswith("http"):
                    response = requests.get(image_input, stream=True, timeout=10)
                    image = Image.open(response.raw)
                else:
                    image = Image.open(image_input)
            else:
                # Assume it's already a PIL image or compatible
                image = image_input

            inputs = self.processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
            
            # Model specific output processing
            predicted_label = self.model.config.id2label[logits.argmax(-1).item()]
            probs = torch.nn.functional.softmax(logits, dim=-1)
            nsfw_score = probs[0][self.model.config.label2id['NSFW']].item() if 'NSFW' in self.model.config.label2id else 0.0
            
            # If label is NSFW or score > 0.5
            is_safe = nsfw_score <= 0.5
            
            return {
                "is_safe": is_safe,
                "nsfw_score": nsfw_score,
                "checked": True,
            }

        except Exception as e:
            logger.error("Image safety check failed: %s", e)
            return {
                "is_safe": None,
                "nsfw_score": None,
                "checked": False,
                "error": f"{type(e).__name__}: {e}",
            }
