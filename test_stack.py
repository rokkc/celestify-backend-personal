# test_stack.py
from app.db import upsert_note, search_notes
from app.ai import summarize_messages
import time

print("1. Testing Gemini Summary...")
fake_messages = [
    {"user": "Yash", "text": "Guys, we are definitely switching to Pinecone."},
    {"user": "Co-founder", "text": "Agreed. It's cheaper."}
]
notes = summarize_messages(fake_messages)
print(f"Generated Notes: {notes}")

if notes:
    print("\n2. Testing Pinecone Upsert...")
    # Take the first note and save it
    note = notes[0]
    upsert_note("channel_test", note['text'], note['type'], time.time())
    
    print("\n3. Waiting 5 seconds for index to update...")
    time.sleep(5)
    
    print("\n4. Testing Retrieval...")
    results = search_notes("What database are we using?", "channel_test")
    for match in results:
        print(f"Found: {match['metadata']['text']} (Score: {match['score']})")