"""
agents/validator.py
-------------------
ValidatorAgent — validates execution results and categorises errors.

Validation rules:
  - If expected output provided → compare actual vs expected (strip whitespace)
  - If no expected output → pass if return_code == 0 and stderr is empty
  - HTML tasks → always pass if file was created and opened with no crash

Error categories (exactly one per failure):
  syntax_error | logic_error | edge_case_failure | runtime_error | dependency_error

Overconfidence check: confidence >= 7 AND result is fail → overconfident: True

Returns:
    passed          (bool)
    error_category  (str|None)
    overconfident   (bool)
    feedback        (str) — injected into next generator prompt
"""

import os
import re

import autogen
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# REPLACE THIS WITH YOUR VALIDATOR SYSTEM PROMPT
# ---------------------------------------------------------------------------
VALIDATOR_SYSTEM_PROMPT = "placeholder"
# ---------------------------------------------------------------------------

# Default system prompt (used when placeholder is not replaced)
_DEFAULT_SYSTEM_PROMPT = """You are SelfCode's ValidatorAgent.
You evaluate whether code execution passed or failed based on strict rules.
You categorise errors precisely and provide concise, actionable feedback for the generator.
Never hallucinate output — work only with the data you are given."""


def _get_effective_system_prompt() -> str:
    if VALIDATOR_SYSTEM_PROMPT and VALIDATOR_SYSTEM_PROMPT.strip() != "placeholder":
        return VALIDATOR_SYSTEM_PROMPT
    return _DEFAULT_SYSTEM_PROMPT


def _normalise(text: str) -> str:
    """Strip and normalise whitespace for comparison."""
    return re.sub(r"\s+", " ", (text or "").strip())


def _categorise_error(error_type_hint: str, error_text: str, output: str) -> str:
    """
    Map executor's rough error_type hint + stderr text to one of the five categories.
    error_type_hint comes from executor's own rough classification.
    """
    # Trust the executor's hint if it's specific
    if error_type_hint in (
        "syntax_error",
        "logic_error",
        "edge_case_failure",
        "runtime_error",
        "dependency_error",
    ):
        return error_type_hint

    # Fallback: re-classify from text
    err_lower = (error_text or "").lower()
    out_lower = (output or "").lower()

    if "syntaxerror" in err_lower or "invalid syntax" in err_lower:
        return "syntax_error"
    if (
        "importerror" in err_lower
        or "modulenotfounderror" in err_lower
        or "no module named" in err_lower
        or "dependency" in err_lower
    ):
        return "dependency_error"
    if (
        "indexerror" in err_lower
        or "keyerror" in err_lower
        or "valueerror" in err_lower
        or "edge" in err_lower
    ):
        return "edge_case_failure"
    if (
        "nameerror" in err_lower
        or "attributeerror" in err_lower
        or "typeerror" in err_lower
        or "logic" in err_lower
        or "wrong" in out_lower
        or "incorrect" in out_lower
    ):
        return "logic_error"

    return "runtime_error"


def _build_feedback(
    passed: bool,
    error_category: str,
    actual_output: str,
    expected_output: str,
    error_text: str,
    overconfident: bool,
    iteration: int,
) -> str:
    """Build a feedback string to pass back to the generator on failure."""
    if passed:
        return "All checks passed. No further action needed."

    parts = [f"Validation failed (iteration {iteration}/3)."]

    if error_category:
        parts.append(f"Error category: {error_category}.")

    if error_text:
        # Truncate very long error messages
        truncated = error_text.strip()[:800]
        parts.append(f"Error details:\n{truncated}")

    if expected_output:
        norm_expected = _normalise(expected_output)
        norm_actual = _normalise(actual_output or "")
        parts.append(f"Expected output: {norm_expected!r}")
        parts.append(f"Actual output:   {norm_actual!r}")
        parts.append("Fix the code so it produces the exact expected output.")
    else:
        parts.append("Fix the code so it runs without errors (return code 0, no stderr).")

    if overconfident:
        parts.append(
            "⚠️ Overconfidence detected: you rated your confidence >= 7 but the code failed. "
            "Be more conservative in your confidence estimate next time."
        )

    return "\n".join(parts)


def run_validator(
    language: str,
    exec_success: bool,
    actual_output: str,
    error_text: str,
    error_type_hint: str,
    confidence_score: int,
    expected_output: str = None,
    iteration: int = 1,
) -> dict:
    """
    Validate the execution result and return a structured verdict.

    Args:
        language:         Language of the executed code.
        exec_success:     Whether subprocess returned code 0.
        actual_output:    stdout from execution.
        error_text:       stderr / error message from execution.
        error_type_hint:  Rough error type from executor.
        confidence_score: Generator's self-reported confidence (1-10).
        expected_output:  Optional expected output string from user.
        iteration:        Current iteration number.

    Returns:
        dict with keys:
            passed          (bool)
            error_category  (str|None)
            overconfident   (bool)
            feedback        (str)
    """
    # ---- Determine pass / fail ----------------------------------------
    lang = (language or "").lower().strip()

    if lang in ("html", "html/css/js", "html/css", "web"):
        # HTML tasks: pass if no crash and file was opened
        passed = exec_success
    elif expected_output and expected_output.strip():
        # Compare normalised actual vs expected
        norm_actual = _normalise(actual_output or "")
        norm_expected = _normalise(expected_output)
        passed = norm_actual == norm_expected
    else:
        # Default: pass if no stderr and exec succeeded
        passed = exec_success and not (error_text and error_text.strip())

    # ---- Categorise error (only relevant on failure) -------------------
    error_category = None
    if not passed:
        error_category = _categorise_error(error_type_hint, error_text, actual_output)

    # ---- Overconfidence check ------------------------------------------
    overconfident = (not passed) and (confidence_score >= 7)

    # ---- Build feedback for next generator iteration -------------------
    feedback = _build_feedback(
        passed=passed,
        error_category=error_category,
        actual_output=actual_output,
        expected_output=expected_output,
        error_text=error_text,
        overconfident=overconfident,
        iteration=iteration,
    )

    return {
        "passed": passed,
        "error_category": error_category,
        "overconfident": overconfident,
        "feedback": feedback,
    }
