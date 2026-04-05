import json
import re
import os
from datetime import datetime
from utils import log_message
from llm import call_llm
from tools import get_tools_definition, get_dispatcher  # Ensure these are imported


class BaseAgent:
    def __init__(
        self,
        config,
        agent_def,
        global_llm_caller_func,
        log_file,
        available_skills="",
        required_tools=None,
    ):
        self.config = config
        self.agent_name = agent_def.get("name", agent_def["key"])
        self.key = agent_def["key"]  # Ensure agent has a key attribute
        self.global_llm_caller = global_llm_caller_func
        self.log_file = log_file
        self.debug_mode = config.get("debug", False)
        self.available_skills = available_skills

        # Agent's directory and memory path
        self.agent_dir = os.path.join(
            os.environ.get("TINYBOT_ROOT", "."), "agents", agent_def["key"]
        )
        self.memory_path = os.path.join(self.agent_dir, "memory.md")
        self.agent_memory = self._load_agent_memory()

        # Load Architecture Philosophy
        self.architecture_philosophy = ""
        arch_path = os.path.join(os.environ.get("TINYBOT_ROOT", "."), "architecture.md")
        if os.path.exists(arch_path):
            with open(arch_path, "r") as f:
                self.architecture_philosophy = f.read()

        # Initialize tools based on required_tools
        self.tools_definition = get_tools_definition(required_tools)

        # ADDED: Load local agent skills if they exist
        local_skills_dir = os.path.join(self.agent_dir, "skills")
        if os.path.exists(local_skills_dir):
            import glob

            local_skills = glob.glob(os.path.join(local_skills_dir, "*.md"))
            # Optionally merge/extend the available_skills string
            # This assumes available_skills is a formatted string.
            # In a real fix, we might need a more robust registration system.
            for skill_path in local_skills:
                skill_name = os.path.basename(skill_path).replace(".md", "")
                self.available_skills += f"\n- {skill_name}: (Local Agent Skill)"

        self.dispatcher = get_dispatcher(self, required_tools)

        self.history = []
        self.agent_system_prompt = agent_def["identity"]
        self.model_config = None
        self.supports_tools = True

        self.last_response = ""

    def _load_agent_memory(self):
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r") as f:
                from collections import deque

                lines = deque(f, maxlen=100)
                content = "".join(lines)
                if len(content) > 10000:
                    content = "... [truncated] ...\n" + content[-10000:]
                return content
        return ""

    def _get_token_count(self, messages_for_llm):
        """Calculates token count based on character count approximation (4 chars per token)."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages_for_llm)
        return total_chars // 4

    def _check_memory_usage(self, messages_for_llm):
        """Monitors prompt size and triggers summary/pruning if threshold is reached."""
        if self._get_token_count(messages_for_llm) > 15000:
            if self.debug_mode:
                print("DEBUG: Memory threshold reached, triggering cleanup.")
            # Implementation for summary/pruning to follow
            pass

    def _prepare_system_message(self):
        skills_text = ""
        if self.available_skills:
            skills_text = f"""### AVAILABLE SKILLS & TOOLS ###
You have access to a set of skills and external MCP tools. 

1. **Standard Skills** (Markdown or Python): 
   To use these, you MUST use the `execute_skill` tool with the appropriate `skill_name` and `parameters`.
   
2. **MCP Servers** (Indicated by '(MCP Server)'):
   These are external service providers that offer tools.
   - To see the tools available on a specific server, use `mcp_list_server_tools` with the `server_name` (e.g., 'manifold').
   - To see the parameters and schema for a specific namespaced tool, use `mcp_get_tool_info` with the namespaced name (e.g., 'manifold:place_bet').
   - To execute an MCP tool, use `mcp_call` with the namespaced name and arguments.

IMPORTANT: Do NOT output the tool call as text in your response. Instead, trigger the appropriate tool function using your tool-calling capability.

Here is the manifest of resources available to you:
{self.available_skills}
"""

        # Inject the dynamic memory path into the identity prompt if the placeholder exists
        identity_prompt = self.agent_system_prompt.replace(
            "{{memory_path}}", self.memory_path
        )

        full_prompt = f"You are {self.agent_name}. {identity_prompt}\n{skills_text}\n"
        return {"role": "system", "content": full_prompt}

    def log_trace(self, message):
        """Logs a high-level trace message to the session transcript for visibility."""
        if self.debug_mode:
            print(f"TRACE [{self.agent_name}]: {message}")
        log_message(self.log_file, "trace", message, self.agent_name)

    def think(self, context, task_description, system_prompt_override=None):
        """
        A highly focused version of ask() designed for 'Intelligence Nodes'.
        Takes a raw data context and a specific reasoning task.
        """
        if system_prompt_override:
            system_prompt = system_prompt_override
        else:
            system_prompt = (
                f"You are {self.agent_name}, a specialized reasoning node.\n"
                f"Your identity: {self.agent_system_prompt}\n"
                "Focus ONLY on the provided context. Do NOT use outside knowledge unless specified."
            )

        prompt = f"### CONTEXT DATA ###\n{context}\n\n### TASK ###\n{task_description}"
        
        self.log_trace(f"Thinking about task: {task_description[:80]}...")
        result = self.ask(prompt, system_prompt=system_prompt)
        self.log_trace(f"Reasoning complete ({len(result)} chars).")
        return result

    def ask(self, prompt, system_prompt=None):
        """
        A stateless, lightweight LLM call that bypasses the history and tool-calling loop.
        Useful for targeted 'Intelligence' tasks (summarization, decisions, etc.) within Python logic.
        """
        if system_prompt is None:
            system_prompt = self._prepare_system_message()["content"]

        # Log the start of the 'ask' operation
        prompt_summary = (prompt[:100] + "...") if len(prompt) > 100 else prompt
        self.log_trace(f"Requesting intelligence node: {prompt_summary}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        if self.debug_mode:
            print(f"DEBUG: Agent '{self.agent_name}' calling stateless ask().")

        response = self.global_llm_caller(
            self.model_config,
            messages,
            tools=None,
            supports_tools=False,
            debug=self.debug_mode,
            log_file=self.log_file,
        )

        content = response.get("content", "")
        # Strip thinking blocks if present and configured
        if self.config.get("show_thinking") is False:
            content = re.sub(
                r"<think>.*?(?:</think>|$)", "", content, flags=re.DOTALL
            ).strip()

        # Log the completion of the 'ask' operation
        self.log_trace(f"Intelligence node response received ({len(content)} chars).")

        return content

    def _call_llm_and_process_tools(self, messages_for_llm, max_iterations=10):
        if self.debug_mode:
            print(
                f"DEBUG: Entering _call_llm_and_process_tools loop (Max iterations: {max_iterations})."
            )
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            if not self.model_config:
                if self.debug_mode:
                    print(
                        "DEBUG: Agent's model configuration is not set. Exiting loop."
                    )
                return "Error: Agent's model configuration is not set."

            if self.debug_mode:
                print(
                    f"DEBUG: Iteration {iterations}/{max_iterations}. Messages sent to LLM ({len(messages_for_llm)} messages):"
                )

            response_message = self.global_llm_caller(
                self.model_config,
                messages_for_llm,
                self.tools_definition,
                self.supports_tools,
                debug=self.debug_mode,
                log_file=self.log_file,
            )

            # Preserve the raw response in history and logs to maintain API contracts (e.g. thought_signature)
            self.history.append(response_message)
            messages_for_llm.append(response_message)
            log_message(self.log_file, "assistant", response_message, self.agent_name)

            # Produce a clean version of content for display/return if show_thinking is False
            clean_content = response_message.get("content", "")
            if self.config.get("show_thinking") is False:
                if clean_content:
                    clean_content = re.sub(
                        r"<think>.*?(?:</think>|$)", "", clean_content, flags=re.DOTALL
                    ).strip()

            if not response_message.get("tool_calls"):
                if self.debug_mode:
                    print("DEBUG: LLM returned conversational response. Exiting loop.")
                llm_content = clean_content if clean_content else "No response content."
                self.last_response = llm_content
                return llm_content

            # Process ALL tool calls in the response
            tool_calls = response_message.get("tool_calls", [])
            for call in tool_calls:
                function_call = call.get("function", {})
                raw_tool_name = function_call.get("name")
                # Handle namespacing (e.g. 'default_api:exec') for local dispatcher lookup
                tool_name = (
                    raw_tool_name.split(":")[-1]
                    if ":" in raw_tool_name
                    else raw_tool_name
                )
                args_str = function_call.get("arguments", "{}")

                print(f"Calling tool: {raw_tool_name}({args_str})...")

                try:
                    args = json.loads(args_str)
                    if tool_name in self.dispatcher:
                        output = self.dispatcher[tool_name](**args)

                        if isinstance(output, str) and len(output) > 15000:
                            output = output[:15000] + "\n... [truncated]"

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": raw_tool_name,
                            "content": output,
                        }
                        messages_for_llm.append(tool_msg)
                        self.history.append(tool_msg)  # Important: Keep history in sync
                        log_message(self.log_file, "tool", tool_msg, self.agent_name)
                    else:
                        error_content = f"Error: Unknown tool '{raw_tool_name}' (normalized to '{tool_name}')"
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": raw_tool_name,
                            "content": error_content,
                        }
                        messages_for_llm.append(tool_msg)
                        self.history.append(tool_msg)
                        log_message(self.log_file, "tool", tool_msg)
                except Exception as e:
                    error_content = f"Error: Invalid arguments or execution failure for tool '{raw_tool_name}'. Exception: {e}"
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": raw_tool_name,
                        "content": error_content,
                    }
                    messages_for_llm.append(tool_msg)
                    self.history.append(tool_msg)
                    log_message(self.log_file, "tool", tool_msg, self.agent_name)

            if self.debug_mode:
                print(
                    f"DEBUG: Finished processing {len(tool_calls)} tool calls. Continuing loop."
                )

        if iterations >= max_iterations:
            error_msg = f"Error: Maximum tool-call iterations ({max_iterations}) reached. The agent might be in a loop. *boop*"
            print(error_msg)
            return error_msg

    def handle_prompt(self, user_input, session_state):
        raise NotImplementedError(
            "handle_prompt method must be implemented by derived classes."
        )


class GenericAgent(BaseAgent):
    def __init__(
        self, config, agent_def, global_llm_caller_func, log_file, available_skills=""
    ):
        required_tools = agent_def.get("tools")
        if not required_tools:
            required_tools = [
                "mcp_call",
                "mcp_get_tool_info",
                "mcp_list_server_tools",
                "read",
                "write",
                "apply_edit_block",
                "execute_skill",
            ]
        super().__init__(
            config,
            agent_def,
            global_llm_caller_func,
            log_file,
            available_skills=available_skills,
            required_tools=required_tools,
        )

        self.default_model_key = agent_def.get("default_model")
        model_key = self.default_model_key

        # Resolve aliases like 'chat_model' or 'coding_model'
        if model_key in config:
            model_key = config[model_key]
        elif not model_key:
            model_key = config.get("chat_model")

        self.active_model_key = model_key
        self.model_config = config.get("models", {}).get(model_key)

        # API keys are sourced *only* from the secrets dictionary in the config.
        if self.model_config:
            self.model_config.pop("api_key", None)

            api_type = self.model_config.get("type")
            secrets = self.config.get("secrets", {})
            api_key = None
            key_name = None

            if api_type == "openai_compatible":
                key_name = secrets.get("OPENAI_API_KEY_NAME", "OPENAI_API_KEY")
                api_key = secrets.get(key_name)
            elif api_type == "google_gemini":
                key_name = secrets.get(
                    "GOOGLE_GEMINI_API_KEY_NAME", "GOOGLE_GEMINI_API_KEY"
                )
                api_key = secrets.get(key_name) or secrets.get("GEMINI_API_KEY")

            if api_key:
                self.model_config["api_key"] = api_key
            elif key_name:
                print(
                    f"Warning: API key '{key_name}' not found in secrets for model type '{api_type}'. API calls may fail."
                )
            else:
                print(
                    f"Warning: Could not determine API key name for model type '{api_type}'. API calls may fail."
                )

        self.supports_tools = True
        self.transitions = agent_def.get("transitions", {})
        self.history.append(self._prepare_system_message())

    def set_model(self, model_key):
        """Switches the active model for this agent."""
        if model_key in self.config.get("models", {}):
            new_model_config = self.config["models"][model_key].copy()
            # Handle secrets as in __init__
            api_type = new_model_config.get("type")
            secrets = self.config.get("secrets", {})
            api_key = None

            if api_type == "openai_compatible":
                api_key = secrets.get(
                    secrets.get("OPENAI_API_KEY_NAME", "OPENAI_API_KEY")
                )
            elif api_type == "google_gemini":
                api_key = secrets.get(
                    secrets.get("GOOGLE_GEMINI_API_KEY_NAME", "GOOGLE_GEMINI_API_KEY")
                ) or secrets.get("GEMINI_API_KEY")

            if api_key:
                new_model_config["api_key"] = api_key

            self.active_model_key = model_key
            self.model_config = new_model_config
            return True
        return False

    def handle_prompt(self, user_input, session_state):
        messages_for_llm = list(self.history)

        # Handle Document Q&A Mode (if context exists)
        if session_state.get("document_context"):
            print(
                "INFO: Document context is loaded. Answering in Q&A mode. (use /clear_context to exit)"
            )
            qa_system_prompt = f"""{self.agent_system_prompt}

### DOCUMENT Q&A MODE ###
You are currently in a question-answering mode focused on a specific document. 
The user is asking questions about the document provided below. 
Your answers MUST be based *only* on the text of this document. 
Do not use your general knowledge. If the answer is not in the document, say so explicitly.

--- DOCUMENT START ---
{session_state["document_context"]}
--- DOCUMENT END ---"""
            if messages_for_llm and messages_for_llm[0]["role"] == "system":
                messages_for_llm[0] = {"role": "system", "content": qa_system_prompt}
            else:
                messages_for_llm.insert(
                    0, {"role": "system", "content": qa_system_prompt}
                )

        # Append /no_think if show_thinking is False
        llm_user_input = user_input
        if self.config.get("show_thinking") is False:
            llm_user_input += " /no_think"

        messages_for_llm.append({"role": "user", "content": llm_user_input})
        self.history.append({"role": "user", "content": llm_user_input})
        log_message(
            self.log_file, "user", user_input, self.agent_name
        )  # Log original input

        llm_response_content = self._call_llm_and_process_tools(messages_for_llm)
        self.last_response = llm_response_content

        # Also check for specific command triggers
        if (
            "/done-coding" in user_input.lower()
            and "general_chat" in session_state["agents"]
        ):
            return "general_chat"

        return None


class SubAgent(BaseAgent):
    """
    A specialized agent for handling delegated, self-contained tasks.
    """

    def __init__(
        self,
        config,
        agent_def,
        global_llm_caller_func,
        log_file,
        task_description,
        available_skills="",
        required_tools=None,
        parent_model_config=None,
    ):
        super().__init__(
            config,
            agent_def,
            global_llm_caller_func,
            log_file,
            available_skills=available_skills,
            required_tools=required_tools,
        )

        if parent_model_config:
            self.model_config = parent_model_config
        else:
            # Sub-agents typically use a versatile model, let's default to the chat model
            chat_model_key = config.get("chat_model")
            self.model_config = config.get("models", {}).get(chat_model_key)

        # API keys are sourced *only* from the secrets dictionary in the config.
        if self.model_config:
            self.model_config.pop("api_key", None)

            api_type = self.model_config.get("type")
            secrets = self.config.get("secrets", {})
            api_key = None
            key_name = None

            if api_type == "openai_compatible":
                key_name = secrets.get("OPENAI_API_KEY_NAME", "OPENAI_API_KEY")
                api_key = secrets.get(key_name)
            elif api_type == "google_gemini":
                key_name = secrets.get(
                    "GOOGLE_GEMINI_API_KEY_NAME", "GOOGLE_GEMINI_API_KEY"
                )
                api_key = secrets.get(key_name) or secrets.get("GEMINI_API_KEY")

            if api_key:
                self.model_config["api_key"] = api_key
            elif key_name:
                print(
                    f"Warning: API key '{key_name}' not found in secrets for model type '{api_type}'. API calls may fail."
                )
            else:
                print(
                    f"Warning: Could not determine API key name for model type '{api_type}'. API calls may fail."
                )

        self.supports_tools = True

        self.task_description = task_description
        self.agent_system_prompt = (
            agent_def["identity"] + f"\nYour assigned task is: {self.task_description}"
        )
        self.agent_name = agent_def.get("name", agent_def["key"])
        self.history.append(self._prepare_system_message())
        self.result = None

    def handle_prompt(self, user_input, session_state):
        """Standard prompt handler."""
        if self.debug_mode:
            print(f"DEBUG: SubAgent.handle_prompt called with input: {user_input[:200]}...")

        """
        For a sub-agent, the 'user_input' is the initial instruction to kick off its task.
        """
        llm_user_input = user_input
        if self.config.get("show_thinking") is False:
            llm_user_input += " /no_think"

        self.history.append({"role": "user", "content": llm_user_input})
        log_message(
            self.log_file, "user", f"SubAgent Task Start: {user_input}", self.agent_name
        )

        llm_response_content = self._call_llm_and_process_tools(list(self.history))
        self.result = llm_response_content

        print(
            f"SubAgent ({self.agent_name}): Task execution finished. Result: {self.result}"
        )

        # Sub-agents are single-shot, they don't transition, they return their result.
        return self.result
