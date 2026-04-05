
import sys
import os

# Ensure the parent directory is in the path so we can import shadow_src (our 'src' copy)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from contextlib import asynccontextmanager
from tinybot_core import TinyBotCore

# Initialize the core engine
core = TinyBotCore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize core on startup
    core.initialize()
    yield
    # Cleanup on shutdown
    core.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    state = core.session_manager.get_state()
    return {
        "status": "online",
        "agent": state.get("active_agent_key", "Unknown"),
        "debug": state.get("debug", False)
    }

@app.get("/history")
async def get_history():
    state = core.session_manager.get_state()
    log_file = state.get("log_file")
    if log_file and os.path.exists(log_file):
        with open(log_file, "r") as f:
            content = f.read()
        return {"history": content}
    return {"history": "No history found."}

# Example endpoint for future dynamic agent interaction
import asyncio

@app.post("/interact")
async def interact(message: str):
    # Use a lock to ensure only one message is processed at a time
    # This prevents race conditions where Web and Telegram overlap
    async with core.session_manager.processing_lock:
        # Run the synchronous core.process in an executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, core.process, message)
        return {"response": response}
