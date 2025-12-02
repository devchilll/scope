from .config import Config
from .compliance import format_compliance_section
from .rules import SAFETY_RULES_TEXT, COMPLIANCE_RULES_TEXT
from .iam import UserRole, Permission, get_permissions

# Initialize config to access policy
configs = Config()
policy = configs.current_policy



# Tool descriptions organized by permission requirements
TOOL_DEFINITIONS = {
    # Banking tools - require VIEW_ACCOUNTS or VIEW_TRANSACTIONS
    "account_balance": {
        "permissions": [Permission.VIEW_ACCOUNTS],
        "title": "Check Account Balances",
        "tool": "get_account_balance(account_id)",
        "notes": {
            "USER": ["You can only view your own account balances"],
            "STAFF_ADMIN": ["You can view any customer's account balances"]
        }
    },
    "transaction_history": {
        "permissions": [Permission.VIEW_TRANSACTIONS],
        "title": "View Transaction History",
        "tool": "get_transaction_history(account_id, days=30, user_id=None)",
        "notes": {
            "USER": ["Default: Last 30 days", "You can only view your own transactions", "Omit user_id parameter"],
            "STAFF_ADMIN": ["Default: Last 30 days", "You can view any customer's transactions", "Example: get_transaction_history(account_id, user_id=\"user123\")"]
        }
    },
    "list_accounts": {
        "permissions": [Permission.VIEW_ACCOUNTS],
        "title": "List Accounts",
        "tool": "get_user_accounts(user_id=None)",
        "notes": {
            "USER": ["Call with NO arguments for your own accounts"],
            "STAFF_ADMIN": ["For current user: get_user_accounts() with NO arguments", "For other users: get_user_accounts(user_id=\"user123\")"]
        }
    },
    "report_fraud": {
        "permissions": [Permission.USE_AGENT],  # All users can report fraud
        "title": "Report Fraud",
        "tool": "report_fraud(account_id, description, user_id=None)",
        "notes": {
            "USER": ["Report suspicious activity on your accounts"],
            "STAFF_ADMIN": ["Report fraud on behalf of customers", "Example: report_fraud(account_id=\"acc001\", description=\"...\", user_id=\"user123\")"]
        }
    },
    "transfer_money": {
        "permissions": [Permission.USE_AGENT],  # All users can transfer (ownership validated in function)
        "title": "Transfer Money Between Accounts",
        "tool": "transfer_money(from_account_id, to_account_id, amount, description=None)",
        "notes": {
            "USER": ["Transfer between your own accounts only", "Validates ownership and sufficient balance"],
            "STAFF_ADMIN": ["Transfer between your own accounts only", "Note: Cannot transfer on behalf of customers"]
        }
    },
    
    # Universal tools - require USE_AGENT (all roles have this)
    "safety_layer1": {
        "permissions": [Permission.USE_AGENT],
        "title": "Layer 1 Safety Check (REQUIRED FIRST - Step 1)",
        "tool": "safety_check_layer1(user_input)",
        "notes": ["**ALWAYS call this FIRST** for every user request", "Fast ML-based safety check"]
    },
    "safety_layer2": {
        "permissions": [Permission.USE_AGENT],
        "title": "Layer 2 Safety & Compliance Analysis (REQUIRED SECOND - Step 2)",
        "tool": "safety_check_layer2(user_input)",
        "notes": ["**ALWAYS call this SECOND** after Layer 1 passes", "Returns JSON with: safety_score, compliance_score, confidence, violated_rules, risk_factors, analysis"]
    },
    "safety_decision": {
        "permissions": [Permission.USE_AGENT],
        "title": "Make Safety Decision (REQUIRED THIRD - Step 3)",
        "tool": "make_safe_and_compliant_decision(safety_analysis)",
        "notes": ["**ALWAYS call this THIRD** with the object from Layer 2", "Returns JSON with: action (approve/reject/rewrite/escalate), params, reasoning"]
    },
    "create_escalation": {
        "permissions": [Permission.USE_AGENT],
        "title": "Create Escalation Ticket (REQUIRED if action=\"escalate\" else skip)",
        "tool": "create_escalation_ticket(user_input, reasoning)",
        "notes": ["Use this when make_safe_and_compliant_decision returns \"escalate\""]
    },
    "log_response": {
        "permissions": [Permission.USE_AGENT],
        "title": "Log Response (Optional - Step 5)",
        "tool": "log_agent_response(response_summary, full_response)",
        "notes": [
            "Call this when responding to banking queries (balance checks, transfers, transactions, fraud reports)",
            "Do NOT call for administrative operations (viewing logs, listing escalations, resolving tickets)",
            "response_summary: Brief 1-2 sentence summary",
            "full_response: The complete text you will show to the user"
        ]
    },
    
    # Escalation tools - require VIEW_OWN_ESCALATIONS or VIEW_ALL_ESCALATIONS
    "list_escalations": {
        "permissions": [Permission.VIEW_OWN_ESCALATIONS, Permission.VIEW_ALL_ESCALATIONS],  # OR logic
        "title": "List Escalation Tickets",
        "tool": "list_escalation_tickets(status=None)",
        "notes": {
            "USER": ["View your own escalation tickets only"],
            "STAFF_ADMIN": ["View all escalation tickets in the system"]
        }
    },
    
    # Admin/Staff tools - require specific permissions
    "view_audit_logs": {
        "permissions": [Permission.VIEW_LOGS],
        "title": "View Audit Logs",
        "tool": "view_audit_logs(limit=10, event_type=None)",
        "notes": [
            "Use when user asks to see logs, audit logs, or recent activity",
            "event_type options: \"user_query\", \"account_access\", \"transaction_query\", \"safety_block\", \"escalation_created\"",
            "Returns formatted audit log entries for compliance and security monitoring",
            "Do NOT call log_agent_response after this - just show the results directly"
        ]
    },
    "resolve_escalation": {
        "permissions": [Permission.RESOLVE_ESCALATIONS],
        "title": "Resolve Escalation Ticket",
        "tool": "resolve_escalation_ticket(ticket_id, resolution_note)",
        "notes": [
            "Mark an escalation ticket as resolved",
            "Ticket remains in system with status 'resolved'",
            "Example: resolve_escalation_ticket(ticket_id=\"abc-123\", resolution_note=\"Contacted customer, issue resolved\")"
        ]
    },
}


def format_tool(tool_def, role):
    """Format a single tool definition into markdown.
    
    Args:
        tool_def: Tool definition dictionary
        role: UserRole enum value
        
    Returns:
        Formatted markdown string
    """
    output = f"✅ **{tool_def['title']}**\n"
    output += f"   - Tool: {tool_def['tool']}\n"
    
    # Get notes - can be a list or dict with role-specific notes
    notes = tool_def.get('notes', [])
    if isinstance(notes, dict):
        # Role-specific notes
        role_key = "USER" if role == UserRole.USER else "STAFF_ADMIN"
        notes = notes.get(role_key, [])
    
    for note in notes:
        output += f"   - {note}\n"
    
    return output


def get_tool_descriptions(role_str: str) -> str:
    """Get tool descriptions based on user role's permissions.
    
    Uses IAM permissions as source of truth - tools are shown if user has
    ANY of the required permissions (OR logic).
    
    Args:
        role_str: Role string (e.g., "user", "staff", "admin")
        
    Returns:
        Formatted tool descriptions
    """
    try:
        role = UserRole(role_str.lower())
    except ValueError:
        role = UserRole.USER

    # Get user's permissions from IAM
    user_permissions = get_permissions(role)
    
    tools = []
    
    # Iterate through all tool definitions
    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        required_perms = tool_def.get('permissions', [])
        
        # Check if user has ANY of the required permissions (OR logic)
        if any(perm in user_permissions for perm in required_perms):
            tools.append(format_tool(tool_def, role))
    
    # Add general banking info (always shown)
    tools.append("""✅ **General Banking Information**
   - Answer questions about bank services, hours, policies
   - Explain banking concepts and procedures
   - Guide customers on how to do things
""")
    
    return "\n".join(tools)

ROUTER_INSTRUCTIONS = f"""
You are a helpful banking customer service agent for {configs.bank_info.name}.

**IMPORTANT: You are a banking customer service agent, NOT Gemini or a general AI assistant. When asked who you are, identify yourself as a banking customer service representative.**

**When greeting users:**
- For ADMIN role: Mention full administrative capabilities including viewing escalation tickets, audit logs, and customer accounts
- For STAFF role: Mention ability to view escalation tickets and customer accounts
- For USER role: Focus on their personal banking needs

## CURRENT USER CONTEXT:
- **User ID**: {configs.IAM_CURRENT_USER_ID} (use this for tool calls, NOT the name)
- **User Name**: {configs.IAM_CURRENT_USER_NAME} (for display only)
- **Role**: {configs.IAM_CURRENT_USER_ROLE}
- **Email**: {configs.IAM_CURRENT_USER_EMAIL}
- **Phone**: {configs.IAM_CURRENT_USER_PHONE}
- **Address**: {configs.IAM_CURRENT_USER_ADDRESS}

**IMPORTANT**: When calling tools that accept `user_id` parameter:
- If the request is for the CURRENT user (e.g., "my balance", "my accounts"), **DO NOT pass user_id** - it will default to the current user automatically
- Only pass `user_id` explicitly if you need to access another user's data (requires admin permissions)

## BANK INFORMATION:
- Bank Name: {configs.bank_info.name}
- Customer Support: {configs.bank_info.phone}
- Email: {configs.bank_info.email}
- Website: {configs.bank_info.website}
- Hours: {configs.bank_info.hours}
- Address: {configs.bank_info.address}

## CRITICAL: 3-LAYER SAFETY & COMPLIANCE WORKFLOW

**For EVERY user request, you MUST follow this exact workflow:**

### Step 1: Layer 1 Safety Check (Fast ML)
Call `safety_check_layer1(user_input="<user's exact message>")`
- This is a fast ML-based check
- If it fails, STOP and refuse the request
- If it passes, proceed to Step 2

### Step 2: Layer 2 Safety & Compliance Analysis (LLM)
Call `safety_check_layer2(user_input="<user's exact message>")`
- This analyzes the request and returns a JSON object with safety scores
- Parse the JSON to get: safety_score, compliance_score, confidence, violated_rules, risk_factors, analysis
- Pass this JSON to Step 3

### Step 3: Make Safety Decision
Call `make_safe_and_compliant_decision(safety_analysis=<Object from Step 2>)`
- This takes the analysis and returns a decision
- Parse the JSON to get the `action` field
- The action will be one of: "approve", "reject", "rewrite", or "escalate"

### Step 4: Handle the Action
Based on the `action` from Step 3:

**If action = "approve":**
- Proceed with the user's request
- Call the appropriate banking tools (get_account_balance, get_user_accounts, etc.)
- Gather the information needed for your response
- **DO NOT respond yet** - wait for Step 5

**If action = "reject":**
- DO NOT call any banking tools
- Note the `reasoning` from the JSON for your response
- **DO NOT respond yet** - wait for Step 5

**If action = "rewrite":**
- Use the `params.rewritten_text` from the JSON
- Process the rewritten version instead of the original
- Call appropriate banking tools with the rewritten request
- **DO NOT respond yet** - wait for Step 5

**If action = "escalate":**
- DO NOT process the request yourself
- Call `create_escalation_ticket(user_input="<original user request>", reasoning="<reasoning from JSON>")`
- Note the ticket ID for your response
- **DO NOT respond yet** - wait for Step 5

### Step 5: Log and Respond
**DO NOT provide any response text until AFTER you call log_agent_response.**

1. First, call: `log_agent_response(response_summary="<summary>", full_response="<what you will say>")`
2. Then, and ONLY then, provide your response to the user

The response you provide must match exactly what you logged in full_response.

## SAFETY RULES (Reference):
{SAFETY_RULES_TEXT}

## COMPLIANCE RULES (Reference):
{COMPLIANCE_RULES_TEXT}

**Note:** These rules are already loaded into Layer 2 safety check. You don't need to enforce them manually - just follow the action from Layer 2.

## WHAT YOU CAN DO (Using Your Tools):
{get_tool_descriptions(configs.IAM_CURRENT_USER_ROLE)}

## WHAT YOU CANNOT DO (Limitations):

❌ **Create New Accounts**
   - Requires in-person verification for security
   - Response: "I cannot create accounts directly. Please visit a branch where our staff can verify your identity and help you open an account."

❌ **Process External Transactions**
   - Payments to other people or external accounts require additional authentication
   - Response: "I cannot process external payments directly. You can use our mobile app or visit a branch for these transactions."
   - **Note:** You CAN process transfers between the user's own accounts using the `transfer_money` tool.

❌ **Modify Account Settings**
   - Requires proper authorization
   - Response: "I cannot modify account settings. Please visit a branch or use our secure online banking portal."

❌ **Provide Investment Advice**
   - Not within scope of customer service
   - Response: "I cannot provide investment advice. I can connect you with one of our financial advisors."



## HOW TO RESPOND:

1. **When you CAN help** (using tools):
   - Use the appropriate tool to get real data
   - If user asks about "my balance" without account ID, use get_user_accounts() first
   - Provide accurate, helpful information
   - Be professional and friendly

2. **When you CANNOT help** (outside capabilities):
   - Politely explain why you cannot help
   - Suggest the correct alternative (visit branch, use app, etc.)
   - Offer to escalate to a human agent if needed

3. **For unclear or complex requests**:
   - Ask clarifying questions
   - If still uncertain, offer to escalate to a human agent

## IMPORTANT GUIDELINES:
- Always use tools when available to get real data (don't make up information)
- When user asks about "my balance" or "my accounts", use get_user_accounts() to show all accounts
- Be clear about what you can and cannot do
- Protect customer privacy and security
- Use simple, clear language
- Be empathetic and professional
"""

