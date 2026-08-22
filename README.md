# Memory Distiller

The Memory Distiller is a Python-based component effectively serving as the "Hippocampus" of the chatbot architecture. Its primary purpose is to process raw interaction logs (chat transcripts or agent traces), distill them into atomic, meaningful memories, scoring them for confidence and importance, and forwarding them to the long-term memory store.

## Architecture

The Distiller operates as a pipeline:
1.  **Segmentation**: Breaks raw text into discrete semantic events.
2.  **Worthiness Detection**: Filters out noise (chitchat, temporary context) to find memory-worthy items.
3.  **Synthesis**: Rewrites events into self-contained, declarative memory statements.
4.  **Scoring**: Assigns confidence (correctness) and importance (impact) scores.
5.  **Deduplication**: Removes redundant information.
6.  **Integration**: Maps data to the Memory API schema and POSTs it for storage.

It uses **Ollama** as the LLM backend for all semantic processing.

## API Usage

The component exposes a FastAPI endpoint at `/v1/distill`.

### Request
`POST /v1/distill`

```json
{
  "source": {
    "type": "chat",
    "id": "conversation-uuid"
  },
  "context": {
    "text": "User: I love Python. Bot: That is great!"
  },
  "metadata": {
    "user_id": "user-uuid",
    "tenant_id": "tenant-uuid",
    "timestamp": "2024-01-20T10:00:00Z"
  },
  "options": {
    "max_memories": 5
  }
}
```

**Note**: The `context` object is **optional**. If omitted, the distiller will automatically attempt to fetch the conversation transcript from the source API (Chatbot or Agent API) using the `source.id` and `source.type`.

### Response
```json
{
  "source": { ... },
  "memories": [
    {
      "type": "semantic",
      "content": "User enjoys programming in Python.",
      "confidence": 0.95,
      "importance": 0.4,
      "tags": ["programming", "python"],
      "justification": "Explicit user statement."
    }
  ],
  "stats": {
    "events_analyzed": 2,
    "memories_emitted": 1
  }
}
```

## Configuration

The application is configured via environment variables. Copy `.env.example` to `.env` to get started.

| Variable | Description |
| :--- | :--- |
| `OLLAMA_BASE_URL` | URL of the Ollama instance (default `http://localhost:11434`). |
| `API_BASE_URL` | Base URL for the other APIs (Chatbot, Agent, Memory). Attempts to fetch transcripts from here and posts results here (default `http://localhost:3000`). |
| `DEBUG` | Enable debug logging (`true`/`false`). |
| `TEMPERATURE` | Temperature for LLM generation (default `0.1`). |
| `PROMPT_*` | Custom prompts for each stage of the pipeline (see `.env.example`). |

## Setup & Running

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.ai/) running with `llama3.2` (or configured model) pulled.

### Local Development

1.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run Application**
    ```bash
    uvicorn main:app --reload --port 8000
    ```

### Docker

1.  **Build Image**
    ```bash
    docker build -t memory-distiller .
    ```

2.  **Run Container**
    ```bash
    docker run -p 8000:8000 --env-file .env memory-distiller
    ```

## Logic Mapping

The distiller maps its internal memory types to the Memory API categories as follows:

| Distiller Type | Memory API Category |
| :--- | :--- |
| `semantic` | `fact` |
| `episodic` | `context` |
| `procedural` | `instruction` |

Importance scores (0.0 - 1.0) are mapped to:
- `critical`: >= 0.9
- `high`: >= 0.7
- `medium`: >= 0.4
- `low`: < 0.4
