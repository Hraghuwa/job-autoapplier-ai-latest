import asyncio
import websockets
import json
from jose import jwt
import time

# Mock settings from backend/config.py and .env
SECRET_KEY = "b37c35377faadeba51fe6464c10a32bf8f4dfe99119948b1cc93e4ff49c7ad32"
ALGORITHM = "HS256"
USER_ID = "42641418-6dfa-4b27-b902-6d31021c81bd" # From subagent report

def create_token(user_id):
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def test_ws():
    token = create_token(USER_ID)
    uri = f"ws://localhost:3002/ws/{USER_ID}?token={token}"
    print(f"Connecting to {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected successfully!")
            # Send a ping
            await websocket.send("ping")
            print("Sent ping")
            # Wait for any response (though backend might not send one back immediately)
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"Received: {msg}")
            except asyncio.TimeoutError:
                print("No message received (normal if agent not running)")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
