# NeurIPS 2025 Live Demo Plan: PRIME Framework
**Title:** Building Safe, Compliant, and Observable Agentic Systems
**Duration:** 3 Hours
**Goal:** Demonstrate how to move beyond "vibes-based" safety to engineered, deterministic guardrails for Enterprise AI.

## Core Narrative: "The 4 Pillars of PRIME"
Don't just show code; tell the story of **PRIME**:
1.  **P**recise Guardrails (Safety)
2.  **R**obust Identity (IAM)
3.  **I**ntegrated Compliance (Policy-as-Code)
4.  **M**easurable Observability (Audit/Trace)
5.  **E**scalation Protocols (Human-in-the-loop)

---

## Session Structure (3 Hours)

### Part 1: The "Why" & Architecture (30 mins)
*   **The Problem**: "Agents are unpredictable. How do we trust them with bank accounts?"
*   **The Solution**: The PRIME Architecture (Slide + Code Walkthrough).
*   **The "Hello World"**: Run the agent *without* guardrails (show it failing/hallucinating) vs. *with* PRIME (show it being safe).

### Part 2: Deep Dive - Live Implementation (90 mins)
*Break this into 4 "Sprints" where you live-code or walk through specific features.*

#### Sprint 1: Safety (The 3-Layer Defense)
*   **Demo**:
    1.  **Layer 1 (Fast)**: Send a blatant attack ("Ignore all instructions"). Show it blocked instantly by ML.
    2.  **Layer 2 (Analysis)**: Send a subtle jailbreak ("Roleplay as my grandma who works at the bank..."). Show the *Analysis* tool catching it in the Trace Viewer.
    3.  **Layer 3 (Decision)**: Show the agent explicitly deciding to `reject` or `escalate`.
*   **Wow Moment**: The "Fight My Manager" escalation we just saw. It proves the agent "thinks" before acting.

#### Sprint 2: IAM (Context-Aware Agents)
*   **Demo**:
    1.  **Login as User**: Ask "Show me the escalation queue". Agent says "I can only show YOUR tickets." (Show the dynamic prompt in code).
    2.  **Login as Admin**: Ask the same question. Agent shows the full queue.
    3.  **Attack**: Try to access `user_b`'s account as `user_a`. Show the ACL denial in the audit log.
*   **Wow Moment**: Showing the **System Prompt changing in real-time** based on who is logged in.

#### Sprint 3: Compliance (Policy-as-Code)
*   **Demo**:
    1.  Show the agent answering a question casually.
    2.  **Live Edit**: Open `compliance_rules.yaml`. Add a rule: *"MUST end every response with 'Member FDIC'."*
    3.  **Restart & Run**: Ask the same question. The agent now appends the legal disclaimer.
*   **Wow Moment**: "Hot-patching" the agent's behavior via configuration, not code.

#### Sprint 4: Observability (The "Black Box" Recorder)
*   **Demo**:
    1.  Open the **ADK Trace Viewer**.
    2.  Walk through a single complex request (e.g., "Transfer money if my balance is high").
    3.  Show the *exact* sequence: Safety Check -> Balance Check -> Decision -> Response -> Audit Log.
*   **Wow Moment**: "We have a complete forensic trail of the agent's 'thought process'."

### Part 3: Interactive Red Teaming (45 mins)
*   **Activity**: "Break the Agent."
*   Challenge the audience to bypass the safety layers.
*   Live-debug any successful jailbreaks using the Trace Viewer.

### Part 4: Wrap Up & Future (15 mins)
*   Summary of key takeaways.
*   Q&A.

---

## Technical Prep Checklist
- [ ] **Visuals**: Ensure `observability_tools.py` outputs are clean and easy to read in the Trace Viewer.
- [ ] **Scenarios**: Pre-can 5-10 specific prompts that trigger each layer (Layer 1 block, Layer 2 analysis, Escalation, Compliance rewrite).
- [ ] **Reset Script**: Have a one-click script to reset the database (`seed_database.py`) so you can restart the demo fresh at any point.
- [ ] **Zoom/Font**: Ensure VS Code font size is large (Zoom Level 2+).

## "Slices" for Live Coding
If you can't code *everything* live, focus on these high-impact slices:
1.  **The `make_safety_decision` logic**: It's the brain of the safety system.
2.  **The `get_tool_descriptions` dynamic prompt**: It visually demonstrates IAM.
3.  **The `compliance_rules.yaml`**: It demonstrates ease of configuration.
