"""Observability tools for PRIME agent - 2-Layer Safety Architecture.

These tools make safety checks and logging visible as explicit tool calls
in the ADK web UI trace viewer.

Architecture:
- Layer 1: Fast ML-based safety check (mock for now)
- Layer 2: LLM-based safety & compliance check with structured JSON output
"""

import json
from typing import Optional
from google.genai import Client
from .logging import get_audit_logger, AuditEventType
from .config import Config
from .rules import SAFETY_RULES_TEXT, COMPLIANCE_RULES_TEXT

# Initialize logger and config
audit_logger = get_audit_logger()
config = Config()

# Initialize Gemini client for Layer 2 safety check
genai_client = Client(
    vertexai=True,
    project=config.CLOUD_PROJECT,
    location=config.CLOUD_LOCATION,
)


def safety_check_layer1(user_input: str) -> str:
    """Layer 1: Fast ML-based safety check (MOCK - always passes for now).
    
    This is a placeholder for a fast ML model that would check for:
    - Offensive language
    - Prompt injection
    - Other quick safety violations
    
    In production, this would call a lightweight ML model (~50ms latency).
    
    Args:
        user_input: The user's input text to check
        
    Returns:
        Safety check result (currently always passes)
    """
    # Log the Layer 1 check
    audit_logger.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id=config.IAM_CURRENT_USER_ID,
        action="safety_layer1_check",
        details={
            "input": user_input[:200],
            "model": "mock_ml_classifier",
            "note": "Mock implementation - always passes"
        }
    )
    
    # Mock implementation - always passes
    is_safe = True
    risk_score = 0.0
    
    if is_safe:
        return f"✅ Layer 1 (ML) Safety Check PASSED. Risk score: {risk_score:.2f}. Proceeding to Layer 2."
    else:
        return f"⚠️ Layer 1 (ML) Safety Check FAILED. Risk score: {risk_score:.2f}. Request blocked."


def safety_check_layer2(user_input: str) -> str:
    """Layer 2: LLM-based safety & compliance analysis.
    
    This layer analyzes user requests against safety and compliance rules,
    returning safety scores and violations WITHOUT making a decision.
    
    Args:
        user_input: The user's input text to check
        
    Returns:
        JSON string with safety analysis:
        {
            "safety_score": 0.0-1.0,
            "compliance_score": 0.0-1.0,
            "confidence": 0.0-1.0,
            "violated_rules": [...],
            "risk_factors": [...],
            "analysis": "..."
        }
    """
    # Create the Layer 2 safety analysis prompt
    layer2_prompt = f"""You are a safety and compliance analyzer for a banking customer service agent.

Your job is to analyze user requests against safety and compliance rules and provide a detailed assessment.

## SAFETY RULES:
{SAFETY_RULES_TEXT}

## COMPLIANCE RULES:
{COMPLIANCE_RULES_TEXT}

## USER REQUEST:
"{user_input}"

## YOUR TASK:
Analyze the user request against the safety and compliance rules above.
Return a JSON object with your analysis. DO NOT make a decision (approve/reject/etc), just analyze.

## OUTPUT FORMAT (JSON):
{{
    "safety_score": 0.95,  // 0.0 (unsafe) to 1.0 (safe)
    "compliance_score": 0.90,  // 0.0 (non-compliant) to 1.0 (compliant)
    "confidence": 0.9,  // 0.0 (low) to 1.0 (high) - how confident you are in this analysis
    "violated_rules": [],  // List of rule IDs if any violations (e.g., ["SAFETY-001", "COMP-005"])
    "risk_factors": [],  // List of specific risk factors identified (e.g., ["mentions competitors", "requests pricing"])
    "analysis": "Request appears safe. User wants to check account balance, which is a standard banking operation with no safety or compliance concerns."
}}

Return ONLY the JSON object, no other text.
"""
    
    try:
        # Call Gemini for Layer 2 safety analysis
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=layer2_prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,  # Low temperature for consistent safety analysis
            }
        )
        
        # Parse the JSON response
        safety_analysis = json.loads(response.text)
        
        # Log the Layer 2 check
        audit_logger.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=config.IAM_CURRENT_USER_ID,
            action="safety_layer2_analysis",
            details={
                "input": user_input[:200],
                "model": "gemini-2.5-flash",
                "analysis": safety_analysis
            }
        )
        
        # Return the JSON as a string for the agent to parse
        return json.dumps(safety_analysis, indent=2)
        
    except Exception as e:
        # Log error
        audit_logger.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=config.IAM_CURRENT_USER_ID,
            action="safety_layer2_analysis_failed",
            success=False,
            error=str(e)
        )
        
        # Return a safe default (low scores on error)
        error_response = {
            "safety_score": 0.0,
            "compliance_score": 0.0,
            "confidence": 0.0,
            "violated_rules": [],
            "risk_factors": ["analysis_error"],
            "analysis": f"Error during safety analysis: {str(e)}. Unable to complete analysis."
        }
        return json.dumps(error_response, indent=2)


def make_safety_decision(safety_analysis_json: str) -> str:
    """Make a decision based on safety analysis results.
    
    This tool takes the output from safety_check_layer2 and makes a verdict:
    approve, reject, rewrite, or escalate.
    
    Args:
        safety_analysis_json: JSON string from safety_check_layer2 containing:
            - safety_score
            - compliance_score
            - confidence
            - violated_rules
            - risk_factors
            - analysis
            
    Returns:
        JSON string with decision:
        {
            "action": "approve" | "reject" | "rewrite" | "escalate",
            "params": {...},
            "reasoning": "..."
        }
    """
    decision_prompt = f"""You are a decision maker for a banking customer service agent.

You receive safety analysis results and must make a verdict on how to proceed.

## SAFETY ANALYSIS RESULTS:
{safety_analysis_json}

## YOUR TASK:
Based on the safety analysis above, decide what action to take.

## OUTPUT FORMAT (JSON):
{{
    "action": "approve",  // "approve" | "reject" | "rewrite" | "escalate"
    "params": {{}},  // Action-specific parameters (e.g., {{"rewritten_text": "..."}} for "rewrite")
    "reasoning": "Safety and compliance scores are high (0.95, 0.90) with no violations. Request is safe to proceed."
}}

## ACTION TYPES:
- **approve**: Request is safe and compliant (safety_score >= 0.8, compliance_score >= 0.8), proceed with normal processing
- **reject**: Request has clear violations or very low scores (safety_score < 0.4 OR compliance_score < 0.4), refuse politely
- **rewrite**: Request has valid intent but some concerns (scores 0.4-0.8), provide rewritten version in params.rewritten_text
- **escalate**: Uncertain situation, low confidence, or edge case (confidence < 0.7), requires human review

Return ONLY the JSON object, no other text.
"""
    
    try:
        # Call Gemini for decision making
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=decision_prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            }
        )
        
        # Parse the JSON response
        decision = json.loads(response.text)
        
        # Log the decision
        audit_logger.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=config.IAM_CURRENT_USER_ID,
            action="safety_decision_made",
            details={
                "model": "gemini-2.5-flash",
                "decision": decision
            }
        )
        
        return json.dumps(decision, indent=2)
        
    except Exception as e:
        # Log error
        audit_logger.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=config.IAM_CURRENT_USER_ID,
            action="safety_decision_failed",
            success=False,
            error=str(e)
        )
        
        # Return a safe default (escalate on error)
        error_response = {
            "action": "escalate",
            "params": {},
            "reasoning": f"Error during decision making: {str(e)}. Escalating for human review."
        }
        return json.dumps(error_response, indent=2)


def log_agent_response(response_summary: str, model_used: str = "gemini-2.5-flash") -> str:
    """Log the agent's response for audit trail.
    
    This tool logs agent responses for compliance and monitoring.
    Call this after you've generated your response to the user.
    
    Args:
        response_summary: Brief summary of your response (1-2 sentences)
        model_used: The model that generated the response
        
    Returns:
        Confirmation that the response was logged
    """
    # Log the LLM response
    audit_logger.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id=config.IAM_CURRENT_USER_ID,
        action="llm_response",
        details={
            "model": model_used,
            "response_received": True,
            "summary": response_summary[:200]
        }
    )
    
    return f"✅ Response logged successfully for audit trail (model: {model_used})"


# Export tools
OBSERVABILITY_TOOLS = [
    safety_check_layer1,
    safety_check_layer2,
    make_safety_decision,
    log_agent_response,
]
