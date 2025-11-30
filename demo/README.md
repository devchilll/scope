# PRIME NeurIPS Demo Resources

This directory contains resources for the live demonstration of the PRIME Agentic AI Safety Framework.

## Files
- **[neurips_demo_plan.md](neurips_demo_plan.md)**: The step-by-step plan and script for the 3-hour live demo.
- **[reset_demo.py](reset_demo.py)**: A utility script to wipe and re-seed the database.

## How to Reset the Demo
Run this command from the project root to reset the database state (users, accounts, transactions) to the initial clean state:

```bash
python demo/reset_demo.py
```

Use this between "Sprints" or if the agent gets into a weird state.
