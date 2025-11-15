import os
import json
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model_flash = genai.GenerativeModel('gemini-2.5-flash')

# The "Brain" Prompt
# We ask for JSON so we can easily parse it in Python code later
SYSTEM_PROMPT = """
You are an ambient AI secretary for a Slack workspace.
Analyze the following transcript of messages.
Extract strictly structured notes in JSON format.

Rules:
1. Ignore phatic communication (hello, thanks, lol).
2. Extract DECISIONS (conclusions reached).
3. Extract BLOCKERS (problems preventing progress).
4. Extract RESOURCES (links, documents shared).
5. If nothing significant happened, return an empty list [].

Output Format:
[
  {"type": "DECISION", "text": "The team decided to use Postgres."},
  {"type": "BLOCKER", "text": "API is returning 500 error on login."}
]
"""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def summarize_messages(messages_list):
    """
    Sends raw Slack messages to Gemini 2.5 Flash and returns structured notes.
    """
    # Convert list of dicts to a single string for the prompt
    # Format: "User: Message content"
    transcript = "\n".join([f"{m.get('user', 'Unknown')}: {m.get('text', '')}" for m in messages_list])
    
    if not transcript.strip():
        return []

    prompt = f"{SYSTEM_PROMPT}\n\n--- START TRANSCRIPT ---\n{transcript}\n--- END TRANSCRIPT ---"

    try:
        # We enforce JSON response for reliability
        response = model_flash.generate_content(
            prompt, 
            generation_config={"response_mime_type": "application/json"}
        )
        
        return json.loads(response.text)
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return []


model_pro = genai.GenerativeModel('gemini-2.5-pro')

def generate_answer(query: str, hot_history: list, cold_notes: list):
    """
    Synthesizes an answer using:
    1. Hot History (Raw text from Redis - last 2 hours)
    2. Cold Notes (Summaries from Pinecone - older knowledge)
    """
    
    # Format inputs for the prompt
    hot_context = "\n".join([f"{m['user']}: {m['text']}" for m in hot_history])
    cold_context = "\n".join([f"- {note['metadata']['text']} (Type: {note['metadata']['type']})" for note in cold_notes])
    
    full_prompt = f"""
    You are an intelligent Slack assistant. Answer the user's question using the provided context.
    
    [LONG TERM MEMORY (Verified Decisions & Notes)]
    {cold_context}
    
    [SHORT TERM MEMORY (Recent Raw Conversation)]
    {hot_context}
    
    [USER QUESTION]
    {query}
    
    Instructions:
    - Prioritize [SHORT TERM MEMORY] for immediate context (e.g. "what did Dave just say?").
    - Prioritize [LONG TERM MEMORY] for facts (e.g. "what did we decide last week?").
    - If the answer is not in the context, say "I don't have that information."
    - Be concise and helpful.
    """
    
    try:
        response = model_pro.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"I encountered an error thinking about that: {e}"