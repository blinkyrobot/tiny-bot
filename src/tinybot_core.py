import json
import importlib
import os

from utils import load_config, setup_logger, log_message, discover_agents, discover_skills
from llm import call_llm, get_gemini_usage

class TinyBotCore:
    def __init__(self, config=None, is_web_interface=False):
        self.config = config if config is not None else load_config()
        self.global_llm_caller_func = call_llm 
        self.is_web_interface = is_web_interface # Flag to adjust behavior if needed

        self.session_state = {
            "debug": self.config.get("debug", False),
            "log_file": setup_logger(self.config, is_web_interface=is_web_interface),
            "active_agent_key": self.config.get("default_agent", "GeneralChatAgent"),
            "agents": {},
            "subagents": {},
            "document_context": None,
            "available_skills": discover_skills()
        }
        self._load_agents()
        self._ensure_default_agent_active()

    def _load_agents(self):
        agent_defs = discover_agents()
        for agent_def in agent_defs:
            key = agent_def["key"]
            class_path = agent_def["class_path"]
            
            try:
                if ":" in class_path:
                    module_path, class_name = class_path.split(":")
                    module_name = module_path.replace("src/", "").replace(".py", "")
                    module = importlib.import_module(module_name)
                    agent_class = getattr(module, class_name)
                    
                    agent_skills = discover_skills(key)
                    self.session_state["agents"][key] = agent_class(self.config, agent_def, self.global_llm_caller_func, self.session_state["log_file"], available_skills=agent_skills)
                    if self.session_state["debug"]: print(f"DEBUG: Loaded agent '{key}' from {class_path}")
                else:
                    print(f"Warning: Invalid class path for agent '{key}': {class_path}")
            except Exception as e:
                print(f"Error loading agent '{key}': {e}")

    def _ensure_default_agent_active(self):
        if self.session_state["active_agent_key"] not in self.session_state["agents"]:
            print(f"Warning: Default agent '{self.session_state['active_agent_key']}' not found. Falling back to first available agent.")
            if self.session_state["agents"]:
                self.session_state["active_agent_key"] = list(self.session_state["agents"].keys())[0]
            else:
                print("Error: No agents loaded.")
                # Depending on the application, you might want to raise an exception here.

    def switch_active_agent(self, new_agent_key, new_prompt=None):
        """Switches the active agent and sets its model to its default."""
        if new_agent_key not in self.session_state["agents"]:
            print(f"Error: Agent '{new_agent_key}' not found. *boop*")
            return

        self.session_state["active_agent_key"] = new_agent_key
        new_agent = self.session_state["agents"][new_agent_key]
        
        default_model_key = getattr(new_agent, 'default_model_key', None)
        if default_model_key in self.config:
            resolved_model_key = self.config[default_model_key]
        elif not default_model_key:
            resolved_model_key = self.config.get("chat_model")
        else:
            resolved_model_key = default_model_key

        if resolved_model_key and resolved_model_key in self.config.get("models", {}):
            new_agent.model_config = self.config["models"][resolved_model_key]
            print(f"*clank* Switching to {new_agent_key} agent (model: {resolved_model_key}). *beep*")
        else:
            print(f"*clank* Switching to {new_agent_key} agent. (Model not changed as default '{resolved_model_key}' was not found). *beep*")

        if new_prompt:
            final_transition_signal = new_agent.handle_prompt(new_prompt, self.session_state)
            if final_transition_signal and final_transition_signal in self.session_state["agents"]:
                self.switch_active_agent(final_transition_signal)

    def handle_orchestrator_command(self, user_input):
        command_parts = user_input.strip().lower().split(' ', 1)
        command = command_parts[0]
        arg = command_parts[1] if len(command_parts) > 1 else ""
        response_messages = []

        if command == '/debug':
            active_agent_key = self.session_state.get("active_agent_key")
            active_agent = self.session_state["agents"].get(active_agent_key)
            if active_agent:
                response_messages.append(f"""--- AGENT PROMPT CONTEXT (HISTORY) ---
{json.dumps(active_agent.history, indent=2)}
--------------------------------------""")
            else:
                response_messages.append("Error: Could not find active agent to debug.")
        elif command == '/agents':
            active_agent_key = self.session_state.get("active_agent_key")
            agent_lines = ["Available Agents: *clank*"]
            for agent_key in self.session_state["agents"]:
                suffix = " [ACTIVE]" if agent_key == active_agent_key else ""
                agent_lines.append(f"- {agent_key}{suffix}")
            response_messages.append("\n".join(agent_lines))
        elif command == '/models':
            models = self.config.get("models", {})
            active_agent = self.session_state["agents"].get(self.session_state.get("active_agent_key"))
            active_model_name = None
            if active_agent and active_agent.model_config:
                for m_key, m_config in models.items():
                    if m_config == active_agent.model_config:
                        active_model_name = m_key
                        break

            model_lines = ["Available Models: *clank*"]
            for m_key in models:
                suffix = " [ACTIVE]" if m_key == active_model_name else ""
                model_lines.append(f"- {m_key}{suffix}")
            response_messages.append("\n".join(model_lines))
        elif command == '/model':
            if not arg:
                response_messages.append("Error: Please specify a model name. Use /models to list available models. *boop*")
            else:
                models = self.config.get("models", {})
                if arg in models:
                    active_agent_key = self.session_state.get("active_agent_key")
                    active_agent = self.session_state["agents"].get(active_agent_key)
                    if active_agent:
                        active_agent.model_config = models[arg]
                        response_messages.append(f"Switched active agent ({active_agent_key}) to model: {arg}. *clank*")
                    else:
                        response_messages.append("Error: No active agent found to switch model. *boop*")
                else:
                    response_messages.append(f"Error: Model '{arg}' not found. Use /models to list available models. *boop*")
        elif command == '/agent':
            if arg in self.session_state["agents"]:
                self.switch_active_agent(arg)
                response_messages.append(f"Switched active agent to: {arg}")
            else:
                response_messages.append(f"Error: Agent '{arg}' not found. Available: {list(self.session_state['agents'].keys())} *boop*")
        elif command == '/clear_context':
            self.session_state["document_context"] = None
            response_messages.append("INFO: Document context has been cleared. Returning to normal conversation mode. *beep*")
        elif command == '/help':
            response_messages.append("Available Commands: *clank*")
            response_messages.append("/exit - Exit the application (CLI only).")
            response_messages.append("/debug - Print the current agent's prompt context.")
            response_messages.append("/agents - List all available agents.")
            response_messages.append("/models - List all available models.")
            response_messages.append("/model <name> - Switch the current agent to a specific model.")
            response_messages.append(f"/agent <name> - Manually switch active agent.")
            response_messages.append("/clear_context - Clear the loaded document from the agent's working memory.")
            response_messages.append("/help - Display this help message. *beep*")
        else:
            response_messages.append(f"Error: Unknown orchestrator command '{command}'. Type /help for commands. *boop*")
        
        return "\n".join(response_messages)

    def _perform_exit_sequence(self):
        print("INFO: Initiating session summary before exit. *clank*")
        
        active_agent = self.session_state["agents"].get(self.session_state["active_agent_key"])
        usage_report = get_gemini_usage()

        if active_agent:
            session_transcript_file = self.session_state.get("log_file")
            if session_transcript_file and active_agent.memory_path:
                exit_prompt = f"TINYBOT_EXIT_SEQUENCE: Please execute the 'summarize_session' skill. The session_transcript_path is '{session_transcript_file}'. The destination_memory_path is '{active_agent.memory_path}'. After the skill is complete, I will exit."
                
                active_agent.handle_prompt(exit_prompt, self.session_state)
                
                print(usage_report)
                print("INFO: Session summary skill finished. Exiting... *clank*")
                return "Exit sequence completed."
            else:
                print(usage_report)
                print("WARNING: Log file or active agent's memory path not found, cannot summarize session. Exiting anyway. *clank*")
                return "Exit sequence skipped (no log/memory path)."
        else:
            print(usage_report)
            print("WARNING: No active agent found, cannot summarize session. Exiting anyway. *clank*")
            return "Exit sequence skipped (no active agent)."

    def process_user_input(self, user_input):
        if user_input.strip().lower() == '/exit':
            return "TINYBOT_EXIT_SIGNAL"
        elif user_input.strip().startswith('/'):
            return self.handle_orchestrator_command(user_input)
        else:
            active_agent_key = self.session_state["active_agent_key"]
            active_agent = self.session_state["agents"].get(active_agent_key)

            if not active_agent:
                if not self.session_state["agents"]:
                    return "Error: No agents loaded."
                
                fallback_key = list(self.session_state["agents"].keys())[0]
                print(f"Error: Active agent '{active_agent_key}' not found. Falling back to {fallback_key}. *clank*")
                active_agent_key = fallback_key
                active_agent = self.session_state["agents"][active_agent_key]
                self.session_state["active_agent_key"] = active_agent_key

            transition_signal = active_agent.handle_prompt(user_input, self.session_state)
            response_content = active_agent.last_response if hasattr(active_agent, 'last_response') else "No direct response from agent."

            if transition_signal:
                new_prompt = None
                if ":" in transition_signal:
                    parts = transition_signal.split(':', 1)
                    target_agent_key = parts[0]
                    new_prompt = parts[1]
                else:
                    target_agent_key = transition_signal
                
                if target_agent_key in self.session_state["agents"]:
                    self.switch_active_agent(target_agent_key, new_prompt)
                    new_active_agent = self.session_state["agents"][self.session_state["active_agent_key"]]
                    response_content += f"\n*clank* Switched to {self.session_state['active_agent_key']} agent. *beep*"
                    if new_active_agent.last_response:
                        response_content += f"\n{new_active_agent.last_response}"
                else:
                    response_content += f"\nWarning: Agent returned unknown transition signal: '{transition_signal}' *boop*"
            
            return response_content
