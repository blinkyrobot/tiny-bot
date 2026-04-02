import os

def run(agent, parameters):
    target_path = parameters.get("path")
    instruction = parameters.get("instruction")
    
    if not target_path or not instruction:
        return "Error: Missing 'path' or 'instruction' parameter."

    # 1. Read the target file using smart tool_read
    file_content = agent.dispatcher["read"](path=target_path)
    if file_content.startswith("Error:"):
        return file_content

    # 2. Use agent.think() to generate the SEARCH/REPLACE block
    reasoning_task = (
        f"Generate a surgical EDIT BLOCK for the file '{target_path}'.\n"
        f"Goal: {instruction}\n"
        "Your output MUST be a JSON object with 'search' and 'replace' keys. "
        "The 'search' block must be a unique, literal snippet from the file. "
        "The 'replace' block should be the new version of that exact snippet."
    )
    
    agent.log_trace(f"Generating refactor plan for {target_path}...")
    llm_output = agent.think(file_content, reasoning_task)
    
    # Simple extraction of JSON if the LLM adds chatter
    import json
    import re
    json_match = re.search(r"({.*})", llm_output, re.DOTALL)
    if not json_match:
        return f"Error: LLM did not provide a valid JSON edit block: {llm_output}"
    
    try:
        edit_data = json.loads(json_match.group(1))
        search_block = edit_data.get("search")
        replace_block = edit_data.get("replace")
    except Exception as e:
        return f"Error: Failed to parse edit JSON: {e}"

    # 3. Apply the edit
    agent.log_trace(f"Applying surgical edit to {target_path}...")
    result = agent.dispatcher["apply_edit_block"](
        path=target_path,
        search=search_block,
        replace=replace_block,
        fuzzy=True
    )

    return f"Refactoring of {target_path} complete. {result}"
