import json
import os
import re
import shutil
from datetime import datetime
from dotenv import dotenv_values

def load_secrets():
    log_debug("Loading secrets.")
    """
    Loads secrets from the .env file and returns them as a dictionary.
    It does NOT modify the environment.
    """
    tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))
    secrets_path = os.path.join(tinybot_root, "secrets/api_keys.env")
    
    secrets = {}
    if os.path.exists(secrets_path):
        log_debug("Found secret path.")
        secrets.update(dotenv_values(secrets_path))
    else:
        # Fallback to local secrets if not in home dir
        local_secrets = os.path.join(os.getcwd(), "secrets/api_keys.env")
        if os.path.exists(local_secrets):
            secrets.update(dotenv_values(local_secrets))
            
    return secrets

def load_config():
    log_debug("Loading config.")
    """Loads the main configuration file and merges secrets into it."""
    config = {}
    secrets = load_secrets()

    try:
        tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
        config_path = os.path.join(tinybot_root, "config.json")
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Warning: config.json not found. Using default settings.")

    # Merge secrets into the main config object under a dedicated key
    config["secrets"] = secrets
    return config

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
        config_match = re.search(r"## Config\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
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
                agent_def["tools"] = [t.strip() for t in tools_str.split(",") if t.strip()]
            
            if transitions_match:
                transitions_str = transitions_match.group(1).strip()
                rules = re.findall(r"(\w+):\s*\[(.*?)\]", transitions_str)
                for target, keywords_str in rules:
                    keywords = [k.strip() for k in keywords_str.split(",")]
                    agent_def["transitions"][target.strip()] = keywords

        # Fallback: Parse dedicated ## Tools section if no tools found in Config
        if not agent_def["tools"]:
            tools_section_match = re.search(r"## Tools\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
            if tools_section_match:
                tools_text = tools_section_match.group(1)
                # Look for bullet points like "- exec" or "- exec: description"
                tool_lines = re.findall(r"-\s*(\w+)", tools_text)
                if tool_lines:
                    agent_def["tools"] = tool_lines
        
        # Use the entire file content for the identity/prompt
        agent_def["identity"] = content.strip()
            
        return agent_def
    except Exception as e:
        print(f"Error loading agent definition from {path}: {e}")
        return None

def discover_skills(agent_key=None):
    """Scans global and agent-specific skills directories and returns an XML summary."""
    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
    
    # Robustly determine the source root for global skills
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tinybot_src = os.environ.get("TINYBOT_SRC", project_root)
    
    skill_dirs = []
    if agent_key:
        agent_skills_dir = os.path.join(tinybot_root, "agents", agent_key, "skills")
        if os.path.exists(agent_skills_dir):
            skill_dirs.append(agent_skills_dir)
    
    skill_dirs.append(os.path.join(tinybot_src, "skills"))
    
    # New: Also discover API manifests
    api_dir = os.path.join(tinybot_src, "api")
    if os.path.exists(api_dir):
        skill_dirs.append(api_dir)

    skills_data = []
    seen_skills = set()

    for skills_dir in skill_dirs:
        if not os.path.exists(skills_dir):
            continue
            
        for entry in os.scandir(skills_dir):
            if not entry.is_file():
                continue
                
            skill_name = entry.name
            description = "No description available."
            
            # Handle Markdown (.md)
            if entry.name.endswith(".md"):
                skill_name = entry.name.replace(".md", "")
                if skill_name in seen_skills: continue
                try:
                    with open(entry.path, "r") as f:
                        content = f.read()
                    desc_match = re.search(r"## Description\n\n?(.*?)(?:\n\n?##|\Z)", content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                except: pass

            # Handle Python (.py)
            elif entry.name.endswith(".py"):
                skill_name = entry.name.replace(".py", "")
                if skill_name in seen_skills: continue
                # We can't easily parse docstrings without importing, but we can try a simple regex for first comment/docstring
                try:
                    with open(entry.path, "r") as f:
                        content = f.read()
                    # Try to find a docstring or top-level comment
                    doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                    if doc_match:
                        description = doc_match.group(1).strip()
                except: pass

            # Handle YAML (.yaml) - These are API Manifests
            elif entry.name.endswith(".yaml"):
                skill_name = entry.name.replace(".yaml", "")
                # We keep manifests distinct by prepending "API: " or just the service name
                if f"API:{skill_name}" in seen_skills: continue
                try:
                    import yaml
                    with open(entry.path, "r") as f:
                        manifest = yaml.safe_load(f)
                    description = f"Native API Manifest for {manifest.get('name', skill_name)}. Use via api_runner."
                    skill_name = f"API:{skill_name}"
                except: pass
            else:
                continue

            if skill_name in seen_skills:
                continue

            # Clean up description (first sentence/line)
            description = description.split(". ")[0].split("\n")[0].strip()
            if description and not description.endswith("."):
                description += "."

            abs_skills_dir = os.path.abspath(skills_dir)
            abs_tinybot_src = os.path.abspath(tinybot_src)
            base_path = tinybot_src if abs_skills_dir.startswith(abs_tinybot_src) else tinybot_root
            
            skills_data.append({
                "name": skill_name,
                "description": description,
                "path": os.path.relpath(entry.path, base_path)
            })
            seen_skills.add(skill_name)

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

def parse_sir(content):
    """
    Parses a .SIR file content into headers and body.
    """
    headers = {}
    parts = content.split("\n\n", 1)
    header_lines = parts[0].split("\n")
    for line in header_lines:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().upper()] = v.strip()
    
    body = parts[1] if len(parts) > 1 else ""
    return headers, body

def send_sir_message(sender_name, recipient_key, content, subject="No Subject"):
    """
    Writes a .SIR file to the recipient's inbox.
    """
    tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))

    # Resolve recipient inbox
    recipient_dir = os.path.join(tinybot_root, "agents", recipient_key.lower())
    inbox_path = os.path.join(recipient_dir, "inbox")

    if not os.path.exists(recipient_dir):
        return f"Error: Recipient agent directory '{recipient_dir}' not found."

    os.makedirs(inbox_path, exist_ok=True)

    # Generate filename: timestamp_sender.SIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{sender_name.replace(' ', '_')}.SIR"
    file_path = os.path.join(inbox_path, filename)

    # Construct .SIR content
    sir_content = f"FROM: {sender_name}\n"
    sir_content += f"TO: {recipient_key}\n"
    sir_content += f"DATE: {datetime.now().isoformat()}\n"
    sir_content += f"SUBJECT: {subject}\n\n"
    sir_content += content

    try:
        with open(file_path, "w") as f:
            f.write(sir_content)
        return f"Message sent to {recipient_key} ({filename})."
    except Exception as e:
        return f"Error sending message to {recipient_key}: {e}"

def archive_sir_message(file_path):
    """
    Moves a processed message to the archive directory.
    """
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' not found."

    try:
        inbox_dir = os.path.dirname(file_path)
        archive_dir = os.path.join(os.path.dirname(inbox_dir), "archive")
        os.makedirs(archive_dir, exist_ok=True)

        dest_path = os.path.join(archive_dir, os.path.basename(file_path))
        shutil.move(file_path, dest_path)
        return f"Archived {os.path.basename(file_path)} to {archive_dir}."
    except Exception as e:
        return f"Error archiving message: {e}"

def get_agent_key_by_name(name, agents_dict):
    """
    Attempts to resolve an agent's key from its display name.
    If no match is found, returns the name itself (case-normalized) as a fallback.
    """
    if not name:
        return None
        
    normalized_name = name.lower().strip()
    
    # 1. Direct key match
    if normalized_name in agents_dict:
        return normalized_name
        
    # 2. Search by agent_name attribute
    for key, agent in agents_dict.items():
        if hasattr(agent, "agent_name") and agent.agent_name.lower() == normalized_name:
            return key
            
    # 3. Fallback: just use the normalized name as the key
    return normalized_name
