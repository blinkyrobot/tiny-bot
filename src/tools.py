from dotenv import load_dotenv
import os
from pathlib import Path
import subprocess
import requests
import pypdf
import json
import re
import difflib
from datetime import datetime
from llm import call_llm
import utils

secrets_path = os.path.join(
    os.environ.get("TINYBOT_ROOT", "."), "secrets", "api_keys.env"
)
load_dotenv(dotenv_path=secrets_path)


def get_secret(key, config, default=None):
    return os.environ.get(key) or config.get("secrets", {}).get(key) or default


def parse_search_replace_blocks(text: str) -> list[dict]:
    """
    Extract file path + search/replace blocks from LLM output.
    Returns list of {'path': str, 'search': str, 'replace': str}
    """
    blocks = []
    pattern = r"(?m)^\s*(?P<path>.*)\n\s*<<<<<<< SEARCH\s*\n(?P<search>.*?)\n\s*=======\s*\n(?P<replace>.*?)\n\s*>>>>>>> REPLACE"

    for match in re.finditer(pattern, text, re.DOTALL):
        path_raw = match.group("path").strip()
        path = re.sub(r"^(File|Path|Target):\s*", "", path_raw, flags=re.IGNORECASE)
        path = path.strip("`").strip("*").strip(":").strip()

        search = match.group("search")
        replace = match.group("replace")
        blocks.append({"path": path, "search": search, "replace": replace})

    return blocks


def apply_edit_block(path: Path, search: str, replace: str, fuzzy: bool = True) -> bool:
    """Apply one block; return True if success."""
    if not path.exists():
        print(f"File not found: {path}")
        return False

    original_content = path.read_text(encoding="utf-8")

    # Try exact match first
    if search in original_content:
        new_content = original_content.replace(
            search, replace, 1
        )  # only first occurrence
        path.write_text(new_content, encoding="utf-8")
        print(f"Applied exact edit to {path}")
        return True

    if not fuzzy:
        print(f"Exact SEARCH not found in {path}")
        return False

    # Fuzzy fallback (very helpful for whitespace/indent drift)
    lines = original_content.splitlines(keepends=True)
    search_lines = search.splitlines(keepends=True)
    best_ratio = 0
    best_start = -1

    for i in range(len(lines) - len(search_lines) + 1):
        chunk = "".join(lines[i : i + len(search_lines)])
        ratio = difflib.SequenceMatcher(None, chunk, search).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i

    if best_ratio > 0.85:  # tune threshold (0.9+ stricter, 0.8 more forgiving)
        # Replace the lines
        new_lines = (
            lines[:best_start]
            + replace.splitlines(keepends=True)
            + lines[best_start + len(search_lines) :]
        )
        path.write_text("".join(new_lines), encoding="utf-8")
        print(f"Fuzzy applied to {path} (similarity {best_ratio:.2f})")
        return True

    print(f"No good match found in {path} (best {best_ratio:.2f})")
    return False


def tool_exec(command, simple=False):
    try:
        tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tinybot_root,
        )
        if simple:
            return result.stdout.strip()
        return f"""CODE: {result.returncode}
STDOUT:
{result.stdout}
STDERR:
{result.stderr}"""
    except Exception as e:
        return f"Error executing command: {e}"


def tool_read(path, tail=None):
    try:
        tinybot_root = os.path.abspath(os.environ.get("TINYBOT_ROOT", "."))

        # Try absolute path directly or relative to root
        full_path = os.path.expanduser(path)
        if not os.path.isabs(full_path):
            full_path = os.path.abspath(os.path.join(tinybot_root, path))

        if os.path.exists(full_path) and os.path.isfile(full_path):
            return _read_file_contents(full_path, tail)

        # Smart Search: If not found, look for filename in the project
        filename = os.path.basename(path)
        print(f"DEBUG: File '{path}' not found. Searching for '{filename}' in {tinybot_root}...")
        
        matches = []
        for root, dirs, files in os.walk(tinybot_root):
            if filename in files:
                matches.append(os.path.join(root, filename))
            
            # Prune search to avoid massive trees (optional but recommended)
            if ".git" in dirs: dirs.remove(".git")
            if "node_modules" in dirs: dirs.remove("node_modules")
            if "__pycache__" in dirs: dirs.remove("__pycache__")

        if len(matches) == 1:
            found_path = matches[0]
            rel_path = os.path.relpath(found_path, tinybot_root)
            print(f"DEBUG: Found unique match: {rel_path}. Reading it.")
            content = _read_file_contents(found_path, tail)
            return f"--- FILE FOUND AT: {rel_path} ---\n{content}"
        elif len(matches) > 1:
            rel_matches = [os.path.relpath(m, tinybot_root) for m in matches]
            return f"Error: File '{path}' not found, but multiple files with that name exist. Please specify which one:\n- " + "\n- ".join(rel_matches)
        
        return f"Error: File '{path}' not found and no similar file found in {tinybot_root}."
    except Exception as e:
        return f"Error reading file: {e}"


def _read_file_contents(path, tail=None):
    with open(path, "r") as f:
        if tail:
            from collections import deque
            lines = deque(f, maxlen=int(tail))
            content = "".join(lines)
            if len(content) > 10000:
                content = "... [truncated older lines] ...\n" + content[-10000:]
            return content
        return f.read()


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
        with open(full_path, mode) as f:
            f.write(content)
        return f"Successfully wrote to {path} (mode: {mode})."
    except Exception as e:
        return f"Error writing to file: {e}"


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
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
        if not results:
            return "No results found."

        output = ""
        for r in results[:5]:  # Top 5 results
            output += f"""Title: {r.get("title")}
URL: {r.get("url")}
Snippet: {r.get("description")}

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
        "key": f"SubAgent_{hash(task_description)}",  # Unique key for sub-agent
        "name": f"SubAgent({task_description[:30]}...)",
        "identity": f"You are a specialized sub-agent tasked with: {task_description}",
    }

    sub_agent = SubAgent(
        config=agent.config,
        agent_def=sub_agent_def,  # Pass the constructed agent_def
        global_llm_caller_func=agent.global_llm_caller,
        log_file=agent.log_file,
        task_description=task_description,
        available_skills=getattr(agent, "available_skills", ""),
        required_tools=required_tools,
        parent_model_config=agent.model_config,
    )

    # Sub-agents run synchronously and get a minimal session_state
    subagent_session_state = {
        "debug": agent.debug_mode,
        "log_file": agent.log_file,
        "active_agent_key": sub_agent_def["key"],  # Use the generated key
        "agents": {
            sub_agent_def["key"]: sub_agent
        },  # Add the sub-agent to its own session_state
        "document_context": None,
        "subagents": {},  # Sub-agents can't spawn other sub-agents for now
        "available_skills": getattr(agent, "available_skills", ""),
    }
    result = sub_agent.handle_prompt(initial_prompt, subagent_session_state)

    print(f"INFO: Sub-agent finished with result: {result}")
    return f"Sub-agent execution finished. Result: {result}"


def tool_execute_skill(agent, skill_name, parameters):
    print(
        f"DEBUG: tool_execute_skill CALLED with skill={skill_name}, params={parameters}"
    )
    # Robustly handle skill name if agent includes file extension
    clean_skill_name = skill_name.replace(".md", "").replace(".markdown", "").replace(".py", "")

    # VALIDATION: Check schema if it exists
    schema = utils.get_skill_docs(clean_skill_name)
    if schema and "actions" in schema:
        action = parameters.get("action")
        if not action:
            return f"Error: 'action' parameter is required for skill '{clean_skill_name}'.\n\nUsage Cheatsheet:\n{json.dumps(schema.get('actions', {}), indent=2)}"
        
        if action not in schema["actions"]:
            return f"Error: Unknown action '{action}' for skill '{clean_skill_name}'.\n\nAvailable Actions:\n- " + "\n- ".join(schema["actions"].keys())
        
        # Check required parameters for the action
        action_def = schema["actions"][action]
        required_params = [p for p, d in action_def.get("parameters", {}).items() if d.get("required")]
        missing = [p for p in required_params if p not in parameters]
        if missing:
            return f"Error: Missing required parameters for '{action}': {', '.join(missing)}\n\nAction Details:\n{json.dumps(action_def, indent=2)}"

    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    tinybot_src = os.environ.get("TINYBOT_SRC", ".")

    # Try global skills first (in TINYBOT_SRC), then agent-specific skills (in TINYBOT_ROOT)
    skill_file_path_md = os.path.join(tinybot_src, "skills", f"{clean_skill_name}.md")
    skill_file_path_py = os.path.join(tinybot_src, "skills", f"{clean_skill_name}.py")
    
    # NEW: Modular directory structures
    if not os.path.exists(skill_file_path_py):
        alt_py = os.path.join(tinybot_src, "skills", clean_skill_name, f"{clean_skill_name}.py")
        if os.path.exists(alt_py):
            skill_file_path_py = alt_py
            
    if not os.path.exists(skill_file_path_md):
        alt_md = os.path.join(tinybot_src, "skills", clean_skill_name, f"{clean_skill_name}.md")
        if os.path.exists(alt_md):
            skill_file_path_md = alt_md

    # Check for Python skill first (Python-first architecture)
    if os.path.exists(skill_file_path_py):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            clean_skill_name, skill_file_path_py
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "run"):
            if hasattr(agent, "log_trace"):
                agent.log_trace(f"Starting Python skill: {clean_skill_name}")
            
            print(f"DEBUG: Executing Python skill '{clean_skill_name}'")
            result = module.run(agent, parameters)
            
            if hasattr(agent, "log_trace"):
                agent.log_trace(f"Python skill completed: {clean_skill_name}")
            
            return result
        else:
            return f"Error: Python skill '{clean_skill_name}' does not have a run(agent, parameters) function."

    # Check agent-specific skills if not found in global
    skill_file_path = skill_file_path_md
    if not os.path.exists(skill_file_path) and hasattr(agent, "key"):
        agent_skill_path_py = os.path.join(
            tinybot_root, "agents", agent.key, "skills", f"{clean_skill_name}.py"
        )
        if os.path.exists(agent_skill_path_py):
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                clean_skill_name, agent_skill_path_py
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "run"):
                if hasattr(agent, "log_trace"):
                    agent.log_trace(f"Starting Agent-local Python skill: {clean_skill_name}")
                
                print(f"DEBUG: Executing Agent-local Python skill '{clean_skill_name}'")
                result = module.run(agent, parameters)
                
                if hasattr(agent, "log_trace"):
                    agent.log_trace(f"Agent-local Python skill completed: {clean_skill_name}")
                
                return result

        agent_skill_path_md = os.path.join(
            tinybot_root, "agents", agent.key, "skills", f"{clean_skill_name}.md"
        )
        if os.path.exists(agent_skill_path_md):
            skill_file_path = agent_skill_path_md

    if not os.path.exists(skill_file_path):
        return f"Error: Skill '{clean_skill_name}' is not defined as a skill in the /skills directory or agent-specific skills directory."

    if hasattr(agent, "log_trace"):
        agent.log_trace(f"Starting Markdown skill: {clean_skill_name}")

    with open(skill_file_path, "r") as f:
        content = f.read()

    # In-memory representation of the skill, to be built by parsing the markdown
    skill_def = {
        "name": clean_skill_name,
        "description": "",
        "parameters": {},
        "steps": [],
    }

    # Simple state machine for parsing
    current_section = None
    current_step = None
    prompt_buffer = None
    current_arg_key = None  # Track current argument for multiline values

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
                        skill_def["parameters"][name_part] = {
                            "type": type_part,
                            "description": desc_part,
                        }
                except:
                    pass

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
                    # Handle "**Tool:** exec" format
                    tool_match = re.search(r"\*\*Tool:\*?\*?\s*(\w+)", line)
                    if tool_match:
                        current_step["tool"] = tool_match.group(1)
                    else:
                        current_step["tool"] = (
                            line.split("**Tool:")[1].strip().split("**")[0].strip()
                        )
                    current_step["arguments"] = {}
                elif "**Skill:" in line:
                    current_step["type"] = "skill"
                    current_step["skill"] = (
                        line.split("**Skill:")[1].strip().split("**")[0].strip()
                    )
                    current_step["arguments"] = {}
                elif "**Step:" in line:  # Legacy/Ambiguous
                    current_step["type"] = "ambiguous"
                    current_step["name"] = (
                        line.split("**Step:")[1].strip().split("**")[0].strip()
                    )
                    current_step["arguments"] = {}
                elif "**Subagent**" in line:
                    current_step["type"] = "subagent"
                    current_step["arguments"] = {}
                elif "**LLM**" in line:
                    current_step["type"] = "llm"
                    current_step["prompt"] = ""
                    current_step["system_prompt"] = ""
                    current_step["required_tools"] = [
                        "read",
                        "write",
                        "exec",
                        "web_search",
                    ]
                elif "**Output**" in line:
                    current_step["type"] = "output"
                elif "**Archive**" in line:
                    current_step["type"] = "archive"
                    current_step["arguments"] = {}
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
                    current_step["output_key"] = (
                        output_match.group(1).strip().strip("`").strip()
                    )
                    current_arg_key = None
                    continue

                system_prompt_match = re.match(
                    r"^-?\s*\*\*System Prompt:\*\*\s*(.*)", line
                )
                if system_prompt_match:
                    current_step["system_prompt"] = (
                        system_prompt_match.group(1).strip().strip("`").strip()
                    )
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
                    current_step["value"] = (
                        value_match.group(1).strip().strip("`").strip()
                    )
                    prompt_buffer = "value"
                    current_arg_key = None
                    continue

                # Handling multiline blocks (Prompts, Values, or tool Arguments)
                if line.startswith("```"):
                    if prompt_buffer in ["prompt", "value", "system_prompt"]:
                        prompt_buffer = prompt_buffer + "_block"
                    elif prompt_buffer in [
                        "prompt_block",
                        "value_block",
                        "system_prompt_block",
                    ]:
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
            print(f"DEBUG: Before step {i + 1}: context keys = {list(context.keys())}")
            if agent.debug_mode:
                print(f"DEBUG: Executing skill step {i + 1}: {step.get('type')}")
            step_type = step.get("type")

            def substitute(text):
                if not isinstance(text, str):
                    return text
                print(
                    f"DEBUG substitute: text={text[:80]}..., context keys={list(context.keys())}"
                )
                for key, value in context.items():
                    val_str = str(value)

                    # Strip <think> blocks to save context space, especially for summaries
                    val_str = re.sub(
                        r"<think>.*?</think>", "", val_str, flags=re.DOTALL
                    )

                    # Truncate very long context values (e.g. file contents) if they are being used in a prompt
                    if len(val_str) > 20000:
                        val_str = val_str[:20000] + "\n... [truncated]"
                    text = text.replace(f"{{{{{key}}}}}", val_str)

                # Cleanup: If any {{key}} remains, it means the argument was not provided
                text = re.sub(r"{{.*?}}", "", text)
                return text

            if step_type == "tool":
                print(f"DEBUG: EXECUTING TOOL STEP: {step}")
                tool_name = step.get("tool")
                raw_args = {
                    k: substitute(v) for k, v in step.get("arguments", {}).items()
                }
                args = {
                    k: (
                        v.lower() == "true"
                        if v.lower() == "true"
                        else (False if v.lower() == "false" else v)
                    )
                    if isinstance(v, str)
                    else v
                    for k, v in raw_args.items()
                }

                if agent.debug_mode:
                    print(f"DEBUG: Skill tool call: {tool_name}({args})")
                dispatcher = get_dispatcher(agent, [tool_name])
                if tool_name in dispatcher:
                    result = dispatcher[tool_name](**args)
                    if step.get("output_key"):
                        context[step["output_key"]] = result
                        print(
                            f"DEBUG: Stored in context['{step['output_key']}'] = {str(result)[:50]}..."
                        )
                else:
                    return f"Error executing skill '{skill_name}': Tool '{tool_name}' not found in dispatcher."

            elif step_type == "skill":
                target_skill_name = step.get("skill")
                raw_args = {
                    k: substitute(v) for k, v in step.get("arguments", {}).items()
                }
                if agent.debug_mode:
                    print(
                        f"DEBUG: Skill-to-skill call: {target_skill_name}({raw_args})"
                    )
                result = tool_execute_skill(agent, target_skill_name, raw_args)
                if not result.startswith("Error:"):
                    if step.get("output_key"):
                        context[step["output_key"]] = result
                else:
                    return f"Error executing skill '{skill_name}' at nested skill '{target_skill_name}': {result}"

            elif step_type == "ambiguous":
                # Legacy/Backwards compatibility: try tool first, then skill
                name = step.get("name")
                raw_args = {
                    k: substitute(v) for k, v in step.get("arguments", {}).items()
                }
                args = {
                    k: (
                        v.lower() == "true"
                        if v.lower() == "true"
                        else (False if v.lower() == "false" else v)
                    )
                    if isinstance(v, str)
                    else v
                    for k, v in raw_args.items()
                }

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

                task_description = substitute(
                    step.get("arguments", {}).get("task_description", "")
                )
                initial_prompt = substitute(
                    step.get("arguments", {}).get("initial_prompt", "")
                )
                required_tools_str = substitute(
                    step.get("arguments", {}).get("required_tools", "[]")
                )

                try:
                    # Handle both list and string representation of a list
                    if isinstance(required_tools_str, str):
                        required_tools = json.loads(
                            required_tools_str.replace("'", '"')
                        )
                    else:
                        required_tools = required_tools_str
                except:
                    required_tools = ["read", "write", "exec", "execute_skill"]

                if agent.debug_mode:
                    print(
                        f"INFO: Skill-spawned Sub-agent for task: '{task_description}'"
                    )

                sub_agent_def = {
                    "key": f"SubAgent_{hash(task_description)}",
                    "name": f"SubAgent({task_description[:30]}...)",
                    "identity": f"You are a specialized sub-agent tasked with: {task_description}",
                }

                sub_agent = SubAgent(
                    config=agent.config,
                    agent_def=sub_agent_def,
                    global_llm_caller_func=agent.global_llm_caller,
                    log_file=agent.log_file,
                    task_description=task_description,
                    available_skills=getattr(agent, "available_skills", ""),
                    required_tools=required_tools,
                    parent_model_config=agent.model_config,
                )

                # Use a minimal session_state for the sub-agent
                subagent_session_state = {
                    "debug": agent.debug_mode,
                    "log_file": agent.log_file,
                    "active_agent_key": sub_agent_def["key"],
                    "agents": {sub_agent_def["key"]: sub_agent},
                    "document_context": None,
                    "subagents": {},
                    "available_skills": getattr(agent, "available_skills", ""),
                }
                result = sub_agent.handle_prompt(initial_prompt, subagent_session_state)

                if step.get("output_key"):
                    context[step["output_key"]] = result

            elif step_type == "llm":
                from agents import SubAgent

                prompt = substitute(step.get("prompt", ""))
                system_prompt = substitute(
                    step.get("system_prompt", "You are a specialized assistant.")
                )
                required_tools = step.get(
                    "required_tools", ["read", "write", "exec", "web_search"]
                )

                if agent.debug_mode:
                    print(f"DEBUG: Skill LLM step. Prompt: {prompt[:100]}...")

                sub_agent_def = {
                    "key": getattr(agent, "key", "skill_subagent"),
                    "name": "TaskExecutor",
                    "identity": system_prompt,
                }

                sub_agent = SubAgent(
                    config=agent.config,
                    agent_def=sub_agent_def,
                    global_llm_caller_func=agent.global_llm_caller,
                    log_file=agent.log_file,
                    task_description="Execute the task",
                    available_skills=getattr(agent, "available_skills", ""),
                    required_tools=required_tools,
                    parent_model_config=getattr(agent, "model_config", None),
                )

                result = sub_agent.handle_prompt(
                    prompt, {"debug": agent.debug_mode, "history": []}
                )
                print(f"DEBUG: LLM step DONE, result length={len(str(result))}")
                if step.get("output_key"):
                    context[step.get("output_key")] = result

            elif step_type == "archive":
                import shutil

                step_args = step.get("arguments", {})
                source_output = substitute(step_args.get("source", ""))
                destination = substitute(step_args.get("destination", ""))

                # Extract file path from exec output format "CODE: X\nSTDOUT:\n/path/file.ext\nSTDERR:\n..."
                file_path = None
                lines = source_output.split("\n")
                for i, line in enumerate(lines):
                    if line.strip() == "STDOUT:" and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith("/"):
                            file_path = next_line
                            break

                print(f"DEBUG: Archive: extracted file_path='{file_path}'")

                print(
                    f"DEBUG: Archive step: extracting file from output, destination={destination}"
                )
                if not file_path:
                    context[step.get("output_key", "archive_result")] = (
                        "Archive failed: No file path found in output"
                    )
                    print(f"DEBUG: No file path found")
                else:
                    try:
                        dest_file = os.path.join(
                            destination, os.path.basename(file_path)
                        )
                        os.makedirs(destination, exist_ok=True)
                        shutil.move(file_path, dest_file)
                        context[step.get("output_key", "archive_result")] = (
                            f"Archived {file_path} to {dest_file}"
                        )
                        print(f"DEBUG: Successfully archived {file_path}")
                    except Exception as e:
                        context[step.get("output_key", "archive_result")] = (
                            f"Archive failed: {e}"
                        )
                        print(f"DEBUG: Archive failed: {e}")

            elif step_type == "output":
                output_val = substitute(step.get("value", "Skill completed."))
                if agent.debug_mode:
                    print(f"DEBUG: Skill final output: {output_val[:100]}...")
                
                if hasattr(agent, "log_trace"):
                    agent.log_trace(f"Markdown skill completed: {skill_name}")

                return output_val

        if hasattr(agent, "log_trace"):
            agent.log_trace(f"Markdown skill completed: {skill_name}")

        return "Skill completed without a specific output value."

    except Exception as e:
        return f"Error executing skill '{skill_name}': {e}"


def tool_apply_edit_block(path, search, replace, fuzzy=True):
    try:
        tinybot_root = os.path.abspath(os.environ.get("TINYBOT_ROOT", "."))
        full_path = os.path.abspath(os.path.join(tinybot_root, path))

        # Security check: ensure the resolved path is within tinybot_root
        if not full_path.startswith(tinybot_root):
            return f"Error: Write access is restricted to the project directory ({tinybot_root}). Attempted to write to {full_path}."

        result = apply_edit_block(Path(full_path), search, replace, fuzzy=fuzzy)
        if result:
            return f"Successfully applied edit block to {path}."
        else:
            return f"Error: SEARCH block not found in {path}. Please ensure exact matching if fuzzy=False."
    except Exception as e:
        return f"Error applying edit block to {path}: {e}"


def tool_get_next_message(agent, inbox_path=None):
    """
    Finds the first .SIR file in the agent's inbox, reads it, and returns its content.
    """
    if not inbox_path:
        if hasattr(agent, "agent_dir"):
            inbox_path = os.path.join(agent.agent_dir, "inbox")
        else:
            return "Error: Agent does not have an 'agent_dir' and no 'inbox_path' provided."

    if not os.path.exists(inbox_path):
        return f"Error: Inbox path '{inbox_path}' does not exist."

    import glob

    sir_files = sorted(glob.glob(os.path.join(inbox_path, "*.SIR")))
    if not sir_files:
        return "No new messages."

    first_file = sir_files[0]
    try:
        with open(first_file, "r") as f:
            content = f.read()
        return f"FILE: {first_file}\nCONTENT:\n{content}"
    except Exception as e:
        return f"Error reading message {first_file}: {e}"


def tool_send_message(agent, recipient, content, subject="No Subject"):
    """
    Writes a .SIR file to the recipient's inbox.
    """
    sender = getattr(agent, "key", "Unknown")
    return utils.send_sir_message(sender, recipient, content, subject)


def tool_archive_message(agent, file_path):
    """
    Moves a processed message to the archive directory.
    """
    return utils.archive_sir_message(file_path)


def tool_mcp_call(agent, tool_name, arguments):
    """
    Calls an MCP tool by its namespaced name (e.g., 'manifold:search_markets').
    """
    from mcp_client import get_mcp_client
    
    mcp_client = get_mcp_client(agent.config)
    if not mcp_client:
        return "Error: MCP Client not initialized."
    
    try:
        # Use synchronous wrapper
        result = mcp_client.call_tool(tool_name, arguments)
        return result
    except Exception as e:
        return f"Error executing MCP tool '{tool_name}': {e}"


def tool_mcp_get_tool_info(agent, tool_name):
    """
    Returns the full JSON schema for a specific MCP tool.
    """
    from mcp_client import get_mcp_client
    mcp_client = get_mcp_client(agent.config)
    if not mcp_client:
        return "Error: MCP Client not initialized."
    return mcp_client.get_tool_info(tool_name)


def tool_mcp_list_server_tools(agent, server_name):
    """
    Returns a list of tools available on a specific MCP server.
    """
    from mcp_client import get_mcp_client
    mcp_client = get_mcp_client(agent.config)
    if not mcp_client:
        return "Error: MCP Client not initialized."
    
    tools = mcp_client.get_server_tools(server_name)
    if not tools:
        return f"No tools found for server '{server_name}'."
    
    output = f"Available tools for server '{server_name}':\n"
    for t in tools:
        output += f"- {t['name']}: {t['description']}\n"
    return output


# New: Centralized tool definitions
ALL_TOOL_DEFINITIONS = {
    "mcp_list_server_tools": {
        "type": "function",
        "function": {
            "name": "mcp_list_server_tools",
            "description": "List all available tools for a specific MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {
                        "type": "string",
                        "description": "The name of the MCP server (e.g., 'manifold')."
                    }
                },
                "required": ["server_name"]
            }
        }
    },
    "mcp_get_tool_info": {
        "type": "function",
        "function": {
            "name": "mcp_get_tool_info",
            "description": "Get the detailed JSON schema (parameters, types) for a specific MCP tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The namespaced tool name (e.g., 'server:tool')."
                    }
                },
                "required": ["tool_name"]
            }
        }
    },
    "mcp_call": {
        "type": "function",
        "function": {
            "name": "mcp_call",
            "description": "Call an MCP tool from an external server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The namespaced tool name (e.g., 'server:tool')."
                    },
                    "arguments": {
                        "type": "object",
                        "description": "The arguments for the tool call."
                    }
                },
                "required": ["tool_name", "arguments"]
            }
        }
    },
    "exec": {
        "type": "function",
        "function": {
            "name": "exec",
            "description": "Run shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "simple": {
                        "type": "boolean",
                        "description": "If true, only return the stripped stdout. Use for variables in skills.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    "read": {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "tail": {
                        "type": "integer",
                        "description": "Optional: Number of lines to read from the end of the file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    "write": {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {
                        "type": "boolean",
                        "description": "Append if true, else overwrite.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    "apply_edit_block": {
        "type": "function",
        "function": {
            "name": "apply_edit_block",
            "description": "Apply a surgical search-and-replace block to a file. Useful for small changes without overwriting the entire file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repository root.",
                    },
                    "search": {
                        "type": "string",
                        "description": "The exact block of code to search for.",
                    },
                    "replace": {
                        "type": "string",
                        "description": "The block of code to replace it with.",
                    },
                    "fuzzy": {
                        "type": "boolean",
                        "description": "If True, use fuzzy matching for SEARCH block.",
                        "default": True,
                    },
                },
                "required": ["path", "search", "replace"],
            },
        },
    },
    "execute_skill": {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Run multi-step skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Skill name."},
                    "parameters": {
                        "type": "object",
                        "description": "Skill parameters.",
                    },
                },
                "required": ["skill_name", "parameters"],
            },
        },
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
                "required": ["query"],
            },
        },
    },
    "get_next_message": {
        "type": "function",
        "function": {
            "name": "get_next_message",
            "description": "Get the next message from the agent's inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "inbox_path": {
                        "type": "string",
                        "description": "Optional: Path to the inbox. Defaults to agent's own inbox.",
                    }
                },
            },
        },
    },
    "send_message": {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to another agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "The name or key of the recipient agent.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The body of the message.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Optional: Subject of the message.",
                    },
                },
                "required": ["recipient", "content"],
            },
        },
    },
    "archive_message": {
        "type": "function",
        "function": {
            "name": "archive_message",
            "description": "Archive a processed message file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the message file to archive.",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    "spawn_subagent": {
        "type": "function",
        "function": {
            "name": "spawn_subagent",
            "description": "Spawn a specialized sub-agent for a specific task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "The specific task for the sub-agent.",
                    },
                    "initial_prompt": {
                        "type": "string",
                        "description": "The first message to send to the sub-agent.",
                    },
                    "required_tools": {
                        "type": "string",
                        "description": "Comma-separated list of tools the sub-agent needs.",
                    },
                },
                "required": ["task_description", "initial_prompt", "required_tools"],
            },
        },
    },
}

# New: Centralized tool functions
ALL_TOOL_FUNCTIONS = {
    "mcp_list_server_tools": tool_mcp_list_server_tools,
    "mcp_get_tool_info": tool_mcp_get_tool_info,
    "mcp_call": tool_mcp_call,
    "exec": tool_exec,
    "read": tool_read,
    "write": tool_write,
    "apply_edit_block": tool_apply_edit_block,
    "execute_skill": tool_execute_skill,
    "web_search": tool_web_search,
    "get_next_message": tool_get_next_message,
    "send_message": tool_send_message,
    "archive_message": tool_archive_message,
    "spawn_subagent": tool_spawn_subagent,
}


def get_tools_definition(tool_names=None):
    if tool_names is None:
        return list(ALL_TOOL_DEFINITIONS.values())

    if isinstance(tool_names, str):
        tool_names = [t.strip() for t in tool_names.split(",") if t.strip()]

    return [
        ALL_TOOL_DEFINITIONS[name]
        for name in tool_names
        if name in ALL_TOOL_DEFINITIONS
    ]


def get_dispatcher(agent, tool_names=None):
    dispatcher = {}

    if isinstance(tool_names, str):
        tool_names = [t.strip() for t in tool_names.split(",") if t.strip()]

    tools_to_load = tool_names if tool_names is not None else ALL_TOOL_FUNCTIONS.keys()

    for name in tools_to_load:
        if name == "execute_skill":
            dispatcher[name] = (
                lambda skill_name, parameters, n=name: ALL_TOOL_FUNCTIONS[n](
                    agent, skill_name, parameters
                )
            )
        elif name == "spawn_subagent":
            dispatcher[name] = (
                lambda task_description,
                initial_prompt,
                required_tools,
                n=name: ALL_TOOL_FUNCTIONS[n](
                    agent, task_description, initial_prompt, required_tools
                )
            )
        elif name == "web_search":
            dispatcher[name] = lambda query, n=name: ALL_TOOL_FUNCTIONS[n](
                agent.config, query
            )
        elif name in ["get_next_message", "send_message", "archive_message", "mcp_call", "mcp_get_tool_info", "mcp_list_server_tools"]:
            dispatcher[name] = (
                lambda *args, n=name, **kwargs: ALL_TOOL_FUNCTIONS[n](
                    agent, *args, **kwargs
                )
            )
        elif name in ALL_TOOL_FUNCTIONS:
            dispatcher[name] = ALL_TOOL_FUNCTIONS[name]
    return dispatcher
