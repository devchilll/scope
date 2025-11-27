"""Safety checking tools for text and image content.

This module contains fast safety checks (Layer 2a) using ML models.
"""

import requests
from io import BytesIO
from PIL import Image


class TextSafetyTool:
    """Text safety checker using transformer-based classification."""
    
    def __init__(self):
        # Lazy import
        from transformers import pipeline
        self.classifier = pipeline("text-classification", model="Falconsai/offensive_speech_detection")

    def check(self, text: str) -> dict:
        """Check text for offensive content.
        
        Args:
            text: Text to check
            
        Returns:
            Dict with is_safe, risk_category, and confidence
        """
        try:
            results = self.classifier(text)
            # Result format: [{'label': 'offensive', 'score': 0.99}] or similar
            
            result = results[0]
            label = result['label'].lower()
            score = result['score']
            
            is_safe = True
            risk_category = "None"
            
            if "offensive" in label:
                is_safe = False
                risk_category = "Offensive"
            
            return {
                "is_safe": is_safe,
                "risk_category": risk_category,
                "confidence": score
            }
        except Exception as e:
            print(f"Text safety check failed: {e}")
            return {"is_safe": True, "risk_category": "Error", "confidence": 0.0}


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
            Dict with is_safe and nsfw_score
        """
        import torch
        
        try:
            image = None
            if isinstance(image_input, str):
                if image_input.startswith("http"):
                    response = requests.get(image_input, stream=True)
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
                "nsfw_score": nsfw_score
            }

        except Exception as e:
            print(f"Image safety check failed: {e}")
            return {"is_safe": True, "nsfw_score": 0.0}
