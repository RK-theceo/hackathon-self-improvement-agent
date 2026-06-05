"""
memory.py
---------
Handles all memory read/write/search operations for SelfCode.
Memory persists across tasks in memory.json.
"""

import json
import os
from datetime import datetime

# Path to the memory file (relative to project root)
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")


def _load_memory() -> list:
    """Load all memory entries from memory.json. Returns empty list on any error."""
    try:
        if not os.path.exists(MEMORY_FILE):
            return []
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError):
        return []


def _save_memory(entries: list) -> None:
    """Write the full memory list back to memory.json."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"[memory] Warning: could not save memory — {e}")


def _extract_keywords(task: str) -> list:
    """
    Simple keyword extractor: lowercase, split on whitespace/punctuation,
    filter out common stopwords, return unique words of length >= 3.
    """
    import re
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "into",
        "are", "was", "has", "have", "had", "not", "but", "can", "all",
        "any", "each", "will", "write", "code", "create", "make", "build",
        "using", "use", "which", "when", "then", "also", "just", "like",
        "some", "such", "its", "our", "your", "their", "they", "them",
        "output", "print", "return", "function", "script", "program",
    }
    words = re.findall(r"[a-z]+", task.lower())
    unique = list({w for w in words if len(w) >= 3 and w not in stopwords})
    return unique


def search_memory(task: str, top_k: int = 3) -> list:
    """
    Search memory for entries whose task_keywords overlap with the current task.
    Requires at least 2 matching keywords. Returns top_k entries sorted by overlap count.

    Returns a list of (entry, overlap_count) tuples — only the entry dicts in practice
    (wrapped for scoring then unwrapped before returning).
    """
    entries = _load_memory()
    if not entries:
        return []

    task_keywords = set(_extract_keywords(task))
    scored = []

    for entry in entries:
        stored_keywords = set(entry.get("task_keywords", []))
        overlap = len(task_keywords & stored_keywords)
        if overlap >= 2:
            scored.append((overlap, entry))

    # Sort descending by overlap count
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def write_memory(
    task: str,
    task_type: str,
    error_type: str,
    fix_summary: str,
    iterations_needed: int,
    final_confidence: int,
    overconfident_flagged: bool,
) -> None:
    """
    Append a new memory entry to memory.json.
    Called after every run, pass or fail.
    """
    entries = _load_memory()

    new_entry = {
        "task_keywords": _extract_keywords(task),
        "task_type": task_type,
        "error_type": error_type,
        "fix_summary": fix_summary,
        "iterations_needed": iterations_needed,
        "final_confidence": final_confidence,
        "overconfident_flagged": overconfident_flagged,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    entries.append(new_entry)
    _save_memory(entries)


def clear_memory() -> None:
    """Overwrite memory.json with an empty list."""
    _save_memory([])


def format_memory_hints(matches: list) -> str:
    """
    Format matched memory entries into a readable string to inject
    into the generator prompt as past-mistake hints.
    """
    if not matches:
        return ""

    lines = ["Past mistakes on similar tasks — avoid these:"]
    for i, entry in enumerate(matches, 1):
        task_type = entry.get("task_type", "unknown")
        error_type = entry.get("error_type", "unknown")
        fix = entry.get("fix_summary", "no details")
        conf = entry.get("final_confidence", "?")
        iters = entry.get("iterations_needed", "?")
        lines.append(
            f"  {i}. [{task_type}] Error type '{error_type}': {fix} "
            f"(took {iters} iterations, final confidence {conf}/10)"
        )

    return "\n".join(lines)
