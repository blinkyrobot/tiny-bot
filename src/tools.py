from dotenv import load_dotenv
import os

secrets_path = os.path.join(os.environ.get("TINYBOT_ROOT", "."), "secrets", "api_keys.env")
load_dotenv(dotenv_path=secrets_path)

def get_secret(key, config, default=None):
    return os.environ.get(key) or config.get("secrets", {}).get(key) or default
import subprocess
import requests
import os
import pypdf
import json # Added for parsing skill definitions
import re
from llm import call_llm # Added for direct LLM calls in tool_execute_skill
from datetime import datetime # Added for timestamp in summaries

def tool_exec(command, simple=False):
    try:
        tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=tinybot_root)
        if simple:
            return result.stdout.strip()
        return f"""CODE: {result.returncode}
STDOUT:
{result.stdout}
STDERR:
{result.stderr}"""
    except Exception as e: return f"Error executing command: {e}"

def tool_read(path, tail=None):
# ... (existing tool_read)
    try:
        expanded_path = os.path.expanduser(path)
        print(f"DEBUG: Attempting to read file at path: {expanded_path} (tail: {tail})")
        with open(expanded_path, "r") as f:
            if tail:
                from collections import deque
                lines = deque(f, maxlen=int(tail))
                content = "".join(lines)
                # Enforce a safety character limit for tail reads
                if len(content) > 10000:
                    content = "... [truncated older lines] ...\n" + content[-10000:]
                return content
            return f.read()
    except Exception as e: return f"Error reading file: {e}"

def tool_write(path, content, append=True):
    try:
        tinybot_root = os.path.abspath(os.environ.get("TINYBOT_ROOT", "."))
        
        # Ensure the target path is absolute and normalized
        full_path = os.path.abspath(os.path.join(tinybot_root, path))

        # Security check: ensure the resolved path is within tinybot_root
        if not full_path.startswith(tinybot_root):
            return f"Error: Write access is restricted to the project directory ({tinybot_root}). Attempted to write to {full_path}."

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        mode = "a" if append else "w"
        with open(full_path, mode) as f: f.write(content)
        return f"Successfully wrote to {path} (mode: {mode})."
    except Exception as e: return f"Error writing to file: {e}"

def tool_web_search(config, query):
    search_config = config.get("tools", {}).get("web", {}).get("search", {})
    if not search_config.get("enabled"):
        return "Error: Web search is disabled in config."
    
    secrets = config.get("secrets", {})
    api_key = get_secret("BRAVE_API_KEY", config)
    
    if not api_key:
        return "Error: Brave API key not found in secrets."
    
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query}
    try:
        response = requests.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params, timeout=20)
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
        if not results:
            return "No results found."
        
        output = ""
        for r in results[:5]: # Top 5 results
            output += f"""Title: {r.get('title')}
URL: {r.get('url')}
Snippet: {r.get('description')}

"""
        return output
    except Exception as e:
        return f"Error performing web search: {e}"

def tool_web_fetch(url):
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        # Return first 5000 characters to avoid flooding the LLM
        return response.text[:5000]
    except Exception as e:
        return f"Error fetching URL: {e}"

def tool_read_pdf(path):
    try:
        expanded_path = os.path.expanduser(path)
        print(f"DEBUG: Attempting to read PDF file at path: {expanded_path}")
        with open(expanded_path, "rb") as file:
            reader = pypdf.PdfReader(file)
            text = ""
            for page_num in range(len(reader.pages)):
                text += reader.pages[page_num].extract_text()
            return text
    except FileNotFoundError:
        return f"Error: PDF file not found at {expanded_path}"
    except Exception as e:
        return f"Error reading PDF file {expanded_path}: {e}"

def tool_spawn_subagent(agent, task_description, initial_prompt, required_tools):
    from agents import SubAgent

    print(f"INFO: Spawning Sub-agent for task: '{task_description}'")

    sub_agent_def = {
        "key": f"SubAgent_{hash(task_description)}", # Unique key for sub-agent
        "name": f"SubAgent({task_description[:30]}...)",
        "identity": f"You are a specialized sub-agent tasked with: {task_description}"
    }

    sub_agent = SubAgent(
        config=agent.config,
        agent_def=sub_agent_def, # Pass the constructed agent_def
        global_llm_caller_func=agent.global_llm_caller,
        log_file=agent.log_file,
        task_description=task_description,
        available_skills=getattr(agent, "available_skills", ""),
        required_tools=required_tools,
        parent_model_config=agent.model_config
    )

    # Sub-agents run synchronously and get a minimal session_state
    subagent_session_state = {
        "debug": agent.debug_mode,
        "log_file": agent.log_file,
        "active_agent_key": sub_agent_def["key"], # Use the generated key
        "agents": {sub_agent_def["key"]: sub_agent}, # Add the sub-agent to its own session_state
        "document_context": None,
        "subagents": {}, # Sub-agents can't spawn other sub-agents for now
        "available_skills": getattr(agent, "available_skills", "")
    }
    result = sub_agent.handle_prompt(initial_prompt, subagent_session_state)

    print(f"INFO: Sub-agent finished with result: {result}")
    return f"Sub-agent execution finished. Result: {result}"


def tool_execute_skill(agent, skill_name, parameters):
    # Robustly handle skill name if agent includes file extension
    clean_skill_name = skill_name.replace(".md", "").replace(".markdown", "")
    
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    tinybot_src = os.environ.get("TINYBOT_SRC", ".")
    
    # Try global skills first (in TINYBOT_SRC), then agent-specific skills (in TINYBOT_ROOT)
    skill_file_path = os.path.join(tinybot_src, "skills", f"{clean_skill_name}.md")
    
    # Check agent-specific skills if not found in global
    if not os.path.exists(skill_file_path) and hasattr(agent, "key"):
        agent_skill_path = os.path.join(tinybot_root, "agents", agent.key, "skills", f"{clean_skill_name}.md")
        if os.path.exists(agent_skill_path):
            skill_file_path = agent_skill_path

    if not os.path.exists(skill_file_path):
        return f"Error: Skill '{clean_skill_name}' is not defined as a skill in the /skills directory or agent-specific skills directory."

    with open(skill_file_path, "r") as f:
        content = f.read()

    # In-memory representation of the skill, to be built by parsing the markdown
    skill_def = {
        "name": clean_skill_name,
        "description": "",
        "parameters": {},
        "steps": []
    }

    # Simple state machine for parsing
    current_section = None
    current_step = None
    prompt_buffer = None
    current_arg_key = None # Track current argument for multiline values
    
    for original_line in content.splitlines():
        line = original_line.strip()
        if not line and not (prompt_buffer or current_arg_key):
            continue

        if line.startswith("## Description"):
            current_section = "description"
            continue
        elif line.startswith("## Parameters"):
            current_section = "parameters"
            continue
        elif line.startswith("## Steps"):
            current_section = "steps"
            continue
        
        if current_section == "description":
            if not line.startswith("##"):
                skill_def["description"] += line + " "

        elif current_section == "parameters":
            if line.startswith("-"):
                # Example: - `source_file` (string): The path...
                try:
                    parts = line.split(":", 1)
                    name_match = re.search(r"`([^`]+)`", parts[0])
                    if name_match:
                        name_part = name_match.group(1)
                        type_part = "string"
                        if "(" in parts[0] and ")" in parts[0]:
                             type_part = parts[0].split("(")[1].split(")")[0]
                        desc_part = parts[1].strip() if len(parts) > 1 else ""
                        skill_def["parameters"][name_part] = {"type": type_part, "description": desc_part}
                except: pass

        elif current_section == "steps":
            # New step: "1. **Tool: ...**", "1. **Skill: ...**", "1. **Subagent**", etc.
            if re.match(r"^\d+\.\s+\*\*", line):
                if current_step:
                    skill_def["steps"].append(current_step)
                current_step = {}
                prompt_buffer = None
                current_arg_key = None
                
                if "**Tool:" in line:
                    current_step["type"] = "tool"
                    current_step["tool"] = line.split("**Tool:")[1].strip().split("**")[0].strip()
                    current_step["arguments"] = {}
                elif "**Skill:" in line:
                    current_step["type"] = "skill"
                    current_step["skill"] = line.split("**Skill:")[1].strip().split("**")[0].strip()
                    current_step["arguments"] = {}
                elif "**Step:" in line: # Legacy/Ambiguous
                    current_step["type"] = "ambiguous"
                    current_step["name"] = line.split("**Step:")[1].strip().split("**")[0].strip()
                    current_step["arguments"] = {}
                elif "**Subagent**" in line:
                    current_step["type"] = "subagent"
                    current_step["arguments"] = {}
                elif "**LLM**" in line:
                    current_step["type"] = "llm"
                    current_step["prompt"] = ""
                    current_step["system_prompt"] = ""
                elif "**Output**" in line:
                    current_step["type"] = "output"
                continue

            if current_step:
                # Check for argument match: - `key`: value
                arg_match = re.match(r"^-?\s*`([^`]+)`\s*:\s*(.*)", line)
                if arg_match:
                    key, value = arg_match.groups()
                    value = value.strip().strip("`").strip()
                    current_step["arguments"][key] = value
                    current_arg_key = key
                    continue

                output_match = re.match(r"^-?\s*\*\*Output:\*\*\s*(.*)", line)
                if output_match:
                    current_step["output_key"] = output_match.group(1).strip().strip("`").strip()
                    current_arg_key = None
                    continue
                
                system_prompt_match = re.match(r"^-?\s*\*\*System Prompt:\*\*\s*(.*)", line)
                if system_prompt_match:
                    current_step["system_prompt"] = system_prompt_match.group(1).strip().strip("`").strip()
                    prompt_buffer = "system_prompt"
                    current_arg_key = None
                    continue
                
                prompt_match = re.match(r"^-?\s*\*\*Prompt:\*\*", line)
                if prompt_match:
                    prompt_buffer = "prompt"
                    current_step["prompt"] = ""
                    current_arg_key = None
                    continue
                
                value_match = re.match(r"^-?\s*\*\*Value:\*\*\s*(.*)", line)
                if value_match:
                    current_step["value"] = value_match.group(1).strip().strip("`").strip()
                    prompt_buffer = "value"
                    current_arg_key = None
                    continue
                
                # Handling multiline blocks (Prompts, Values, or tool Arguments)
                if line.startswith("```"):
                    if prompt_buffer in ["prompt", "value", "system_prompt"]:
                        prompt_buffer = prompt_buffer + "_block"
                    elif prompt_buffer in ["prompt_block", "value_block", "system_prompt_block"]:
                        prompt_buffer = None
                    elif current_arg_key:
                        if not hasattr(current_step, "_in_arg_block"):
                            current_step["_in_arg_block"] = False
                        
                        if not current_step["_in_arg_block"]:
                            current_step["_in_arg_block"] = True
                        else:
                            current_step["_in_arg_block"] = False
                            current_arg_key = None
                    continue

                if prompt_buffer == "prompt_block":
                    current_step["prompt"] += original_line + "\n"
                elif prompt_buffer == "value_block":
                    current_step["value"] += original_line + "\n"
                elif prompt_buffer == "system_prompt_block":
                    current_step["system_prompt"] += original_line + "\n"
                elif current_arg_key and current_step.get("_in_arg_block", False):
                    current_step["arguments"][current_arg_key] += original_line + "\n"

    if current_step:
        skill_def["steps"].append(current_step)
    
    if agent.debug_mode:
        print(f"DEBUG: Parsed skill '{skill_name}': {json.dumps(skill_def, indent=2)}")

    # Execution logic starts here, using the parsed skill_def
    try:
        context = dict(parameters)
        context["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(agent, "key"):
            context["agent_key"] = agent.key
        
        for i, step in enumerate(skill_def.get("steps", [])):
            if agent.debug_mode: print(f"DEBUG: Executing skill step {i+1}: {step.get('type')}")
            step_type = step.get("type")

            def substitute(text):
                if not isinstance(text, str): return text
                for key, value in context.items():
                    val_str = str(value)
                    
                    # Strip <think> blocks to save context space, especially for summaries
                    val_str = re.sub(r"<think>.*?</think>", "", val_str, flags=re.DOTALL)
                    
                    # Truncate very long context values (e.g. file contents) if they are being used in a prompt
                    if len(val_str) > 20000:
                         val_str = val_str[:20000] + "\n... [truncated]"
                    text = text.replace(f'{{{{{key}}}}}', val_str)
                
                # Cleanup: If any {{key}} remains, it means the argument was not provided
                text = re.sub(r"{{.*?}}", "(missing argument)", text)
                return text

            if step_type == "tool":
                tool_name = step.get("tool")
                raw_args = {k: substitute(v) for k, v in step.get("arguments", {}).items()}
                args = {k: (v.lower() == "true" if v.lower() == "true" else (False if v.lower() == "false" else v)) if isinstance(v, str) else v for k, v in raw_args.items()}
                
                if agent.debug_mode: print(f"DEBUG: Skill tool call: {tool_name}({args})")
                dispatcher = get_dispatcher(agent, [tool_name])
                if tool_name in dispatcher:
                    result = dispatcher[tool_name](**args)
                    if step.get("output_key"):
                        context[step["output_key"]] = result
                else:
                    return f"Error executing skill '{skill_name}': Tool '{tool_name}' not found in dispatcher."

            elif step_type == "skill":
                target_skill_name = step.get("skill")
                raw_args = {k: substitute(v) for k, v in step.get("arguments", {}).items()}
                if agent.debug_mode: print(f"DEBUG: Skill-to-skill call: {target_skill_name}({raw_args})")
                result = tool_execute_skill(agent, target_skill_name, raw_args)
                if not result.startswith("Error:"):
                    if step.get("output_key"):
                        context[step["output_key"]] = result
                else:
                    return f"Error executing skill '{skill_name}' at nested skill '{target_skill_name}': {result}"

            elif step_type == "ambiguous":
                # Legacy/Backwards compatibility: try tool first, then skill
                name = step.get("name")
                raw_args = {k: substitute(v) for k, v in step.get("arguments", {}).items()}
                args = {k: (v.lower() == "true" if v.lower() == "true" else (False if v.lower() == "false" else v)) if isinstance(v, str) else v for k, v in raw_args.items()}
                
                dispatcher = get_dispatcher(agent, [name])
                if name in dispatcher:
                    result = dispatcher[name](**args)
                else:
                    result = tool_execute_skill(agent, name, raw_args)
                
                if not (isinstance(result, str) and result.startswith("Error:")):
                    if step.get("output_key"):
                        context[step["output_key"]] = result
                else:
                    return f"Error executing skill '{skill_name}' at ambiguous step '{name}': {result}"

            elif step_type == "subagent":
                from agents import SubAgent
                task_description = substitute(step.get("arguments", {}).get("task_description", ""))
                initial_prompt = substitute(step.get("arguments", {}).get("initial_prompt", ""))
                required_tools_str = substitute(step.get("arguments", {}).get("required_tools", "[]"))
                
                try:
                    # Handle both list and string representation of a list
                    if isinstance(required_tools_str, str):
                        required_tools = json.loads(required_tools_str.replace("'", '"'))
                    else:
                        required_tools = required_tools_str
                except:
                    required_tools = ["read", "write", "exec", "execute_skill"]

                if agent.debug_mode: print(f"INFO: Skill-spawned Sub-agent for task: '{task_description}'")

                sub_agent_def = {
                    "key": f"SubAgent_{hash(task_description)}",
                    "name": f"SubAgent({task_description[:30]}...)",
                    "identity": f"You are a specialized sub-agent tasked with: {task_description}"
                }

                sub_agent = SubAgent(
                    config=agent.config,
                    agent_def=sub_agent_def,
                    global_llm_caller_func=agent.global_llm_caller,
                    log_file=agent.log_file,
                    task_description=task_description,
                    available_skills=getattr(agent, "available_skills", ""),
                    required_tools=required_tools,
                    parent_model_config=agent.model_config
                )

                # Use a minimal session_state for the sub-agent
                subagent_session_state = {
                    "debug": agent.debug_mode,
                    "log_file": agent.log_file,
                    "active_agent_key": sub_agent_def["key"],
                    "agents": {sub_agent_def["key"]: sub_agent},
                    "document_context": None,
                    "subagents": {},
                    "available_skills": getattr(agent, "available_skills", "")
                }
                result = sub_agent.handle_prompt(initial_prompt, subagent_session_state)
                
                if step.get("output_key"):
                    context[step["output_key"]] = result

            elif step_type == "llm":
                prompt = substitute(step.get("prompt", ""))
                system_prompt = substitute(step.get("system_prompt", "You are a specialized assistant."))
                
                if agent.debug_mode: print(f"DEBUG: Skill LLM step. Prompt: {prompt[:100]}...")

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
                
                response = call_llm(
                    agent.model_config,
                    messages,
                    tools=[],
                    supports_tools=False,
                    debug=agent.debug_mode
                )
                
                if response and response.get("content"):
                    content = response["content"]
                    if agent.config.get("show_thinking") is False:
                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                    
                    if step.get("output_key"):
                        context[step["output_key"]] = content
                else:
                    return f"Error executing skill '{skill_name}': LLM failed to generate a response for a generative step."

            elif step_type == "output":
                output_val = substitute(step.get("value", "Skill completed."))
                if agent.debug_mode: print(f"DEBUG: Skill final output: {output_val[:100]}...")
                return output_val
        
        return "Skill completed without a specific output value."
        
    except Exception as e:
        return f"Error executing skill '{skill_name}': {e}"


# New: Centralized tool definitions
ALL_TOOL_DEFINITIONS = {
    "exec": {"type": "function", "function": {"name": "exec", "description": "Run shell command.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "simple": {"type": "boolean", "description": "If true, only return the stripped stdout. Use for variables in skills."}}, "required": ["command"]}}},
    "read": {"type": "function", "function": {"name": "read", "description": "Read file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "tail": {"type": "integer", "description": "Optional: Number of lines to read from the end of the file."}}, "required": ["path"]}}},
    "write": {"type": "function", "function": {"name": "write", "description": "Write to file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean", "description": "Append if true, else overwrite."}}, "required": ["path", "content"]}}},
    "execute_skill": {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Run multi-step skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Skill name."},
                    "parameters": {"type": "object", "description": "Skill parameters."}
                },
                "required": ["skill_name", "parameters"]
            }
        }
    },
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."}
                },
                "required": ["query"]
            }
        }
    }
}

# New: Centralized tool functions
ALL_TOOL_FUNCTIONS = {
    "exec": tool_exec,
    "read": tool_read,
    "write": tool_write,
    "execute_skill": tool_execute_skill,
    "web_search": tool_web_search,
}


def get_tools_definition(tool_names=None):
    if tool_names is None:
        return list(ALL_TOOL_DEFINITIONS.values())
    return [ALL_TOOL_DEFINITIONS[name] for name in tool_names if name in ALL_TOOL_DEFINITIONS]

def get_dispatcher(agent, tool_names=None):
    dispatcher = {}
    tools_to_load = tool_names if tool_names is not None else ALL_TOOL_FUNCTIONS.keys()
    
    for name in tools_to_load:
        if name == "execute_skill":
            dispatcher[name] = lambda skill_name, parameters, n=name: ALL_TOOL_FUNCTIONS[n](agent, skill_name, parameters)
        elif name == "spawn_subagent":
            dispatcher[name] = lambda task_description, initial_prompt, required_tools, n=name: ALL_TOOL_FUNCTIONS[n](agent, task_description, initial_prompt, required_tools)
        elif name == "web_search":
            dispatcher[name] = lambda query, n=name: ALL_TOOL_FUNCTIONS[n](agent.config, query)
        elif name in ALL_TOOL_FUNCTIONS:
            dispatcher[name] = ALL_TOOL_FUNCTIONS[name]
    return dispatcher