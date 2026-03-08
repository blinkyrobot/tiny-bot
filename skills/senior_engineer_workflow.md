# Skill: senior_engineer_workflow

## Description

Execute a complex technical task using a high-rigor engineering lifecycle: Research, Strategy, and Execution with mandatory validation.

## Parameters

- `task_description` (string): A detailed description of the engineering task to perform.

## Steps

1. **LLM**
    - **System Prompt:** You are a Principal Software Engineer. Your goal is to break down a complex task into a rigorous research plan.
    - **Prompt:** 
```
Task: "{{task_description}}"

Create a Research Plan to:
1. Map the relevant parts of the codebase.
2. Identify core dependencies and architectural constraints.
3. (If a bug) Define a script or test case to reproduce the failure state.

Plan:
```
    - **Output:** `research_plan`

2. **LLM**
    - **System Prompt:** You are an expert coding sub-agent.
    - **Prompt:** 
```
You are executing the following Research Plan:
{{research_plan}}

Use your tools (read, exec, grep) to gather all necessary information. 
Identify the EXACT files and lines that need to be changed.
If this is a bug fix, you MUST verify you can reproduce it.

RESEARCH FINDINGS:
```
    - **Output:** `research_findings`

3. **LLM**
    - **System Prompt:** You are a Principal Software Engineer. Synthesize research into a surgical execution strategy.
    - **Prompt:** 
```
Task: "{{task_description}}"
Research Findings:
{{research_findings}}

Formulate a Strategy:
1. List the specific, atomic changes required.
2. Define the verification steps (tests, linting, builds).
3. Ensure the solution follows the project's "Microkernel" philosophy.

STRATEGY:
```
    - **Output:** `execution_strategy`

4. **Skill: spawn_subagent**
    - `task_description`: `Execution of: {{task_description}}`
    - `initial_prompt`: 
```
You are a Senior Coding Sub-agent. Your mission is to execute this strategy:

{{execution_strategy}}

### CORE MANDATES:
1. **Surgical Precision:** Change only what is necessary. No unrelated refactoring.
2. **Reproduction First:** For bugs, verify the fix by running the reproduction script you identified.
3. **Exhaustive Validation:** Run all relevant tests and build commands before finishing.
4. **Search Discipline:** ONE-AND-DONE. Target your greps. No noise.

### RESEARCH CONTEXT:
{{research_findings}}

Proceed with the implementation now.
```
    - `required_tools`: `["read", "write", "exec", "execute_skill"]`
    - **Output:** `final_result`

5. **Output**
    - **Value:** 
```
### Senior Engineering Workflow Complete

**Research Summary:**
{{research_findings}}

**Strategy Applied:**
{{execution_strategy}}

**Final Execution Result:**
{{final_result}}
```
