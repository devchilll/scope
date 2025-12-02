"""Configuration loader for safety and compliance rules.

Loads YAML configuration files and makes them available to the agent.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any


def load_yaml_config(filename: str) -> Dict[str, Any]:
    """Load a YAML configuration file.
    
    Args:
        filename: Name of the YAML file (without path)
        
    Returns:
        Dictionary containing the configuration
    """
    config_dir = Path(__file__).parent
    config_path = config_dir / filename
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_safety_rules() -> Dict[str, Any]:
    """Load safety rules configuration.
    
    Returns:
        Dictionary containing safety rules and thresholds
    """
    return load_yaml_config('safety_rules.yaml')


def load_compliance_rules() -> Dict[str, Any]:
    """Load compliance rules configuration.
    
    Returns:
        Dictionary containing compliance rules and thresholds
    """
    return load_yaml_config('compliance_rules.yaml')


def format_rules_for_prompt(rules: List[Dict[str, Any]]) -> str:
    """Format rules into a human-readable string for LLM prompts.
    
    Args:
        rules: List of rule dictionaries
        
    Returns:
        Formatted string with all rules
    """
    formatted = []
    for rule in rules:
        rule_text = f"""
**{rule['id']}**: {rule['description']}
- Category: {rule['category']}
- Severity: {rule['severity']}
- Action: {rule['action']}
"""
        if 'regulation' in rule:
            rule_text += f"- Regulation: {rule['regulation']}\n"
        
        if 'examples' in rule and rule['examples']:
            rule_text += "- Examples:\n"
            for example in rule['examples']:
                rule_text += f"  - {example}\n"
        
        formatted.append(rule_text.strip())
    
    return "\n\n".join(formatted)


# Load configurations at module import
SAFETY_CONFIG = load_safety_rules()
COMPLIANCE_CONFIG = load_compliance_rules()

# Format rules for prompts
SAFETY_RULES_TEXT = format_rules_for_prompt(SAFETY_CONFIG['safety_rules'])
COMPLIANCE_RULES_TEXT = format_rules_for_prompt(COMPLIANCE_CONFIG['compliance_rules'])
