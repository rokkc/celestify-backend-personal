import os
import json
import time
import redis
from celery import Celery
from dotenv import load_dotenv

# Import our verified AI/DB modules
from app.ai import summarize_messages
from app.db import upsert_note

load_dotenv()

# 1. Configure Celery
celery_app = Celery(
    "ambient_ai",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

# 2. Redis Client (for fetching the buffer)
# We need to parse the URL to get connection details if not using localhost
redis_url = os.getenv("REDIS_URL")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

@celery_app.task(bind=True)
def process_channel_buffer(self, channel_id):
    """
    The 'Debounced' Task.
    It runs 5 minutes after a message is received.
    It checks if the channel has been silent since then.
    """
    print(f"🧐 Checking buffer for channel: {channel_id}")
    
    # A. Check for recent activity (The "Silence Check")
    # We store the timestamp of the LAST message in 'active:{channel_id}'
    last_active = redis_client.get(f"active:{channel_id}")
    
    if last_active:
        time_since_active = time.time() - float(last_active)
        # If someone spoke in the last 4.5 minutes, abort! 
        # We let the NEWER task (scheduled by the newer message) handle it.
        if time_since_active < 280: 
            print(f"   -> Channel active {int(time_since_active)}s ago. Skipping (Debounce).")
            return "Skipped: Too active"

    # B. Fetch Messages
    # Get all messages from the list 'buffer:{channel_id}'
    raw_messages = redis_client.lrange(f"buffer:{channel_id}", 0, -1)
    
    if not raw_messages:
        return "Skipped: Buffer empty"

    print(f"   -> Processing {len(raw_messages)} messages...")
    
    # Parse JSON strings back to dicts
    messages_data = [json.loads(m) for m in raw_messages]
    
    # C. Call Gemini (The Note Taker)
    notes = summarize_messages(messages_data)
    
    if not notes:
        # If no notes generated, we still clear buffer to avoid infinite loops
        redis_client.delete(f"buffer:{channel_id}")
        return "Processed: No important notes found"

    # D. Save to Pinecone
    saved_count = 0
    current_time = time.time()
    for note in notes:
        success = upsert_note(
            channel_id=channel_id,
            text=note['text'],
            note_type=note['type'],
            timestamp=current_time
        )
        if success: saved_count += 1

    # E. Cleanup
    # Clear the buffer only after successful processing
    redis_client.delete(f"buffer:{channel_id}")
    
    return f"Success: Saved {saved_count} notes."