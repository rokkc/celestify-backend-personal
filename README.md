# Celestify AI Core

The backend engine for the Celestify Ambient Slack AI. This service handles real-time message ingestion, asynchronous "note-taking" via Gemini 1.5 Flash, and semantic retrieval (RAG) via Pinecone.

## 🏗 Architecture

* **API (FastAPI):** Receives raw webhooks from Slack and pushes them to a Redis buffer.
* **Worker (Celery):** Background processes that batch messages, summarize them using AI, and update the Vector DB.
* **Database:**
    * **Redis:** Hot storage (Message buffers, deduplication, task queues).
    * **Pinecone:** Cold storage (Vector embeddings of decisions/notes).
* **AI Models:**
    * **Gemini 1.5 Flash:** High-volume summarization & entity extraction.
    * **Gemini 2.5 Pro:** Complex reasoning & Q/A.





    