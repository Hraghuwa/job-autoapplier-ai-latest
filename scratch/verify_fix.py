import asyncio
import json
import uuid
import time
import httpx
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Mock settings
SECRET_KEY = "b37c35377faadeba51fe6464c10a32bf8f4dfe99119948b1cc93e4ff49c7ad32"
ALGORITHM = "HS256"
USER_ID = "42641418-6dfa-4b27-b902-6d31021c81bd"

def create_token(user_id):
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def trigger_and_verify():
    token = create_token(USER_ID)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Trigger agent run (Phase 1 LinkedIn)
    async with httpx.AsyncClient() as client:
        print("Triggering agent run...")
        response = await client.post(
            "http://localhost:3002/agents/run",
            json={"phases": [1]},
            headers=headers
        )
        print(f"Response: {response.status_code} - {response.text}")
        if response.status_code != 200:
            return

        run_id = response.json()["run_ids"][0]
        print(f"Run ID: {run_id}")

        # 2. Wait for it to start failing or succeeding
        print("Waiting 10 seconds for agent to start...")
        await asyncio.sleep(10)

        # 3. Check logs in DB
        db_path = "/tmp/jadb/jobagent.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()

        from sqlalchemy import text
        result = session.execute(text("SELECT event_type, message FROM agent_logs WHERE run_id = :rid ORDER BY created_at DESC"), {"rid": run_id.replace("-", "")})
        logs = result.fetchall()
        
        print("\n--- RECENT LOGS ---")
        for log in logs:
            print(f"[{log[0]}] {log[1]}")
        
        has_str_error = any("'str' object has no attribute 'get'" in str(log[1]) for log in logs)
        if has_str_error:
            print("\n❌ FIX FAILED: Still seeing 'str' object error.")
        else:
            print("\n✅ LOGS LOOK GOOD (No 'str' object error seen yet).")
        
        session.close()

if __name__ == "__main__":
    asyncio.run(trigger_and_verify())
