# Skill: spawn_subagent

## Description
Delegate a specific, self-contained task to a specialized sub-agent. This is useful for complex generative tasks or when you want to isolate a specific operation.

## Parameters
- `task` (string): A clear and concise description of the task the sub-agent should perform.
- `initial_prompt` (string): The initial instruction or question to provide to the sub-agent.
- `context_files` (array of strings, optional): A list of file paths that the sub-agent might need to refer to. The sub-agent is responsible for reading them if needed.
- `context` (string, optional): Additional text context to provide directly.
- `required_tools` (string): A JSON-formatted list of tools the sub-agent should have access to (e.g., `["read", "write", "exec", "execute_skill"]`).

## Steps

1. **Subagent**
    - `task_description`: `{{task}}`
    - `initial_prompt`: `Task: {{task}}\n\nPrompt: {{initial_prompt}}\n\nRelevant Files: {{context_files}}\n\n### CONTEXT ###\n{{context}}`
    - `required_tools`: `{{required_tools}}`
    **Output:** `subagent_result`

2. **Output**
    **Value:**
```
Sub-agent has completed its task. *beep*
Task: {{task}}
Result:
{{subagent_result}}
```
