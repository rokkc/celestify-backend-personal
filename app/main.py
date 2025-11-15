import os
import json
import time
import redis
from fastapi import FastAPI, Request, BackgroundTasks
from app.worker import process_channel_buffer
from app.db import search_notes
from app.ai import generate_answer

app = FastAPI()

# Redis Client (Same as worker)
redis_url = os.getenv("REDIS_URL")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

@app.get("/")
def health():
    return {"status": "Celestify Core is Listening"}

@app.post("/slack/events")
async def slack_events(request: Request):
    """
    The main webhook URL you will give to Slack.
    """
    # 1. Get Body
    body = await request.json()

    # 2. Handle Slack URL Verification (The Handshake)
    # Slack sends this when you first verify the URL in their dashboard
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # 3. Handle Message Events
    event = body.get("event", {})
    
    # Ignore bot messages to prevent infinite loops
    if event.get("bot_id"):
        return {"status": "ignored_bot"}

    if event.get("type") == "message" and not event.get("subtype"):
        channel_id = event.get("channel")
        user_id = event.get("user")
        text = event.get("text")
        ts = event.get("ts")

        print(f"📩 Received msg from {user_id} in {channel_id}")

        # A. Push to Redis Buffer (The "Hot Window")
        msg_payload = json.dumps({
            "user": user_id, 
            "text": text, 
            "ts": ts
        })
        redis_client.rpush(f"buffer:{channel_id}", msg_payload)

        # B. Update "Last Active" Timestamp
        # This is used by the worker to check for silence
        redis_client.set(f"active:{channel_id}", time.time())

        # C. Schedule the Debounced Worker
        # "Try to process this channel in 5 minutes"
        # If the user keeps talking, the worker will see the updated timestamp 
        # and cancel itself.
        process_channel_buffer.apply_async(args=[channel_id], countdown=20)

    return {"status": "ok"}


@app.post("/chat/ask")
def ask_question(payload: dict):
    """
    Endpoint for the Slack Bot to get an answer.
    Payload: {"question": "...", "channel_id": "..."}
    """
    question = payload.get("question")
    channel_id = payload.get("channel_id")
    
    print(f"🤔 Thinking about: {question}")

    # 1. Fetch Hot Window (Redis)
    # Get the last 50 raw messages from the buffer to understand "now"
    # Note: Redis stores strings, need to parse JSON
    raw_buffer = redis_client.lrange(f"buffer:{channel_id}", -50, -1)
    hot_history = [json.loads(m) for m in raw_buffer]
    
    # 2. Fetch Cold Window (Pinecone)
    # Search for notes relevant to the specific QUESTION
    cold_notes = search_notes(query_text=question, channel_id=channel_id, top_k=5)
    
    # 3. Synthesize Answer (Gemini Pro)
    answer = generate_answer(question, hot_history, cold_notes)
    
    return {"answer": answer}
