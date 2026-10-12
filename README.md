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
| `PIPELINE_MODE` | `combined` (default) or `sequential`. Changes how many LLM calls the pipeline makes. |
| `CONFIDENCE_THRESHOLD` | Worthiness cutoff (default `0.5`). |
| `MEMORY_MODE` | `distiller` (default), `neuralese`, `neuralese-distiller`, or `off`. |

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

## Prompts

All prompt text lives in `prompts/*.md`, one file per stage, loaded by `prompts.py` at
import time. **Prompts are not configurable at runtime.** The `PROMPT_SEGMENTATION`,
`PROMPT_WORTHINESS`, `PROMPT_SYNTHESIS`, `PROMPT_SCORING`, `PROMPT_COMBINED_EVAL` and
`SYSTEM_PREAMBLE` environment overrides were removed on purpose: with any of them set, the
reported `promptset_hash` described text that was not what ran, which silently invalidates
an eval baseline.

Editing a prompt:

1. Edit the `.md` file under `prompts/`.
2. Bump `version` in its frontmatter, and `prompts/promptset.json` if the change is
   meaningful.
3. `python prompts.py --write-lock` to regenerate `prompts/promptset.lock.json`.
4. `python -m pytest -q` to confirm the drift gate passes.
5. Commit the markdown and the regenerated lock together.

`tests/test_prompts.py::TestDriftGate` fails when the markdown no longer matches the
committed lock, which is what catches a prompt edit that shipped without a version bump.

Read-only inspection of a running deployment, gated to bouc.io staff roles:

```bash
GET /v1/distill/prompts                 # inventory: id, version, hash
GET /v1/distill/prompts/{id}            # template as authored
GET /v1/distill/prompts/{id}/rendered   # preamble + stage prompt, as sent
GET /v1/distill/promptset               # version + hash for this deployment
```

Full design, including the inventory and the known divergences preserved on purpose:
[PROMPT_MANAGEMENT.md](../../agent/agent-api-server/PROMPT_MANAGEMENT.md)

## Quality Gates

```bash
ruff check .            # lint
ruff check . --fix      # auto-fix what is mechanically fixable
ruff format .           # format, write
ruff format --check .   # format, check only
python -m pytest -q     # unit tests
```

CI runs `lint` and `unit-test` from the shared `bouc-io/ci-templates` project
(`python.yml`). Ruff replaces flake8, black, and isort in one tool; its configuration
lives in `pyproject.toml`.

- **Both lint and format gate the pipeline.** Unlike the Node repos there is no warning
  ratchet here: ruff currently reports zero findings, so the gate is simply "stays clean".
- **`E501` (line too long) is disabled on purpose.** `ruff format` already enforces line
  length everywhere it can. The only lines that exceeded it were inside strings it cannot
  split: long log and error messages in `assignment_config_client.py` and `main.py`.
  Prompt text lives in `prompts/*.md`, which ruff does not lint.
- **`ruff format` is idempotent**, so unlike the prettier-based repos a single pass is
  enough.
- Unit tests must stay free of live dependencies. Anything needing a running memory-api,
  agent-api, or LLM belongs in a local integration run, not CI.

## License

[Elastic License 2.0](./LICENSE) — source-available; not OSI open source.
