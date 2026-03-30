# Skill: inbox_handler

## Description
Processes the agent's inbox by scanning for .SIR files and handling them.

## Parameters
- `inbox_path` (string): The absolute path to the agent's inbox directory.

## Steps
1. **Tool:** exec
   - `command`: ls {{inbox_path}}/*.SIR 2>/dev/null | head -1
   - **Output:** first_file

2. **LLM**
   - **System Prompt:** You are a research agent. Read the inbox file and do research. Use write tool to create a summary file at {{inbox_path}}/../outbox/summary.md.
   - **Prompt:** 1. Read {{first_file}}. 2. Do web research on the topic. 3. Write a summary to {{inbox_path}}/../outbox/summary.md. Include your research findings.
   - **Required Tools:** ["read", "write", "exec", "web_search"]
   - **Output:** inbox_result

3. **Tool:** exec
   - `command`: test -f {{first_file}} && mv {{first_file}} {{inbox_path}}/../archive/ || echo "Done"
   - **Output:** archive_result

4. **Output**
   - **Value:** Processed inbox. Result: {{inbox_result}}
