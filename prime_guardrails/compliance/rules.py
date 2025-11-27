"""Compliance rules transformation module."""
from typing import List


def transform_rules(raw_rules: List[str]) -> List[str]:
    """Convert human-readable rules to agent principles.
    
    This is a mock transformation that formats rules for the agent.
    In production, this could use an LLM to expand and formalize rules.
    
    Example:
        Input: "Don't talk about competitors"
        Output: "PRINCIPLE: Do not discuss, compare, or mention competing 
                 brands, products, or services. Politely decline such requests."
    
    Args:
        raw_rules: List of human-readable rules
        
    Returns:
        List of agent-ready formatted principles
    """
    transformed = []
    for rule in raw_rules:
        # Mock transformation - simple formatting
        # In production, could use LLM to expand these
        transformed.append(f"PRINCIPLE: {rule}")
    
    return transformed


def format_compliance_section(transformed_rules: List[str]) -> str:
    """Format compliance rules for inclusion in agent prompt.
    
    Args:
        transformed_rules: List of agent-ready principles
        
    Returns:
        Formatted string for agent instruction
    """
    if not transformed_rules:
        return ""
    
    rules_str = "\n".join([f"{i+1}. {rule}" 
                          for i, rule in enumerate(transformed_rules)])
    
    return f"""
COMPLIANCE PRINCIPLES:
{rules_str}

If input violates any principle, REFUSE and cite the rule number in your response.
"""
