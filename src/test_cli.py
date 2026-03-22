import sys
import os

# 1. Ensure sandbox path is prioritized for testing
sys.path.insert(0, os.path.abspath("./sandbox/src"))

from tinybot_core import TinyBotCore

def run_test_cli():
    print("--- TinyBot Sandbox CLI (Headless Mode) ---")
    print("Initializing Core...")
    
    # TinyBotCore will automatically look for config.json 
    # based on $TINYBOT_ROOT environment variable.
    try:
        core = TinyBotCore(is_web_interface=False)
        print("Core initialized.")
    except Exception as e:
        print(f"Failed to initialize core: {e}")
        return

    while True:
        try:
            user_input = input("tinybot-test> ")
            if user_input.strip().lower() == '/exit':
                print("Exiting test CLI.")
                break
            
            # Direct interaction with TinyBotCore's processing logic
            response = core.process_user_input(user_input)
            print(f"Blinky: {response}")
            
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_test_cli()
