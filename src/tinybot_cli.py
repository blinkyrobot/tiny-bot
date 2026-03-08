import json
import importlib

from tinybot_core import TinyBotCore

# Original imports
from utils import load_config, setup_logger, log_message, discover_agents
from llm import call_llm

def main():
    # Instantiate TinyBotCore
    tinybot_core = TinyBotCore()
    session_state = tinybot_core.session_state # Access session_state from the core

    print("tinybot engine started. *beep*")
    print(f"Current active agent: {session_state['active_agent_key']}. Type /help for commands. *clank*")

    while True:
        try:
            user_input = input(f"> ")
            if not user_input: continue

            # Delegate user input processing to TinyBotCore
            response = tinybot_core.process_user_input(user_input)

            if response == "TINYBOT_EXIT_SIGNAL":
                tinybot_core._perform_exit_sequence()
                break
            else:
                print(response)

        except KeyboardInterrupt: print("\nExiting... *clank*"); break
        except Exception as e: print(f"\nAn unexpected error occurred: {e} *boop*"); break


if __name__ == "__main__":
    main()
