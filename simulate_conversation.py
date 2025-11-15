import time
import json
import redis
import os
from dotenv import load_dotenv
from app.worker import process_channel_buffer

load_dotenv()

# Setup Redis
redis_url = os.getenv("REDIS_URL")
r = redis.Redis.from_url(redis_url, decode_responses=True)

CHANNEL_ID = "C-SIMULATION-TEST"

# A fake conversation about choosing a tech stack
conversation = [
    {"user": "U_ALICE", "text": "Hey team, we need to pick a frontend framework for the dashboard."},
    {"user": "U_BOB", "text": "I prefer React because the ecosystem is huge."},
    {"user": "U_CHARLIE", "text": "I am currently blocked by the old Angular legacy code, we need to migrate that first."},
    {"user": "U_ALICE", "text": "Good point. But for the new stuff, let's stick with React."},
    {"user": "U_BOB", "text": "Agreed. React it is."},
    {"user": "U_ALICE", "text": "Also, here is the link to the design specs: https://figma.com/file/123"}
]

def run_simulation():
    print(f"🚀 Starting Simulation in channel: {CHANNEL_ID}")
    
    # 1. Clear old data
    r.delete(f"buffer:{CHANNEL_ID}")
    r.delete(f"active:{CHANNEL_ID}")

    # 2. Simulate "Typing"
    for msg in conversation:
        print(f"   💬 {msg['user']} says: {msg['text']}")
        
        # Push to Redis (mimicking the Slack Bot)
        msg['ts'] = time.time()
        r.rpush(f"buffer:{CHANNEL_ID}", json.dumps(msg))
        
        # Update "Active" timestamp
        r.set(f"active:{CHANNEL_ID}", time.time())
        
        # Trigger the worker (mimicking the API)
        # In the real app, this happens on every message with a countdown.
        # We set countdown=10s so we can see the result quickly.
        process_channel_buffer.apply_async(args=[CHANNEL_ID], countdown=10)
        
        time.sleep(1) # Simulate 1 second between messages

    print("\n✅ Messages sent! The conversation has now 'gone silent'.")
    print("⏳ The AI Worker should wake up in ~10 seconds...")

if __name__ == "__main__":
    run_simulation()
