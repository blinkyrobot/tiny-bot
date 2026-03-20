import httpx
import asyncio

class HeadlessClient:
    """Utility client to interface with the TinyBot Headless Engine."""
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url

    async def send_message(self, message: str):
        """Sends a message to the headless engine and returns the response."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/interact", 
                    params={"message": message},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json().get("response", "No response found in server output.")
            except httpx.ConnectError:
                return "Error: Could not connect to the engine server. Is it running?"
            except httpx.HTTPStatusError as e:
                return f"Server returned an error status: {e.response.status_code}"
            except Exception as e:
                return f"An unexpected communication error occurred: {e}"

    async def check_health(self):
        """Checks the heartbeat of the engine."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"status": "offline", "error": str(e)}

    async def get_history(self):
        """Retrieves the current session history."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}/history", timeout=5.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"history": f"Error retrieving history: {e}"}
