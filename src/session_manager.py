import threading
import json
import os
import asyncio

class SessionManager:
    """Thread-safe manager for core agent and application state."""
    def __init__(self):
        self._lock = threading.Lock()
        self._processing_lock = None # Will be initialized lazily in the event loop
        self.state = {
            "agents": {},
            "subagents": {},
            "active_agent_key": None,
            "document_context": None,
            "available_skills": []
        }

    @property
    def processing_lock(self):
        if self._processing_lock is None:
            self._processing_lock = asyncio.Lock()
        return self._processing_lock

    def update_agent(self, key, agent_instance):
        with self._lock:
            self.state["agents"][key] = agent_instance

    def set_active_agent(self, key):
        with self._lock:
            self.state["active_agent_key"] = key

    def get_active_agent(self):
        with self._lock:
            return self.state["agents"].get(self.state["active_agent_key"])

    def get_state(self):
        with self._lock:
            return self.state
