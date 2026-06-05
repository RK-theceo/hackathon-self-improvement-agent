"""
agents/generator.py
-------------------
GeneratorAgent — produces code for any task type.
Uses Groq API directly (no AutoGen chat overhead).

OUTPUT FORMAT (always):
  LANGUAGE: <python|html|bash|javascript|etc>
  DEPENDENCIES: <comma-separated pip packages or "none">
  ```<lang>
  <full code>
  ```
  CONFIDENCE: X/10 — <one-line reason>
"""

import os
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# REPLACE THIS WITH YOUR GENERATOR SYSTEM PROMPT
# ---------------------------------------------------------------------------
GENERATOR_SYSTEM_PROMPT = "placeholder"
# ---------------------------------------------------------------------------

# Default system prompt used when placeholder is not replaced
_DEFAULT_SYSTEM_PROMPT = """You are SelfCode's GeneratorAgent — an expert programmer that writes correct, runnable code for any task.

RULES:
1. Detect the task type: Python, HTML/CSS/JS, Bash, Node.js, etc.
2. Always respond in EXACTLY this format — no deviations:

LANGUAGE: <python|html|bash|javascript|etc>
DEPENDENCIES: <comma-separated pip packages or "none">
```<language>
<full working code here>
```
CONFIDENCE: X/10 — <one-line reason why you're this confident>

3. DEPENDENCIES must list every pip package the code imports that is not in stdlib. If none needed, write exactly: none
4. Do NOT add any explanation, comments, or text outside the format above.
5. On retry iterations you will receive: previous code, error output, error category, iteration number, and memory hints. Use ALL of them to write a corrected version.
6. Be precise with indentation, imports, and edge cases.
7. For HTML tasks: write a complete self-contained HTML file with embedded CSS and JS.
8. For Bash tasks: write a complete .sh script starting with #!/bin/bash.
9. For Node.js tasks: write complete .js code using require() or ES modules as appropriate.
10. The code block must start with ``` and end with ``` on its own line. No exceptions.
"""


def _get_effective_system_prompt() -> str:
    """Return the custom system prompt if set, otherwise fall back to default."""
    if GENERATOR_SYSTEM_PROMPT and GENERATOR_SYSTEM_PROMPT.strip() != "placeholder":
        return GENERATOR_SYSTEM_PROMPT
    return _DEFAULT_SYSTEM_PROMPT


def _build_prompt(
    task: str,
    iteration: int,
    previous_code: str = None,
    error_output: str = None,
    error_category: str = None,
    memory_hints: str = None,
    expected_output: str = None,
) -> str:
    """
    Build the full prompt for the generator.
    First iteration: clean task + memory hints + optional expected output.
    Retry iterations: include previous code, error, category, and memory hints.
    """
    parts = []

    if iteration == 1:
        parts.append(f"TASK:\n{task.strip()}")
        if expected_output:
            parts.append(f"\nEXPECTED OUTPUT (your code must produce this exactly):\n{expected_output.strip()}")
        if memory_hints:
            parts.append(f"\n{memory_hints}")
        parts.append(
            "\nRespond ONLY in the required format:\n"
            "LANGUAGE: ...\nDEPENDENCIES: ...\n```lang\n<code>\n```\nCONFIDENCE: X/10 — reason"
        )
    else:
        parts.append(f"RETRY — ITERATION {iteration}/3\n")
        parts.append(f"ORIGINAL TASK:\n{task.strip()}")
        if expected_output:
            parts.append(f"\nEXPECTED OUTPUT:\n{expected_output.strip()}")
        if previous_code:
            parts.append(f"\nPREVIOUS CODE (that failed):\n```\n{previous_code}\n```")
        if error_output:
            parts.append(f"\nERROR OUTPUT:\n{error_output.strip()}")
        if error_category:
            parts.append(f"\nERROR CATEGORY: {error_category}")
        if memory_hints:
            parts.append(f"\n{memory_hints}")
        parts.append(
            "\nFix the code completely. Respond ONLY in the required format:\n"
            "LANGUAGE: ...\nDEPENDENCIES: ...\n```lang\n<code>\n```\nCONFIDENCE: X/10 — reason"
        )

    return "\n".join(parts)


def _parse_response(response_text: str) -> dict:
    """
    Parse the generator's response into structured fields.
    Returns dict with keys: language, dependencies, code, confidence_score, confidence_reason, raw.
    Falls back gracefully on parse errors.
    """
    result = {
        "language": "python",
        "dependencies": [],
        "code": "",
        "confidence_score": 5,
        "confidence_reason": "parse error — defaulting to 5",
        "raw": response_text,
    }

    try:
        # Extract LANGUAGE
        lang_match = re.search(r"LANGUAGE:\s*(\S+)", response_text, re.IGNORECASE)
        if lang_match:
            result["language"] = lang_match.group(1).lower().strip()

        # Extract DEPENDENCIES — filter out anything that isn't a real package name
        dep_match = re.search(r"DEPENDENCIES:\s*(.+)", response_text, re.IGNORECASE)
        if dep_match:
            raw_deps = dep_match.group(1).strip()
            if raw_deps.lower() in ("none", "null", "n/a", "...", "") or not raw_deps:
                result["dependencies"] = []
            else:
                result["dependencies"] = [
                    d.strip() for d in raw_deps.split(",")
                    if d.strip() and re.match(r'^[a-zA-Z0-9_\-\.\[\]]+$', d.strip())
                ]

        # Extract CODE block — multiple strategies in order of preference
        code_match = re.search(
            r"```(?:python|html|bash|javascript|js|sh|node)?\s*\n(.*?)```",
            response_text,
            re.DOTALL | re.IGNORECASE,
        )
        if code_match:
            result["code"] = code_match.group(1).strip()
        else:
            # Fallback 1: any ``` block
            fallback = re.search(r"```\s*\n?(.*?)```", response_text, re.DOTALL)
            if fallback:
                extracted = fallback.group(1).strip()
                # Strip language name if it snuck in as the first line
                lines = extracted.splitlines()
                if lines and re.match(
                    r'^(python|html|bash|javascript|js|sh|node|lang)$',
                    lines[0].strip(),
                    re.IGNORECASE,
                ):
                    extracted = "\n".join(lines[1:]).strip()
                result["code"] = extracted
            else:
                # Fallback 2: everything between DEPENDENCIES line and CONFIDENCE line
                after_deps = re.split(r'DEPENDENCIES:.*\n', response_text, flags=re.IGNORECASE)
                if len(after_deps) > 1:
                    chunk = after_deps[1].split("CONFIDENCE:")[0].strip()
                    result["code"] = chunk

        # Extract CONFIDENCE
        conf_match = re.search(
            r"CONFIDENCE:\s*(\d+)\s*/\s*10\s*[—\-–]\s*(.+)",
            response_text,
            re.IGNORECASE,
        )
        if conf_match:
            raw_score = int(conf_match.group(1))
            result["confidence_score"] = max(1, min(10, raw_score))  # clamp 1-10
            result["confidence_reason"] = conf_match.group(2).strip()

    except Exception as e:
        print(f"[generator] Parse warning: {e}")

    return result


def run_generator(
    task: str,
    iteration: int = 1,
    previous_code: str = None,
    error_output: str = None,
    error_category: str = None,
    memory_hints: str = None,
    expected_output: str = None,
) -> dict:
    """
    Call the GeneratorAgent via Groq API directly and return parsed output.

    Args:
        task:            The user's task description.
        iteration:       Current iteration number (1-3).
        previous_code:   Code from the last failed iteration.
        error_output:    Error text from the last failed execution.
        error_category:  Category string from the ValidatorAgent.
        memory_hints:    Formatted string from memory.py.
        expected_output: Optional expected output string from user.

    Returns:
        dict with keys: language, dependencies, code, confidence_score,
                        confidence_reason, raw
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment. Check your .env file.")

    client = Groq(api_key=api_key)
    system_prompt = _get_effective_system_prompt()

    prompt = _build_prompt(
        task=task,
        iteration=iteration,
        previous_code=previous_code,
        error_output=error_output,
        error_category=error_category,
        memory_hints=memory_hints,
        expected_output=expected_output,
    )

    # Call Groq API directly — no AutoGen overhead
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    raw_response = response.choices[0].message.content or ""

    # Debug print — remove after confirming it works
    print(f"[generator] Iteration {iteration} raw response preview:\n{raw_response[:500]}\n")

    if not raw_response.strip():
        print("[generator] Warning: empty response from Groq.")
        raw_response = (
            "LANGUAGE: python\nDEPENDENCIES: none\n"
            "```python\n# empty\n```\n"
            "CONFIDENCE: 1/10 — no response received"
        )

    return _parse_response(raw_response)
