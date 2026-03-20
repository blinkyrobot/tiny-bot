import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv

def load_secrets():
    """Loads secrets from the .env file."""
    tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))
    secrets_path = os.path.join(tinybot_root, "secrets/api_keys.env")
    if os.path.exists(secrets_path):
        load_dotenv(secrets_path)
    else:
        # Fallback to local secrets if not in home dir
        local_secrets = os.path.join(os.getcwd(), "secrets/api_keys.env")
        if os.path.exists(local_secrets):
            load_dotenv(local_secrets)

def load_config():
    """Loads the main configuration file."""
    load_secrets() # Ensure secrets are loaded into environment
    try:
        tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
        config_path = os.path.join(tinybot_root, "config.json")
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found!"); exit(1)

def setup_logger(config, is_web_interface=False):
    """Sets up the transcript log file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename_template = config["log_file"]
    
    log_filename = log_filename_template.format(timestamp=timestamp)
    
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    full_log_path = os.path.join(tinybot_root, log_filename)
    
    os.makedirs(os.path.dirname(full_log_path), exist_ok=True)
    return full_log_path

def log_debug(message, agent_name=None):
    """Logs a debug message to the debug log file."""
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    debug_log_path = os.path.join(tinybot_root, "logs", "debug.log")
    os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    role_prefix = f"[{agent_name}] " if agent_name else ""
    
    with open(debug_log_path, "a") as f:
        f.write(f"[{timestamp}] {role_prefix}DEBUG: {json.dumps(message, default=str)}\n")

def log_message(log_file, role, message, agent_name=None):
    """Logs a clean message to the transcript."""
    # Ensure we only log string content to the transcript
    if not isinstance(message, str):
        # If it's not a string, it's likely internal state or tool output we don't want in the clean transcript
        # We'll log it to debug instead and return
        log_debug(message, agent_name)
        return

    role_prefix = f"[{agent_name}] " if agent_name else ""
    with open(log_file, "a") as f: 
        f.write(f'**{role_prefix}{role.upper()}**: {message}\n\n')

def discover_agents():
    """Scans the /agents directory for agent definitions."""
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    agents_dir = os.path.join(tinybot_root, "agents")
    agent_definitions = []
    
    if not os.path.exists(agents_dir):
        return agent_definitions

    for entry in os.scandir(agents_dir):
        if entry.is_dir():
            identity_path = os.path.join(entry.path, "identity.md")
            if os.path.exists(identity_path):
                agent_def = load_agent_definition(identity_path)
                if agent_def:
                    agent_def["key"] = entry.name # Use directory name as the key
                    agent_definitions.append(agent_def)
    return agent_definitions

def load_agent_definition(path):
    """Parses an agent's identity.md file into a configuration dictionary."""
    try:
        with open(path, "r") as f:
            content = f.read()
        
        agent_def = {
            "key": "",
            "name": "",
            "class_path": "",
            "default_model": "",
            "tools": [],
            "transitions": {},
            "identity": ""
        }
        
        # Parse Config section
        config_match = re.search(r"## Config\n(.*?)\n##", content, re.DOTALL)
        if config_match:
            config_text = config_match.group(1)
            name_match = re.search(r"-\s*\*\*Name:\*\*\s*(.*)", config_text)
            class_match = re.search(r"-\s*\*\*Class Path:\*\*\s*(.*)", config_text)
            model_match = re.search(r"-\s*\*\*Default Model:\*\*\s*(.*)", config_text)
            tools_match = re.search(r"-\s*\*\*Tools:\*\*\s*(.*)", config_text)
            transitions_match = re.search(r"-\s*\*\*Transitions:\*\*\s*(.*)", config_text)
            
            if name_match: agent_def["name"] = name_match.group(1).strip()
            if class_match: agent_def["class_path"] = class_match.group(1).strip()
            if model_match: agent_def["default_model"] = model_match.group(1).strip()
            if tools_match:
                tools_str = tools_match.group(1).strip()
                agent_def["tools"] = [t.strip() for t in tools_str.split(",")]
            
            if transitions_match:
                transitions_str = transitions_match.group(1).strip()
                # format: target: [word1, word2], target2: [word3]
                # More robust split using regex to find target: [keywords]
                rules = re.findall(r"(\w+):\s*\[(.*?)\]", transitions_str)
                for target, keywords_str in rules:
                    keywords = [k.strip() for k in keywords_str.split(",")]
                    agent_def["transitions"][target.strip()] = keywords
        
        # Use the entire file content for the identity/prompt
        agent_def["identity"] = content.strip()
            
        return agent_def
    except Exception as e:
        print(f"Error loading agent definition from {path}: {e}")
        return None

def discover_skills(agent_key=None):
    """Scans global and agent-specific skills directories and returns an XML summary."""
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    
    skill_dirs = []
    if agent_key:
        agent_skills_dir = os.path.join(tinybot_root, "agents", agent_key, "skills")
        if os.path.exists(agent_skills_dir):
            skill_dirs.append(agent_skills_dir)
    skill_dirs.append(os.path.join(tinybot_root, "skills"))

    skills_data = []
    seen_skills = set()

    for skills_dir in skill_dirs:
        if not os.path.exists(skills_dir):
            continue
            
        for entry in os.scandir(skills_dir):
            if entry.is_file() and entry.name.endswith(".md"):
                skill_name = entry.name.replace(".md", "")
                if skill_name in seen_skills:
                    continue
                
                try:
                    with open(entry.path, "r") as f:
                        content = f.read()
                    
                    desc_match = re.search(r"## Description\n\n?(.*?)(?:\n\n?##|\Z)", content, re.DOTALL)
                    description = desc_match.group(1).strip() if desc_match else "No description available."
                    
                    # Keep it concise: first sentence or first line
                    description = description.split(". ")[0].split("\n")[0].strip()
                    if description and not description.endswith("."):
                        description += "."

                    skills_data.append({
                        "name": skill_name,
                        "description": description,
                        "path": os.path.relpath(entry.path, tinybot_root)
                    })
                    seen_skills.add(skill_name)
                except Exception as e:
                    print(f"Warning: Could not parse skill file {entry.name}: {e}")

    if not skills_data:
        return ""

    xml_lines = ["<available_skills>"]
    for skill in sorted(skills_data, key=lambda x: x["name"]):
        # Manual XML escaping for basic safety
        name = skill['name'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        desc = skill['description'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        loc = skill['path'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        xml_lines.append("  <skill>")
        xml_lines.append(f"    <name>{name}</name>")
        xml_lines.append(f"    <description>{desc}</description>")
        xml_lines.append(f"    <location>{loc}</location>")
        xml_lines.append("  </skill>")
    xml_lines.append("</available_skills>")
    
    return "\n".join(xml_lines)
