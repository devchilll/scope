import os
import logging
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class AgentModel(BaseModel):
    """Agent model settings."""
    name: str = Field(default="scope_safety_router")
    model: str = Field(default="gemini-2.5-flash")

class BankInfo(BaseModel):
    """Bank contact and information settings."""
    name: str = Field(default="SCOPE Bank")
    phone: str = Field(default="1-800-SCOPE-BANK")
    email: str = Field(default="support@example.com")
    website: str = Field(default="https://www.example.com")
    hours: str = Field(default="Monday-Friday 9AM-5PM EST, Saturday 10AM-2PM EST")
    address: str = Field(default="123 Banking Street, Financial District, NY 10004")

# ============================================================================
# PILLAR 1: Safety Policy
# ============================================================================

class SafetyPolicy(BaseModel):
    """Safety thresholds and settings."""
    threshold_high: float = 0.8
    use_ml_models: bool = True  # Run the Layer 2a ML classifier (false = skip it; no LLM fallback)

# ============================================================================
# PILLAR 2: Compliance Configuration
# ============================================================================

class ComplianceConfig(BaseModel):
    """Business-specific compliance rules."""
    enabled: bool = True
    raw_rules: List[str] = Field(default_factory=list)  # Human input
    transformed_rules: List[str] = Field(default_factory=list)  # Agent-ready format

# ============================================================================
# PILLAR 5: Escalation Configuration
# ============================================================================

class EscalationConfig(BaseModel):
    """Escalation configuration.

    Tickets are stored in the banking database (see scope/escalation/queue.py).
    """
    # Layer 2b confidence below this is escalated to human review
    threshold: float = 0.6

# ============================================================================
# Combined Policy
# ============================================================================

class Policy(BaseModel):
    """Combined policy configuration - policy-backed SCOPE pillars."""
    safety: SafetyPolicy = Field(default_factory=SafetyPolicy)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)

# ============================================================================
# Main Configuration
# ============================================================================

class Config(BaseSettings):
    """Configuration settings for the SCOPE agent."""
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../.env"
        ),
        env_prefix="GOOGLE_",
        case_sensitive=True,
        extra="ignore"
    )
    
    agent_settings: AgentModel = Field(default_factory=AgentModel)
    bank_info: BankInfo = Field(default_factory=BankInfo)
    app_name: str = "scope_app"
    CLOUD_PROJECT: str = Field(default="my_project")
    CLOUD_LOCATION: str = Field(default="us-central1")
    GENAI_USE_VERTEXAI: str = Field(default="true")  # "false" uses the Gemini API (GOOGLE_API_KEY)
    
    # Pillar 1: Safety Configuration
    SAFETY_THRESHOLD_HIGH: float = Field(default=0.8)
    SAFETY_USE_ML_MODELS: bool = Field(default=True)
    
    # Pillar 2: Compliance Configuration
    COMPLIANCE_ENABLED: bool = Field(default=True)
    COMPLIANCE_RULES: List[str] = Field(default_factory=list)
    
    # Pillar 4: IAM - current user for testing
    IAM_CURRENT_USER_ROLE: str = Field(default="USER")
    IAM_CURRENT_USER_ID: str = Field(default="user")
    IAM_CURRENT_USER_NAME: str = Field(default="Alice Johnson")
    IAM_CURRENT_USER_EMAIL: str = Field(default="alice@example.com")
    IAM_CURRENT_USER_PHONE: str = Field(default="+1-555-0123")
    IAM_CURRENT_USER_ADDRESS: str = Field(default="123 Customer Street, Banking City, NY 10001")

    # Pillar 5: Escalation Configuration
    ESCALATION_THRESHOLD: float = Field(default=0.6)

    @property
    def current_policy(self) -> Policy:
        """Returns structured policy object for the policy-backed pillars.
        
        Returns:
            Policy object containing safety, compliance, and escalation configs
        """
        # Pillar 1: Safety
        safety = SafetyPolicy(
            threshold_high=self.SAFETY_THRESHOLD_HIGH,
            use_ml_models=self.SAFETY_USE_ML_MODELS
        )
        
        # Pillar 2: Compliance
        compliance = ComplianceConfig(
            enabled=self.COMPLIANCE_ENABLED,
            raw_rules=self.COMPLIANCE_RULES,
            transformed_rules=[]  # Will be populated at agent init
        )
        
        # Pillar 5: Escalation
        escalation = EscalationConfig(
            threshold=self.ESCALATION_THRESHOLD
        )
        
        return Policy(
            safety=safety,
            compliance=compliance,
            escalation=escalation
        )
