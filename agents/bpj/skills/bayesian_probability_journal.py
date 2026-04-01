import os

def run(agent, parameters):
    journal_topic = parameters.get("journal_topic")
    output_filename = parameters.get("output_filename")
    
    if not journal_topic or not output_filename:
        return "Error: Missing journal_topic or output_filename."

    # 1. Determine path and check for existing entry
    # Using agent.agent_dir to resolve path correctly
    tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))
    journal_path = os.path.join(tinybot_root, "agents", "bpj", "journal", output_filename)
    
    file_exists = os.path.exists(journal_path)
    current_entry = ""
    if file_exists:
        try:
            with open(journal_path, 'r') as f:
                current_entry = f.read()
        except Exception as e:
            return f"Error reading existing journal: {e}"

    # 2. Scout for latest data (Spawn Sub-agent)
    # Note: We use the dispatcher to call tools
    task_desc = (
        f"Search/scout for the latest signals and data related to {journal_topic}. "
        "PROTOCOL: Perform extensive research using reputable sources (official docs, news, academic papers). "
        "You MUST provide specific citations/URLs for all data. "
        "ADHERENCE: Your report must be strictly evidence-based; do not include information not found in your search results."
    )
    initial_prompt = f"I need you to scout for the latest data on '{journal_topic}'. Use your web_search tool to find recent information, analyze it according to the protocol, and provide a detailed report. Start now."
    
    scout_res = agent.dispatcher["spawn_subagent"](
        task_description=task_desc,
        initial_prompt=initial_prompt,
        required_tools="web_search,read"
    )
    
    # Extract the actual content from the spawn_subagent result string
    scout_report = scout_res.replace("Sub-agent execution finished. Result: ", "")

    # 3. Dispatch to the appropriate skill
    if not file_exists:
        print(f"DEBUG: Journal {output_filename} not found. Triggering create_journal.")
        result = agent.dispatcher["execute_skill"](
            skill_name="create_journal",
            parameters={
                "journal_topic": journal_topic,
                "output_filename": output_filename,
                "scout_report": scout_report
            }
        )
    else:
        print(f"DEBUG: Journal {output_filename} found. Triggering update_journal.")
        result = agent.dispatcher["execute_skill"](
            skill_name="update_journal",
            parameters={
                "journal_topic": journal_topic,
                "output_filename": output_filename,
                "scout_report": scout_report,
                "current_entry": current_entry
            }
        )

    return result
