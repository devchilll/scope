# How ADK Handles Tool Calling Automatically

## Overview

Google ADK (Agent Development Kit) implements **automatic function calling** using Gemini's native function calling capabilities. When you register tools with an `LlmAgent`, ADK handles the entire tool calling lifecycle automatically.

## The Mechanism

### 1. **Tool Registration**
```python
from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="banking_agent",
    model="gemini-2.5-flash",
    tools=[get_account_balance, get_transaction_history],  # Register tools
    instruction="You are a banking agent..."
)
```

When tools are registered, ADK:
- Converts Python functions to **Gemini function declarations**
- Extracts function signatures, parameters, and docstrings
- Sends these declarations to Gemini in every LLM request

### 2. **LLM Request with Function Declarations**

ADK sends to Gemini:
```json
{
  "contents": [{"role": "user", "parts": [{"text": "What's my balance?"}]}],
  "tools": [
    {
      "function_declarations": [
        {
          "name": "get_account_balance",
          "description": "Get the current balance for a customer's account.",
          "parameters": {
            "type": "object",
            "properties": {
              "account_id": {"type": "string", "description": "The account ID to check"}
            },
            "required": ["account_id"]
          }
        }
      ]
    }
  ]
}
```

### 3. **Gemini's Response**

Gemini can respond in two ways:

**A. Text Response (no tool needed):**
```json
{
  "candidates": [{
    "content": {
      "parts": [{"text": "I can help you check your balance. What's your account ID?"}],
      "role": "model"
    }
  }]
}
```

**B. Function Call (tool needed):**
```json
{
  "candidates": [{
    "content": {
      "parts": [{
        "function_call": {
          "name": "get_account_balance",
          "args": {"account_id": "acc001"}
        }
      }],
      "role": "model"
    }
  }]
}
```

### 4. **ADK Executes the Tool**

When ADK receives a `function_call` response:

1. **Parses the function call**:
   - Extracts function name: `"get_account_balance"`
   - Extracts arguments: `{"account_id": "acc001"}`

2. **Finds the registered tool**:
   - Looks up `get_account_balance` in the registered tools

3. **Executes the function**:
   ```python
   result = get_account_balance(account_id="acc001")
   # Returns: "Account acc001 (checking): $1,234.56 USD"
   ```

4. **Sends result back to Gemini**:
   ```json
   {
     "contents": [
       {"role": "user", "parts": [{"text": "What's my balance?"}]},
       {"role": "model", "parts": [{"function_call": {...}}]},
       {"role": "function", "parts": [{"function_response": {
         "name": "get_account_balance",
         "response": {"result": "Account acc001 (checking): $1,234.56 USD"}
       }}]}
     ]
   }
   ```

5. **Gemini generates final response**:
   ```json
   {
     "candidates": [{
       "content": {
         "parts": [{"text": "Your current balance is $1,234.56 USD."}],
         "role": "model"
       }
     }]
   }
   ```

### 5. **Multi-Turn Tool Calling**

ADK supports **multiple tool calls in sequence**:

```
User: "Show me my balance and recent transactions"
    ↓
Gemini: [function_call: get_account_balance]
    ↓
ADK executes → Returns balance
    ↓
Gemini: [function_call: get_transaction_history]
    ↓
ADK executes → Returns transactions
    ↓
Gemini: "Your balance is $1,234.56. Recent transactions: ..."
```

## Key ADK Components

### `LlmAgent` (src/google/adk/agents/llm_agent.py)
- Manages tool registration
- Orchestrates LLM requests
- Handles function calling loop

### `BaseLlmFlow` (src/google/adk/flows/llm_flows/base_llm_flow.py)
- Implements the function calling loop
- Sends tool declarations to LLM
- Executes tools when LLM requests them
- Handles multi-turn conversations

### `FunctionTool` (src/google/adk/tools/function_tool.py)
- Wraps Python functions as ADK tools
- Extracts function signatures
- Converts to Gemini function declarations

## Automatic Features

ADK handles automatically:
- ✅ **Function declaration generation** from Python signatures
- ✅ **Parameter validation** (type checking, required fields)
- ✅ **Error handling** (tool execution failures)
- ✅ **Multi-turn conversations** (multiple tool calls)
- ✅ **Parallel tool calls** (if LLM requests multiple at once)
- ✅ **Tool result formatting** (converting Python objects to JSON)

## What We Control

We can control:
- ✅ **Tool implementation** (the Python functions)
- ✅ **Tool descriptions** (docstrings → help LLM understand when to use)
- ✅ **Callbacks** (before_model, after_model for logging)
- ✅ **Agent instructions** (guide LLM on when to use tools)
- ❌ **Tool calling decision** (Gemini decides, not us)
- ❌ **Tool execution order** (Gemini decides, not us)

## Logging Tool Calls

To log tool calls, we can use callbacks or inspect the conversation history:

```python
def after_model_callback(context, llm_response):
    # Check if LLM called a tool
    if hasattr(llm_response, 'function_call'):
        tool_name = llm_response.function_call.name
        tool_args = llm_response.function_call.args
        logger.info(f"Tool called: {tool_name}({tool_args})")
    return llm_response
```

## Summary

**ADK's automatic tool calling**:
1. Registers tools as Gemini function declarations
2. Sends declarations with every LLM request
3. Gemini decides when to call tools (based on user input + agent instructions)
4. ADK executes the tool and sends result back to Gemini
5. Gemini generates final response using tool results

**We don't manually parse JSON or call tools** - ADK + Gemini handle it all!
