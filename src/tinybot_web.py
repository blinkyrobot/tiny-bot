from flask import Flask, request, jsonify, render_template
import os
import markdown
import asyncio
from client_utils import HeadlessClient

BOT_AVATAR_URL = "/static/avatars/blinky.png"

# Initialize Client
client = HeadlessClient(base_url="http://127.0.0.1:8000")

app = Flask(__name__, 
            static_folder='static', 
            template_folder='templates')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def get_status():
    status = asyncio.run(client.check_health())
    return jsonify({"active_agent": "N/A", "engine_status": status.get("status")})

@app.route('/history', methods=['GET'])
def get_history():
    history_data = asyncio.run(client.get_history())
    raw_history = history_data.get("history", "")
    
    # Parse the markdown history into a list of messages
    # Format is **USER**: ... or **[Agent] ASSISTANT**: ...
    import re
    messages = []
    
    # Regex to find **ROLE**: CONTENT
    # Using DOTALL to capture multi-line content between headers
    parts = re.split(r'\*\*(?:\[.*?\] )?(USER|ASSISTANT)\*\*:', raw_history)
    
    # parts[0] is everything before the first match
    for i in range(1, len(parts), 2):
        role = parts[i].lower()
        content = parts[i+1].strip() if i+1 < len(parts) else ""
        if role == 'assistant': role = 'bot'
        messages.append({"role": role, "content": markdown.markdown(content)})
    
    return jsonify({"history": messages})

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"response": "No message provided."}), 400

    # Communicate with Headless Engine
    response_content = asyncio.run(client.send_message(user_input))
    
    return jsonify({
        "response": markdown.markdown(response_content), 
        "active_agent": "N/A (Managed by Engine)", 
        "avatar_url": BOT_AVATAR_URL
    })

@app.route('/shutdown', methods=['POST'])
def shutdown():
    # 1. Tell engine to exit (triggers summarization)
    response_content = asyncio.run(client.send_message("/exit"))
    
    # 2. Schedule actual process termination of THIS web server
    def terminate():
        import time
        import signal
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGINT)
        
    import threading
    threading.Thread(target=terminate).start()

    return jsonify({
        "response": markdown.markdown(response_content),
        "status": "Web UI shutting down... *clank*"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
