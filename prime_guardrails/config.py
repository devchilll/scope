import os
import logging
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AgentModel(BaseModel):
    """Agent model settings."""
    name: str = Field(default="prime_safety_router")
    model: str = Field(default="gemini-2.5-flash")

# ============================================================================
# PILLAR 1: Safety Policy
# ============================================================================

class SafetyPolicy(BaseModel):
    """Safety thresholds and settings."""
    mode: str = "STRICT"
    threshold_high: float = 0.8
    threshold_medium: float = 0.4
    use_ml_models: bool = True  # Use ML models vs LLM for Layer 2a

# ============================================================================
# PILLAR 2: Compliance Configuration
# ============================================================================

class ComplianceConfig(BaseModel):
    """Business-specific compliance rules."""
    enabled: bool = True
    raw_rules: List[str] = Field(default_factory=list)  # Human input
    transformed_rules: List[str] = Field(default_factory=list)  # Agent-ready format

# ============================================================================
# PILLAR 3: IAM Configuration
# ============================================================================

class IAMConfig(BaseModel):
    """Identity and Access Management configuration."""
    enabled: bool = True
    default_user_role: str = "USER"  # Default role for new users
    require_authentication: bool = False  # Whether to require auth
    session_timeout_minutes: int = 60

# ============================================================================
# PILLAR 4: Escalation Configuration
# ============================================================================

class EscalationConfig(BaseModel):
    """Escalation queue configuration."""
    enabled: bool = True
    threshold: float = 0.6  # Confidence threshold for escalation
    storage_type: str = "sqlite"  # sqlite, json, or database
    storage_path: str = "escalations.db"
    auto_notify_admins: bool = False  # Auto-notify admins of new escalations

# ============================================================================
# Combined Policy
# ============================================================================

class Policy(BaseModel):
    """Combined policy configuration - The 4 Pillars of PRIME."""
    safety: SafetyPolicy = Field(default_factory=SafetyPolicy)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    iam: IAMConfig = Field(default_factory=IAMConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)

# ============================================================================
# Main Configuration
# ============================================================================

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
    
    agent_settings: AgentModel = Field(default_factory=AgentModel)
    app_name: str = "prime_guardrails_app"
    CLOUD_PROJECT: str = Field(default="my_project")
    CLOUD_LOCATION: str = Field(default="us-central1")
    GENAI_USE_VERTEXAI: str = Field(default="true")
    
    # Legacy Policy Configuration (for backward compatibility)
    POLICY_MODE: str = Field(default="STRICT")
    THRESHOLD_HIGH: float = Field(default=0.8)
    THRESHOLD_MEDIUM: float = Field(default=0.4)
    
    # Pillar 1: Safety Configuration
    SAFETY_MODE: str = Field(default="STRICT")
    SAFETY_THRESHOLD_HIGH: float = Field(default=0.8)
    SAFETY_THRESHOLD_MEDIUM: float = Field(default=0.4)
    SAFETY_USE_ML_MODELS: bool = Field(default=True)
    
    # Pillar 2: Compliance Configuration
    COMPLIANCE_ENABLED: bool = Field(default=True)
    COMPLIANCE_RULES: List[str] = Field(default_factory=list)
    
    # Pillar 3: IAM    # IAM Pillar
    IAM_ENABLED: bool = Field(default=True)
    IAM_DEFAULT_USER_ROLE: str = Field(default="USER")
    IAM_REQUIRE_AUTHENTICATION: bool = Field(default=False)
    IAM_SESSION_TIMEOUT_MINUTES: int = Field(default=60)
    
    # Current user for testing
    IAM_CURRENT_USER_ROLE: str = Field(default="USER")
    IAM_CURRENT_USER_ID: str = Field(default="user")
    IAM_CURRENT_USER_NAME: str = Field(default="Test User")

    # Escalation Pillar 4: Escalation Configuration
    ESCALATION_ENABLED: bool = Field(default=True)
    ESCALATION_THRESHOLD: float = Field(default=0.6)
    ESCALATION_STORAGE_TYPE: str = Field(default="sqlite")
    ESCALATION_STORAGE_PATH: str = Field(default="prime_guardrails/escalation/data/escalations.db")
    ESCALATION_AUTO_NOTIFY_ADMINS: bool = Field(default=False)

    @property
    def current_policy(self) -> Policy:
        """Returns structured policy object with all 4 pillars.
        
        Returns:
            Policy object containing safety, compliance, IAM, and escalation configs
        """
        # Pillar 1: Safety
        safety = SafetyPolicy(
            mode=self.SAFETY_MODE,
            threshold_high=self.SAFETY_THRESHOLD_HIGH,
            threshold_medium=self.SAFETY_THRESHOLD_MEDIUM,
            use_ml_models=self.SAFETY_USE_ML_MODELS
        )
        
        # Pillar 2: Compliance
        compliance = ComplianceConfig(
            enabled=self.COMPLIANCE_ENABLED,
            raw_rules=self.COMPLIANCE_RULES,
            transformed_rules=[]  # Will be populated at agent init
        )
        
        # Pillar 3: IAM
        iam = IAMConfig(
            enabled=self.IAM_ENABLED,
            default_user_role=self.IAM_DEFAULT_USER_ROLE,
            require_authentication=self.IAM_REQUIRE_AUTHENTICATION,
            session_timeout_minutes=self.IAM_SESSION_TIMEOUT_MINUTES
        )
        
        # Pillar 4: Escalation
        escalation = EscalationConfig(
            enabled=self.ESCALATION_ENABLED,
            threshold=self.ESCALATION_THRESHOLD,
            storage_type=self.ESCALATION_STORAGE_TYPE,
            storage_path=self.ESCALATION_STORAGE_PATH,
            auto_notify_admins=self.ESCALATION_AUTO_NOTIFY_ADMINS
        )
        
        return Policy(
            safety=safety,
            compliance=compliance,
            iam=iam,
            escalation=escalation
        )
