import os
import time
from pinecone import Pinecone
from dotenv import load_dotenv
import uuid

load_dotenv()

# 1. Initialize the Client
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index_host = os.getenv("PINECONE_INDEX_HOST")

# 2. Connect to your specific Index
index = pc.Index(host=index_host)

def get_embedding(text):
    """
    Generates a vector using Pinecone's server-side model (llama-text-embed-v2).
    """
    try:
        # We use the 'inference' API to turn text -> numbers on their server
        response = pc.inference.embed(
            model="llama-text-embed-v2",
            inputs=[text],
            parameters={"input_type": "passage", "truncate": "END"}
        )
        return response[0]['values']
    except Exception as e:
        print(f"[Pinecone Embed Error] {e}")
        return None

def upsert_note(channel_id: str, text: str, note_type: str, timestamp: float):
    try:
        # A. Generate Vector
        vector = get_embedding(text)
        if not vector:
            return False

        # B. Create Unique ID (Channel + Time + Random UUID suffix)
        # OLD: unique_id = f"{channel_id}_{int(timestamp)}"
        # NEW:
        unique_id = f"{channel_id}_{int(timestamp)}_{str(uuid.uuid4())[:8]}"

        # ... rest of the function stays the same ...
        index.upsert(
            vectors=[{
                "id": unique_id,
                "values": vector, 
                "metadata": {
                    "channel": channel_id,
                    "text": text,       # <--- The AI needs this later!
                    "type": note_type,  # e.g. "DECISION"
                    "timestamp": timestamp
                }
            }]
        )
        print(f"✅ Saved note to Pinecone: {unique_id}")
        return True
        
    except Exception as e:
        print(f"[Pinecone Upsert Error] {e}")
        return False

def search_notes(query_text: str, channel_id: str = None, top_k=5):
    """
    Retrieves the most relevant notes for a user question.
    """
    # 1. Embed the query (using the same model!)
    response = pc.inference.embed(
        model="llama-text-embed-v2",
        inputs=[query_text],
        parameters={"input_type": "query"}
    )
    query_vector = response[0]['values']

    # 2. Search
    # If channel_id is provided, we filter results to ONLY that channel
    filter_dict = {"channel": channel_id} if channel_id else None

    results = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict
    )
    
    return results['matches']