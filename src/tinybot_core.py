import json
import importlib
import os
import glob

from utils import (
    load_config,
    setup_logger,
    log_message,
    log_debug,
    discover_agents,
    discover_skills,
    parse_sir,
    send_sir_message,
    archive_sir_message,
    get_agent_key_by_name,
)
from llm import call_llm
from session_manager import SessionManager
from mcp_client import get_mcp_client


class TinyBotCore:
    def __init__(self, config=None, is_web_interface=False):
        self.config = config if config is not None else load_config()
        self.global_llm_caller_func = call_llm
        self.is_web_interface = is_web_interface
        self.session_manager = SessionManager()
        
        # Initialize MCP Client
        self.mcp_client = get_mcp_client(self.config)
        mcp_skills = ""
        try:
            # List available MCP servers instead of every individual tool
            servers = self.config.get("mcpServers", {})
            if servers:
                mcp_skills += "\n### AVAILABLE MCP SERVERS ###"
                for server_name in servers:
                    mcp_skills += f"\n- {server_name} (MCP Server): Use `mcp_list_server_tools` to see what this server can do."
        except Exception as e:
            log_debug(f"Error discovering MCP servers: {e}")

        # Initialize base state
        self.mcp_manifest = mcp_skills
        initial_state = {
            "debug": self.config.get("debug", False),
            "log_file": setup_logger(self.config, is_web_interface=is_web_interface),
            "active_agent_key": self.config.get("default_agent", "GeneralChatAgent"),
            "available_skills": discover_skills() + self.mcp_manifest,
        }
        self.session_manager.state.update(initial_state)

        self._load_agents()
        self._ensure_default_agent_active()

    def initialize(self):
        """Lifecycle hook for engine startup."""
        log_debug("TinyBot Engine Core Initializing... *whir*")
        return True

    def shutdown(self):
        """Lifecycle hook for engine shutdown."""
        log_debug("TinyBot Engine Core Shutting down... *clank*")
        try:
            self.mcp_client.shutdown()
        except Exception as e:
            log_debug(f"Error during MCP client shutdown: {e}")
        return True

    def register_agent(self, agent_def):
        key = agent_def["key"]
        class_path = agent_def["class_path"]

        try:
            if ":" in class_path:
                module_path, class_name = class_path.split(":")
                module_name = (
                    module_path.replace("src/", "").replace("/", ".").replace(".py", "")
                )
                module = importlib.import_module(module_name)
                agent_class = getattr(module, class_name)

                # Combine filesystem skills with discovered MCP tools
                agent_skills = discover_skills(key) + self.mcp_manifest
                agent_instance = agent_class(
                    self.config,
                    agent_def,
                    self.global_llm_caller_func,
                    self.session_manager.state["log_file"],
                    available_skills=agent_skills,
                )
                self.session_manager.update_agent(key, agent_instance)
                if self.session_manager.state["debug"]:
                    print(f"DEBUG: Loaded agent '{key}' from {class_path}")
                return True
        except Exception as e:
            print(f"Error loading agent '{key}': {e}")
        return False

    def _load_agents(self):
        for agent_def in discover_agents():
            self.register_agent(agent_def)

    def _ensure_default_agent_active(self):
        state = self.session_manager.get_state()
        if state["active_agent_key"] not in state["agents"]:
            if state["agents"]:
                state["active_agent_key"] = list(state["agents"].keys())[0]

    def switch_active_agent(self, new_agent_key, new_prompt=None):
        state = self.session_manager.get_state()
        if new_agent_key not in state["agents"]:
            return

        self.session_manager.set_active_agent(new_agent_key)
        new_agent = self.session_manager.get_active_agent()

        if new_prompt:
            new_agent.handle_prompt(new_prompt, state)

    def check_agent_inboxes(self):
        """
        Check all registered agents for messages. 
        Background agents auto-reply; the Active agent receives messages in-context.
        """
        state = self.session_manager.get_state()
        active_key = state.get("active_agent_key")
        tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))
        
        notifications = []
        active_agent_messages = []
        
        # 1. Snapshot: Find all messages that exist right now
        pending_work = []
        for agent_key, agent in state.get("agents", {}).items():
            inbox_path = os.path.join(tinybot_root, "agents", agent_key.lower(), "inbox")
            if os.path.exists(inbox_path):
                sir_files = glob.glob(os.path.join(inbox_path, "*.SIR"))
                for f in sir_files:
                    pending_work.append((agent_key, agent, f))

        # 2. Process the snapshot
        for agent_key, agent, file_path in pending_work:
            try:
                with open(file_path, "r") as f:
                    content = f.read()
                
                headers, body = parse_sir(content)
                sender = headers.get("FROM", "Unknown")
                subject = headers.get("SUBJECT", "No Subject")

                if agent_key == active_key:
                    # Priority 1: Deliver to the human-facing agent
                    active_agent_messages.append(f"--- NEW MESSAGE ---\nFROM: {sender}\nSUBJECT: {subject}\nCONTENT:\n{body}\n--------------------")
                    archive_sir_message(file_path)
                    log_debug(f"Delivered message from {sender} to active agent {agent_key}")
                else:
                    # Priority 2: Full Tool-Calling Loop for background agents
                    log_debug(f"Background processing: {agent_key} processing message from {sender}")
                    
                    # We give the agent full context but instruct it to be concise 
                    # and detect completion to avoid infinite loops.
                    wrapped_input = (
                        f"SYSTEM: Automated request from {sender} (Subject: {subject}).\n"
                        "Process this. If it's just a 'Thank you' or task complete, respond with '[NO_REPLY]'. "
                        "Otherwise, provide your findings.\n\n"
                        f"CONTENT: {body}"
                    )
                    
                    agent.handle_prompt(wrapped_input, state)
                    response = getattr(agent, "last_response", "")

                    if sender != "Unknown" and response.strip() and "[NO_REPLY]" not in response:
                        send_sir_message(agent_key, sender, response, subject=f"Re: {subject}")
                    
                    archive_sir_message(file_path)
                    notifications.append(f"[{agent_key}] Processed task from {sender}")

            except Exception as e:
                log_debug(f"Error in messaging loop for {agent_key}: {e}")
        
        # Return background notifications and any messages meant for the active agent
        return "\n\n".join(notifications), "\n\n".join(active_agent_messages)

    def process(self, user_input):
        """Main entry point for processing messages."""
        # Check inboxes and get messages for the active agent
        bg_notifications, active_agent_mail = self.check_agent_inboxes()
        
        # Inject incoming mail into the active agent's prompt
        full_input = user_input
        if active_agent_mail:
            full_input = f"SYSTEM: Incoming messages for you:\n{active_agent_mail}\n\n---\n\nUSER: {user_input}"
            
        response = self.process_user_input(full_input)
        
        if bg_notifications:
            return f"{bg_notifications}\n\n---\n\n{response}"
        return response

    def process_user_input(self, user_input):
        if not user_input or not user_input.strip():
            return ""

        state = self.session_manager.get_state()
        active_agent_key = state.get("active_agent_key")
        log_file = state["log_file"]
        log_message(log_file, "user", user_input, active_agent_key)

        if user_input.strip().lower() == "/exit":
            active_agent = state["agents"].get(active_agent_key)
            if active_agent:
                # Determine memory path - check agent instance or its definition
                memory_path = getattr(active_agent, "memory_path", None)
                if not memory_path:
                    # Fallback: try to find it in the agent's directory
                    tinybot_root = os.environ.get("TINYBOT_ROOT", os.path.expanduser("~/.tinybot"))
                    memory_path = os.path.join(
                        tinybot_root,
                        "agents",
                        active_agent_key.lower().replace("agent", ""),
                        "memory.md",
                    )

                exit_prompt = (
                    f"SYSTEM: The user has requested to exit. Please execute the 'summarize_session' skill now. "
                    f"Use session_transcript_path='{log_file}' and destination_memory_path='{memory_path}'. "
                    f"After the skill execution is confirmed, acknowledge the exit. *clank*"
                )
                active_agent.handle_prompt(exit_prompt, state)
                response_content = (
                    active_agent.last_response
                    if hasattr(active_agent, "last_response")
                    else "Exiting... *beep*"
                )
                log_message(log_file, "assistant", response_content, active_agent_key)
                # Return the summary response with a signal suffix
                return f"{response_content}\n\n[SIGNAL:EXIT]"
            return "[SIGNAL:EXIT]"

        if user_input.strip().startswith("/"):
            return self.handle_orchestrator_command(user_input)

        active_agent = state["agents"].get(active_agent_key)

        if not active_agent:
            if not state["agents"]:
                err = "Error: No agents loaded."
                log_debug(err)
                return err

            fallback_key = list(state["agents"].keys())[0]
            self.session_manager.set_active_agent(fallback_key)
            active_agent_key = fallback_key
            active_agent = state["agents"][active_agent_key]

        # Execute Agent Logic
        transition_signal = active_agent.handle_prompt(user_input, state)

        # Capture Response
        response_content = (
            active_agent.last_response
            if hasattr(active_agent, "last_response") and active_agent.last_response
            else "No direct response from agent."
        )

        # Handle Transitions
        if transition_signal:
            target_agent_key = transition_signal
            new_prompt = None

            if ":" in transition_signal:
                parts = transition_signal.split(":", 1)
                target_agent_key = parts[0]
                new_prompt = parts[1] if len(parts) > 1 else None

            if target_agent_key in state["agents"]:
                self.switch_active_agent(target_agent_key, new_prompt)
                new_active_agent_key = state["active_agent_key"]
                new_active_agent = state["agents"][new_active_agent_key]

                response_content += (
                    f"\n\n*clank* Switched to {new_active_agent_key} agent. *beep*"
                )
                if (
                    hasattr(new_active_agent, "last_response")
                    and new_active_agent.last_response
                ):
                    response_content += f"\n\n{new_active_agent.last_response}"
            else:
                log_debug(
                    f"Warning: Agent returned unknown transition signal: '{transition_signal}'"
                )

        log_message(state["log_file"], "assistant", response_content, active_agent_key)
        return response_content

    def handle_orchestrator_command(self, user_input):
        command_parts = user_input.strip().lower().split(" ", 1)
        command = command_parts[0]
        arg = command_parts[1] if len(command_parts) > 1 else ""
        response_messages = []
        state = self.session_manager.get_state()

        if command == "/debug":
            active_agent_key = state.get("active_agent_key")
            active_agent = state["agents"].get(active_agent_key)
            if active_agent:
                response_messages.append(
                    f"--- AGENT PROMPT CONTEXT ---\n{json.dumps(getattr(active_agent, 'history', []), indent=2)}\n----------------------------"
                )
            else:
                response_messages.append("Error: Could not find active agent to debug.")
        elif command == "/agents":
            active_agent_key = state.get("active_agent_key")
            agent_lines = ["Available Agents: *clank*"]
            for agent_key in state["agents"]:
                suffix = " [ACTIVE]" if agent_key == active_agent_key else ""
                agent_lines.append(f"- {agent_key}{suffix}")
            response_messages.append("\n".join(agent_lines))
        elif command == "/agent":
            if arg in state["agents"]:
                self.switch_active_agent(arg)
                response_messages.append(f"Switched to agent '{arg}'. *clank*")
            else:
                response_messages.append(f"Error: Agent '{arg}' not found.")
        elif command == "/summarize":
            # Logic for summarization would go here, for now a placeholder
            response_messages.append(
                "Session summarization initiated... *whir* (Feature pending implementation in core)"
            )
        elif command == "/models":
            models = self.config.get("models", {})
            active_agent_key = state.get("active_agent_key")
            active_agent = state["agents"].get(active_agent_key)
            active_model_key = getattr(active_agent, "active_model_key", None)
            
            if models:
                model_lines = ["Available Models: *beep*"]
                for model_key, model_config in models.items():
                    suffix = " [ACTIVE]" if model_key == active_model_key else ""
                    model_lines.append(f"- {model_key}{suffix}")
                response_messages.append("\n".join(model_lines))
            else:
                response_messages.append("No models configured.")
        elif command == "/model":
            active_agent_key = state.get("active_agent_key")
            active_agent = state["agents"].get(active_agent_key)
            if active_agent and hasattr(active_agent, "set_model"):
                if active_agent.set_model(arg):
                    response_messages.append(f"Switched active agent '{active_agent_key}' to model '{arg}'. *beep*")
                else:
                    response_messages.append(f"Error: Model '{arg}' not found in configuration.")
            else:
                response_messages.append("Error: Active agent does not support switching models.")
        elif command == "/help":
            response_messages.append(
                "Available Commands: /debug, /agents, /agent <key>, /models, /model <key>, /summarize, /help, /exit"
            )
        else:
            response_messages.append(f"Error: Unknown command '{command}'.")

        return "\n".join(response_messages)
