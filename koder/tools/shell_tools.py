"""
shell_tools.py
================
Run shell commands in a sandboxed working directory.
"""

from __future__ import annotations

import subprocess
from typing import Optional, Dict, Any

from .common import resolve_path, ok, err, ToolError, WORKSPACE_DIR


def run_command(command: str, timeout: int = 60, cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    Run a shell command and capture stdout/stderr/exit code.

    Args:
        command: The shell command to execute.
        timeout: Max execution time in seconds (default 60).
        cwd: Optional working directory relative to the workspace.

    Returns:
        dict with success flag, message, and data (stdout, stderr, returncode).
    """
    try:
        work_dir = resolve_path(cwd) if cwd else WORKSPACE_DIR

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        data = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

        if result.returncode == 0:
            return ok(data=data, message=f"Command succeeded: {command}")
        return ok(data=data, message=f"Command exited with code {result.returncode}: {command}")

    except ToolError as e:
        return err(str(e))
    except subprocess.TimeoutExpired:
        return err(f"Command timed out after {timeout}s: {command}")
    except Exception as e:
        return err(f"Failed to run command '{command}': {e}")