"""
Prompt registry for the Memory Distiller.

Prompt text lives in ``prompts/*.md``, one file per unit with YAML-ish frontmatter. This
module loads them at import time, hashes each one, and exposes the registry.

Unlike the Node services there is no codegen step: the Dockerfile copies the whole tree
(``COPY . .``) and ``.dockerignore`` only excludes ``README.md`` and the design doc, so the
markdown ships as-is and can be read at runtime.

**Runtime overrides were deliberately removed.** The previous version let
``PROMPT_SEGMENTATION``, ``PROMPT_WORTHINESS``, ``PROMPT_SYNTHESIS``, ``PROMPT_SCORING``,
``PROMPT_COMBINED_EVAL`` and ``SYSTEM_PREAMBLE`` replace prompt text from the environment.
That made ``PROMPTSET_HASH`` a lie whenever one was set, which would quietly corrupt an
eval baseline. Prompt text now changes only through git.
"""

import hashlib
import pathlib
from typing import Any

PROMPTS_DIR = pathlib.Path(__file__).resolve().parent / "prompts"
_PROMPTSET_FILE = PROMPTS_DIR / "promptset.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_frontmatter(raw: str, source: str) -> tuple[dict[str, Any], str]:
    """
    Split leading ``---`` frontmatter from the body.

    Only single-line ``key: value`` pairs are supported, which is all the generator emits.
    Keeping it dependency-free avoids pulling PyYAML in for six files.
    """
    if not raw.startswith("---\n"):
        raise ValueError(f"{source}: missing frontmatter (file must start with '---')")
    end = raw.find("\n---\n", 3)
    if end == -1:
        raise ValueError(f"{source}: unterminated frontmatter (no closing '---')")

    meta: dict[str, Any] = {}
    for line in raw[4 : end + 1].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"{source}: unparseable frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    for key in ("id", "title", "version", "stage", "role"):
        if key not in meta:
            raise ValueError(f"{source}: frontmatter is missing required key '{key}'")
    meta["version"] = int(meta["version"])

    body = raw[end + 5 :]
    # Strip exactly one trailing newline: files end with one because text files should,
    # but the prompt itself must not carry it (the original constants had none).
    if body.endswith("\n"):
        body = body[:-1]
    return meta, body


def _compute_set_hash(version: str, registry: dict[str, dict[str, Any]]) -> str:
    """
    Set hash over the promptset version plus every unit's id, declared version and resolved
    template hash. Same formula as the Node services, so the two hashes mean the same thing.

    Derived from the registry rather than cached, so build_lock() reflects the prompts
    actually loaded and a template change moves the hash.
    """
    return _sha256(
        "\n".join(
            [f"promptset:{version}"]
            + [
                f"{pid}@{entry['meta']['version']}:{entry['hash']}"
                for pid, entry in sorted(registry.items())
            ]
        )
    )


def _load() -> tuple[str, str, dict[str, dict[str, Any]]]:
    if not _PROMPTSET_FILE.exists():
        raise FileNotFoundError(f"missing {_PROMPTSET_FILE}")

    import json

    version = json.loads(_PROMPTSET_FILE.read_text(encoding="utf-8")).get("version")
    if not version:
        raise ValueError("prompts/promptset.json is missing a 'version' field")

    registry: dict[str, dict[str, Any]] = {}
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"), path.name)
        pid = meta["id"]
        if pid in registry:
            raise ValueError(f"duplicate prompt id '{pid}' in {path.name}")
        registry[pid] = {"meta": meta, "template": body, "hash": _sha256(body)}

    if not registry:
        raise ValueError(f"no prompt files found in {PROMPTS_DIR}")

    return version, _compute_set_hash(version, registry), registry


PROMPTSET_VERSION, PROMPTSET_HASH, PROMPTS = _load()


# ---------------------------------------------------------------------------
# Drift gate
#
# The Node services get this for free: their codegen emits a committed generated.ts that
# carries every hash, so comparing a fresh build against it detects a prompt edit that
# shipped without a version bump. This service loads markdown at runtime with nothing
# committed to compare against, so the lock file below plays that role.
#
# Regenerate after an intentional prompt change:   python prompts.py --write-lock
# ---------------------------------------------------------------------------

LOCK_FILE = PROMPTS_DIR / "promptset.lock.json"


def build_lock() -> dict[str, Any]:
    """The exact contents that belong in promptset.lock.json, deterministically ordered."""
    return {
        "promptset_version": PROMPTSET_VERSION,
        "promptset_hash": _compute_set_hash(PROMPTSET_VERSION, PROMPTS),
        "prompts": {
            pid: {"version": entry["meta"]["version"], "hash": entry["hash"]}
            for pid, entry in sorted(PROMPTS.items())
        },
    }


def read_lock() -> dict[str, Any] | None:
    """Committed lock, or None when it has never been written."""
    import json

    if not LOCK_FILE.exists():
        return None
    return json.loads(LOCK_FILE.read_text(encoding="utf-8"))


def write_lock() -> dict[str, Any]:
    import json

    lock = build_lock()
    LOCK_FILE.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock


if __name__ == "__main__":
    import sys

    if "--write-lock" in sys.argv:
        written = write_lock()
        print(
            f"prompts: wrote {LOCK_FILE.name} - {len(written['prompts'])} units, "
            f"promptset {written['promptset_version']} ({written['promptset_hash'][:12]})"
        )
    else:
        print(f"usage: python {pathlib.Path(__file__).name} --write-lock")
        sys.exit(2)


def get_prompt(prompt_id: str) -> str:
    """Prompt text by id. Raises KeyError for an unknown id."""
    if prompt_id not in PROMPTS:
        raise KeyError(f"Unknown prompt id: {prompt_id}")
    return PROMPTS[prompt_id]["template"]


def prompt_hash(prompt_id: str) -> str:
    if prompt_id not in PROMPTS:
        raise KeyError(f"Unknown prompt id: {prompt_id}")
    return PROMPTS[prompt_id]["hash"]


def list_prompts() -> list[dict[str, Any]]:
    """Metadata for every unit, id-sorted. Backs GET /v1/prompts."""
    return [
        {
            "id": pid,
            "title": entry["meta"]["title"],
            "version": entry["meta"]["version"],
            "stage": entry["meta"]["stage"],
            "role": entry["meta"]["role"],
            "hash": entry["hash"],
            "note": entry["meta"].get("note"),
        }
        for pid, entry in sorted(PROMPTS.items())
    ]


def promptset_summary(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "promptset_version": PROMPTSET_VERSION,
        "promptset_hash": PROMPTSET_HASH,
        "unit_count": len(PROMPTS),
    }
    if extra:
        summary.update(extra)
    return summary
