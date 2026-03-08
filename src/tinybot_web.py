from flask import Flask, request, jsonify, render_template
import os
import markdown
import signal

from tinybot_core import TinyBotCore

BOT_AVATAR_URL = "/static/avatars/blinky.png"

current_dir = os.path.dirname(os.path.abspath(__file__))
static_folder_path = os.path.join(current_dir, 'static')
template_folder_path = os.path.join(current_dir, 'templates')

app = Flask(__name__, static_folder=static_folder_path, template_folder=template_folder_path)

# Global instance of TinyBotCore
tinybot_core_instance = None

@app.before_request
def initialize_app():
    global tinybot_core_instance
    if tinybot_core_instance is None:
        tinybot_core_instance = TinyBotCore(is_web_interface=True)
        # We can now access the session_state managed by TinyBotCore
        # For web interface, we don't need to expose all of it globally,
        # but rather interact via tinybot_core_instance methods.

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def get_status():
    if tinybot_core_instance:
        active_agent_key = tinybot_core_instance.session_state["active_agent_key"]
        return jsonify({"active_agent": active_agent_key})
    return jsonify({"active_agent": "N/A", "error": "TinyBotCore not initialized"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"response": "No message provided."}), 400

    if tinybot_core_instance is None:
        return jsonify({"response": "Error: TinyBotCore not initialized."}), 500

    response_content = tinybot_core_instance.process_user_input(user_input)

    if response_content == "TINYBOT_EXIT_SIGNAL":
        print("INFO: TINYBOT_EXIT_SIGNAL received in /chat. *clank*")
        exit_message = tinybot_core_instance._perform_exit_sequence()
        # Trigger shutdown in a separate thread so we can still return the response
        import threading
        def kill_server():
            import time
            import signal
            time.sleep(2) # Delay to allow response transmission
            print(f"INFO: Executing process group shutdown (PGID: {os.getpgrp()})... *beep*")
            try:
                os.killpg(os.getpgrp(), signal.SIGTERM)
            except Exception as e:
                print(f"WARNING: killpg failed: {e}. Falling back to os._exit(0)")
                os._exit(0)

        threading.Thread(target=kill_server).start()
        return jsonify({"response": f"EXIT: {exit_message}", "active_agent": tinybot_core_instance.session_state["active_agent_key"], "avatar_url": BOT_AVATAR_URL})
    active_agent_key = tinybot_core_instance.session_state["active_agent_key"]
    
    return jsonify({
        "response": markdown.markdown(response_content), 
        "active_agent": active_agent_key, 
        "avatar_url": BOT_AVATAR_URL
    })

@app.route('/shutdown', methods=['POST'])
def shutdown():
    print("INFO: Shutdown request received via /shutdown. *clank*")
    if tinybot_core_instance:
        tinybot_core_instance._perform_exit_sequence()
    
    import threading
    def kill_server():
        import time
        import signal
        time.sleep(2)
        print(f"INFO: Executing process group shutdown (PGID: {os.getpgrp()})... *beep*")
        try:
            os.killpg(os.getpgrp(), signal.SIGTERM)
        except Exception as e:
            print(f"WARNING: killpg failed: {e}. Falling back to os._exit(0)")
            os._exit(0)
    
    threading.Thread(target=kill_server).start()
    return jsonify({"response": "Shutting down... *clank*"})

@app.route('/history', methods=['GET'])
def get_history():
    if tinybot_core_instance:
        active_agent_key = tinybot_core_instance.session_state.get("active_agent_key")
        active_agent = tinybot_core_instance.session_state["agents"].get(active_agent_key)
        history = active_agent.history if active_agent and hasattr(active_agent, 'history') else []
        return jsonify({"history": history})
    return jsonify({"history": [], "error": "TinyBotCore not initialized"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
