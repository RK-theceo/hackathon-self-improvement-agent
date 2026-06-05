"""
agents/executor.py
------------------
ExecutorAgent — installs dependencies and executes generated code.

Supports:
  - Python  → writes temp .py file, runs with subprocess
  - HTML    → writes temp .html file, opens in browser
  - Bash    → writes temp .sh file, runs with subprocess
  - JavaScript (Node) → writes temp .js file, runs with subprocess

Returns structured result: success, output, error, error_type, install_log
"""

import os
import re
import subprocess
import sys
import tempfile
import webbrowser

import autogen
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# REPLACE THIS WITH YOUR EXECUTOR SYSTEM PROMPT
# ---------------------------------------------------------------------------
EXECUTOR_SYSTEM_PROMPT = "placeholder"
# ---------------------------------------------------------------------------

# Default system prompt (used when placeholder is not replaced)
_DEFAULT_SYSTEM_PROMPT = """You are SelfCode's ExecutorAgent.
Your only job is to confirm execution results. You receive pre-formatted execution
output and return it verbatim. Do not modify, summarise, or add commentary."""

# Directory for all temporary files
TMP_DIR = "/tmp/selfcode"


def _ensure_tmp_dir() -> None:
    """Create the temp directory if it doesn't exist."""
    os.makedirs(TMP_DIR, exist_ok=True)


def _get_effective_system_prompt() -> str:
    if EXECUTOR_SYSTEM_PROMPT and EXECUTOR_SYSTEM_PROMPT.strip() != "placeholder":
        return EXECUTOR_SYSTEM_PROMPT
    return _DEFAULT_SYSTEM_PROMPT


def _install_dependencies(deps: list) -> tuple:
    """
    Run pip install for each dependency in the list.
    Returns (success: bool, install_log: str).
    """
    if not deps:
        return True, ""

    install_log_parts = []
    all_success = True

    for dep in deps:
        dep = dep.strip()
        if not dep:
            continue
        if not re.match(r'^[a-zA-Z0-9_\-\.\[\]]+$', dep):
            install_log_parts.append(f"⚠️ Skipped invalid dependency: {dep}")
            continue
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep, "--quiet"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                install_log_parts.append(f"✅ Installed: {dep}")
            else:
                install_log_parts.append(
                    f"❌ Failed to install: {dep}\n{result.stderr.strip()}"
                )
                all_success = False
        except subprocess.TimeoutExpired:
            install_log_parts.append(f"⏱ Timeout installing: {dep}")
            all_success = False
        except Exception as e:
            install_log_parts.append(f"❌ Error installing {dep}: {e}")
            all_success = False

    return all_success, "\n".join(install_log_parts)


def _execute_python(code: str) -> dict:
    """Write code to a temp .py file and execute it."""
    _ensure_tmp_dir()
    tmp_path = os.path.join(TMP_DIR, "temp_code.py")

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "Execution timed out after 30 seconds.",
            "return_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1,
        }


def _execute_html(code: str) -> dict:
    """Write code to a temp .html file and open it in the browser."""
    _ensure_tmp_dir()
    tmp_path = os.path.join(TMP_DIR, "temp_code.html")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)
        webbrowser.open(f"file://{tmp_path}")
        return {
            "success": True,
            "output": f"HTML file created and opened: {tmp_path}",
            "error": None,
            "return_code": 0,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1,
        }


def _execute_bash(code: str) -> dict:
    """Write code to a temp .sh file and execute it with bash."""
    _ensure_tmp_dir()
    tmp_path = os.path.join(TMP_DIR, "temp_code.sh")

    # Ensure shebang
    if not code.strip().startswith("#!"):
        code = "#!/bin/bash\n" + code

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(code)

    os.chmod(tmp_path, 0o755)

    try:
        result = subprocess.run(
            ["bash", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "Bash execution timed out after 30 seconds.",
            "return_code": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": "bash not found on this system.",
            "return_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1,
        }


def _execute_javascript(code: str) -> dict:
    """Write code to a temp .js file and execute it with Node.js."""
    _ensure_tmp_dir()
    tmp_path = os.path.join(TMP_DIR, "temp_code.js")

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        result = subprocess.run(
            ["node", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "Node.js execution timed out after 30 seconds.",
            "return_code": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": "node not found. Please install Node.js.",
            "return_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1,
        }


def run_executor(language: str, code: str, dependencies: list) -> dict:
    """
    Main entry point for the ExecutorAgent.

    Steps:
      1. Auto-install any listed dependencies via pip.
      2. Execute the code based on detected language.
      3. Return structured result.

    Args:
        language:     Language string from generator (python, html, bash, javascript, etc.)
        code:         The generated source code string.
        dependencies: List of pip package names to install before running.

    Returns:
        dict with keys:
            success      (bool)
            output       (str)   — stdout or browser-open confirmation
            error        (str|None) — stderr or error message
            error_type   (str)   — rough category for upstream use
            install_log  (str)   — log of dependency installs
    """
    # Step 1: Install dependencies
    install_success, install_log = _install_dependencies(dependencies)

    if not install_success:
        return {
            "success": False,
            "output": "",
            "error": f"Dependency installation failed.\n{install_log}",
            "error_type": "dependency_error",
            "install_log": install_log,
        }

    # Step 2: Execute based on language
    lang = language.lower().strip()

    if lang in ("python", "py"):
        exec_result = _execute_python(code)
    elif lang in ("html", "html/css/js", "html/css", "web"):
        exec_result = _execute_html(code)
    elif lang in ("bash", "sh", "shell"):
        exec_result = _execute_bash(code)
    elif lang in ("javascript", "js", "node", "nodejs", "node.js"):
        exec_result = _execute_javascript(code)
    else:
        # Unknown language — try running as Python by default
        print(f"[executor] Unknown language '{lang}', defaulting to Python execution.")
        exec_result = _execute_python(code)

    # Classify rough error type from stderr for downstream use
    error_type = "none"
    if not exec_result["success"]:
        err = (exec_result.get("error") or "").lower()
        if "syntaxerror" in err or "invalid syntax" in err:
            error_type = "syntax_error"
        elif "importerror" in err or "modulenotfounderror" in err or "no module named" in err:
            error_type = "dependency_error"
        elif "timeout" in err:
            error_type = "runtime_error"
        elif "nameerror" in err or "attributeerror" in err or "typeerror" in err:
            error_type = "logic_error"
        elif "indexerror" in err or "keyerror" in err or "valueerror" in err:
            error_type = "edge_case_failure"
        else:
            error_type = "runtime_error"

    return {
        "success": exec_result["success"],
        "output": exec_result.get("output", ""),
        "error": exec_result.get("error"),
        "error_type": error_type,
        "install_log": install_log,
    }
