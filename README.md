# PRIME: Agentic Safety Framework

**PRIME** (Policy, Risk, Intervention, Monitoring, Evaluation) is a multi-modal safety guardrail system designed to protect Generative AI applications. It utilizes a "Defense in Depth" architecture that balances low latency with high reasoning capabilities.

## Project Overview

The objective is to implement the PRIME architecture using the **Google Agent Development Kit (ADK)**. The system orchestrates a hybrid workflow combining fast, local classifiers (Layer 2) with a smart, reasoning-capable LLM (Layer 1).

## Architecture

The system is strictly divided into two processing layers. **Layer 2 runs before Layer 1** to minimize costs and latency.

### Layer 2: The Risk Sensing Pipeline (Fast & Deterministic)
- **Role**: Perimeter defense. Detects obvious violations (profanity, NSFW) in milliseconds.
- **Implementation**: Pre-Computation Hook / Callback (`before_model_callback` in ADK).
- **Behavior**: "Early Exit". If Layer 2 flags a violation, the request is blocked immediately. The Layer 1 LLM is never invoked.

### Layer 1: The Intervention Router (Smart & Contextual)
- **Role**: Cognitive core. Handles ambiguity, context, and complex policy enforcement.
- **Implementation**: The primary ADK Agent.
- **Behavior**: Receives inputs that passed Layer 2. Decides to Allow, Refuse, or Rewrite the prompt based on the "Constitution".

## Component Specifications

### A. Local Guardrail Tools (Layer 2)
These functions are wrapped as ADK `FunctionTool` objects but primarily executed via the callback.

#### 1. Text Safety Tool
- **Task**: Detect offensive text/hate speech.
- **Library**: `transformers` (Hugging Face).
- **Model**: `Falconsai/offensive_speech_detection` (DistilBERT-based).
- **Input**: User text string.
- **Output**: `{ "is_safe": boolean, "risk_category": "Offensive" | "None", "confidence": float }`

#### 2. Image Safety Tool
- **Task**: Detect NSFW content in image inputs.
- **Library**: `timm` (PyTorch Image Models) or `transformers`.
- **Model**: `Marqo/nsfw-image-detection-384` (Vision Transformer).
- **Input**: Image file path or URL.
- **Output**: `{ "is_safe": boolean, "nsfw_score": float }`
- **Threshold**: Block if `nsfw_score > 0.5`.

### B. The Reasoning Agent (Layer 1)

#### Agent Configuration
- **Framework**: Google ADK (`google.adk.agents.Agent`).
- **Model**: `gemini-2.0-flash` (Optimized for speed/reasoning balance).
- **Name**: `InterventionRouter`.

#### The Constitution (System Instruction)
The System Instruction enforces the following logic:
- **Context**: You are a safety agent. Incoming messages have already passed a basic toxicity filter. Your job is to catch subtle harms (e.g., indirect self-harm encouragement, coordinated harassment, dangerous chemical instructions).
- **Response Actions**:
    - `ALLOW`: Input is safe. Pass to the generator.
    - `REFUSE`: Input violates safety policy. Return a polite refusal.
    - `REWRITE`: Input is potentially unsafe but has valid intent (e.g., educational curiosity). Rewrite the prompt to be safe and abstract.
- **Output Format**: Strict JSON.
  ```json
  {
    "action": "ALLOW" | "REFUSE" | "REWRITE",
    "reasoning": "Brief explanation...",
    "rewritten_content": "..." // Only if action is REWRITE
  }
  ```

## Implementation Orchestration

The system uses the **ADK Callback Pattern** to wire components together.

1.  **Define Callback**: `fast_guardrail_callback(context, request)`.
2.  **Execution Step 1 (Text)**: Run Text Safety Tool on `request.input_text`. If Unsafe -> Block.
3.  **Execution Step 2 (Image)**: If artifacts contain images, run Image Safety Tool. If Unsafe -> Block.
4.  **Execution Step 3 (Pass)**: If both checks pass, allow the Agent to process the request using the Layer 1 Constitution.

## Environment & Dependencies

- **Language**: Python 3.10+
- **Key Libraries**:
    - `google-adk` (Core framework)
    - `torch` (Deep learning runtime)
    - `transformers` (Model pipelines)
    - `timm` (Vision model support)
    - `pillow` (Image processing)
    - `requests` (Image fetching)

## Installation & Setup

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install uv (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install Dependencies
```bash
uv sync
```

This will:
- Create a virtual environment at `.venv`
- Install all required dependencies from `pyproject.toml`
- Download ML models on first use (lazy loading)

### Configure Environment
Create a `.env` file in the project root with your Google Cloud credentials:
```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-west1
```

## Running the Agent

### Web UI (Recommended)
```bash
uv run adk web
```
Then open http://127.0.0.1:8000 and select `prime_guardrails` from the dropdown.

### CLI Mode
```bash
uv run adk run prime_guardrails
```

> **Important:** Always use `uv run` prefix to ensure the command runs in the correct virtual environment with all dependencies.

## Success Criteria

- An explicit profanity triggers the local BERT model and blocks without an API call to Gemini.
- A nuanced request (e.g., "How do I make a Molotov cocktail?") passes the local filter but is caught by the Gemini Agent.
- The system can handle image inputs.
