import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AgentModel(BaseModel):
    """Agent model settings."""
    name: str = Field(default="prime_safety_router")
    model: str = Field(default="gemini-2.0-flash")

class Config(BaseSettings):
    """Configuration settings for the PRIME agent."""
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../.env"
        ),
        env_prefix="GOOGLE_",
        case_sensitive=True,
        extra="ignore"
    )
    
    agent_settings: AgentModel = Field(default=AgentModel())
    app_name: str = "prime_guardrails_app"
    CLOUD_PROJECT: str = Field(default="my_project")
    CLOUD_LOCATION: str = Field(default="us-central1")
    GENAI_USE_VERTEXAI: str = Field(default="true")
    
    # Policy Configuration
    POLICY_MODE: str = Field(default="STRICT")
    THRESHOLD_HIGH: float = Field(default=0.8)
    THRESHOLD_MEDIUM: float = Field(default=0.4)

    @property
    def current_policy(self):
        return {
            "mode": self.POLICY_MODE,
            "thresholds": {
                "high": self.THRESHOLD_HIGH,
                "medium": self.THRESHOLD_MEDIUM
            }
        }
