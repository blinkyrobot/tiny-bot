# Conductor Manager Skill

## Description
Manages the lifecycle of specialized sub-agents. Orchestrates agent switching, context hand-offs, and state persistence by spawning agents based on role identities stored in $TINYBOT_ROOT/agents/[role]/identity.md.

## Parameters
- `agent_role`: The directory name of the agent (e.g., `ceo`, `engineer`, `qa_specialist`, `shipping_specialist`).
- `action`: The action to perform (`spawn`, `activate`, `archive`).

## Usage
- `execute_skill(skill_name="conductor_manager", parameters={"agent_role": "ceo", "action": "spawn"})`
