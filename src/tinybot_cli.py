import asyncio
import sys
import readline
# Import our new client utils
from client_utils import HeadlessClient

# Basic command completion
COMMANDS = ["/quit", "/health", "/help"]

def completer(text, state):
    options = [c for c in COMMANDS if c.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None

async def main():
    # Setup readline completion
    readline.set_completer(completer)
    if 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    # Initialize the client that points to our headless server
    client = HeadlessClient(base_url="http://127.0.0.1:8000")

    print("tinybot engine headless CLI client starting... *beep*")
    
    # Check health on startup
    health = await client.check_health()
    if health.get("status") == "online":
        print(f"Engine is ONLINE. Agent: {health.get('agent', 'Unknown')} *whir*")
    else:
        print(f"Engine is OFFLINE: {health.get('error', 'Unknown Error')} *sad beep*")
        print("Please ensure the engine server is running (e.g., bin/tinybot-web).")
        # Continue anyway for debugging if they really want, or exit? Let's just warn.

    print("Commands routed to engine server. Type /quit to exit. *clank*")

    # Use a loop to send requests
    while True:
        try:
            # We use loop.run_in_executor to handle blocking input() in an async loop
            loop = asyncio.get_event_loop()
            user_input = await loop.run_in_executor(None, input, "> ")
            
            if not user_input: continue
            
            trimmed = user_input.strip()
            if trimmed == "/quit":
                print("Exiting... *clank*")
                break
            
            if trimmed == "/health":
                health = await client.check_health()
                print(f"Health: {health}")
                continue

            if trimmed == "/help":
                print(f"Available commands: {', '.join(COMMANDS)}")
                continue

            # Send to engine server
            response = await client.send_message(user_input)
            
            if "[SIGNAL:EXIT]" in response:
                # Print the response without the signal tag
                clean_response = response.replace("[SIGNAL:EXIT]", "").strip()
                if clean_response:
                    print(f"{clean_response}")
                print("\nExiting... *clank*")
                break
                
            print(f"{response}")

        except (KeyboardInterrupt, EOFError): 
            print("\nExiting... *clank*")
            break
        except Exception as e: 
            print(f"\nAn unexpected error occurred: {e} *boop*")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
