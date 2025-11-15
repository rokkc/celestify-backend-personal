import os
import json
import time
import redis
from celery import Celery
from dotenv import load_dotenv

# Import our AI and DB modules
from app.ai import summarize_messages
from app.db import upsert_note

load_dotenv()

# 1. Configure Celery
# Note: We use the REDIS_URL from .env (which includes the ssl_cert_reqs fix if you added it)
celery_app = Celery(
    "ambient_ai",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

# 2. Redis Client (for fetching the buffer manually)
redis_url = os.getenv("REDIS_URL")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

@celery_app.task(bind=True)
def process_channel_buffer(self, channel_id):
    """
    The Smart Worker Task.
    1. Checks for Silence (Debounce).
    2. Processes messages in CHUNKS of 500 (Safe for massive loads).
    3. Summarizes & Saves to Pinecone.
    """
    print(f"🧐 Checking buffer for channel: {channel_id}")
    
    # --- STEP A: DEBOUNCE (The Silence Check) ---
    # We store the timestamp of the LAST message in 'active:{channel_id}'
    last_active = redis_client.get(f"active:{channel_id}")
    
    if last_active:
        time_since_active = time.time() - float(last_active)
        # 280 seconds = ~4.5 minutes. 
        # We use 280 instead of 300 to give a tiny buffer before the next scheduled check.
        if time_since_active < 280: 
            print(f"   -> Channel active {int(time_since_active)}s ago. Skipping.")
            return "Skipped: Too active"

    # --- STEP B: PROCESSING LOOP (Chunking) ---
    total_notes_saved = 0
    
    while True:
        # Fetch the first 500 messages
        # (0 to 499 is 500 items)
        raw_messages = redis_client.lrange(f"buffer:{channel_id}", 0, 499)
        
        # If the list is empty, we are done!
        if not raw_messages:
            break

        print(f"   Processing chunk of {len(raw_messages)} messages...")
        
        # Parse JSON
        try:
            messages_data = [json.loads(m) for m in raw_messages]
        except Exception as e:
            print(f"   Error parsing JSON in batch: {e}")
            # Safety valve: If data is corrupt, remove it so we don't loop forever
            redis_client.ltrim(f"buffer:{channel_id}", len(raw_messages), -1)
            continue

        # Call Gemini (The Note Taker)
        # This summarizes the batch of 500
        notes = summarize_messages(messages_data)
        
        if notes:
            # Save to Pinecone
            current_time = time.time()
            for note in notes:
                upsert_note(
                    channel_id=channel_id,
                    text=note['text'],
                    note_type=note['type'],
                    timestamp=current_time
                )
            total_notes_saved += len(notes)
            print(f"   -> Saved {len(notes)} notes from this chunk.")
        else:
            print("   -> No important info found in this chunk.")

        # --- STEP C: CLEANUP (Trim the Buffer) ---
        # Delete the 500 messages we just processed.
        # 'ltrim' keeps the range you specify. 
        # So we say "Keep everything from index 500 to the end".
        # This effectively deletes 0-499.
        redis_client.ltrim(f"buffer:{channel_id}", len(raw_messages), -1)
        
        # Sleep briefly to be nice to the Gemini API Rate Limits
        time.sleep(2)

    # Final Cleanup
    # We remove the 'active' key so the system knows this session is fully closed.
    redis_client.delete(f"active:{channel_id}")
    
    return f"Success: Processed complete. Saved {total_notes_saved} new notes."
