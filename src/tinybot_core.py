import json
import importlib
import os

from utils import (
    load_config,
    setup_logger,
    log_message,
    log_debug,
    discover_agents,
    discover_skills,
)
from llm import call_llm
from session_manager import SessionManager


class TinyBotCore:
    def __init__(self, config=None, is_web_interface=False):
        self.config = config if config is not None else load_config()
        self.global_llm_caller_func = call_llm
        self.is_web_interface = is_web_interface
        self.session_manager = SessionManager()

        # Initialize base state
        initial_state = {
            "debug": self.config.get("debug", False),
            "log_file": setup_logger(self.config, is_web_interface=is_web_interface),
            "active_agent_key": self.config.get("default_agent", "GeneralChatAgent"),
            "available_skills": discover_skills(),
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

                agent_skills = discover_skills(key)
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
        """Check all registered agents for messages in their inbox."""
        state = self.session_manager.get_state()
        tinybot_root = os.environ.get("TINYBOT_ROOT", "/Users/peggy/.tinybot")
        
        for agent_key, agent in state.get("agents", {}).items():
            inbox_path = os.path.join(tinybot_root, "agents", agent_key.lower().replace("agent", ""), "inbox")
            if os.path.exists(inbox_path) and os.listdir(inbox_path):
                log_debug(f"Mail found for agent {agent_key}. Spawning handler...")
                # Logic to trigger agent to process inbox
                # This could be calling a method on the agent or spawning a subprocess
                # For now, we simulate with a log and a dummy action
                agent.handle_prompt(f"SYSTEM: You have new messages in your inbox at {inbox_path}. Please process them.", state)

    def process(self, user_input):
        """Main entry point for processing messages."""
        self.check_agent_inboxes() # Check inboxes before every turn
        return self.process_user_input(user_input)

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
                    tinybot_root = os.environ.get("TINYBOT_ROOT", ".")
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
