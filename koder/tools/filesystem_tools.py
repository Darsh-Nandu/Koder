"""
filesystem_tools.py
====================
File and directory operations sandboxed to WORKSPACE_DIR:
read, write, create, delete, list, and check existence.
"""

from __future__ import annotations

import shutil
from typing import Optional, List, Dict, Any

from .common import resolve_path, ok, err, ToolError, WORKSPACE_DIR


def read_file(path: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
    """
    Read the contents of a text file.

    Args:
        path: Path relative to the workspace directory.
        max_chars: Optional limit on number of characters returned.

    Returns:
        dict with success flag, message, and data (file contents as string).
    """
    try:
        file_path = resolve_path(path)
        if not file_path.exists():
            return err(f"File not found: {path}")
        if file_path.is_dir():
            return err(f"Path is a directory, not a file: {path}")

        content = file_path.read_text(encoding="utf-8", errors="replace")
        truncated = False
        if max_chars is not None and len(content) > max_chars:
            content = content[:max_chars]
            truncated = True

        return ok(
            data={"content": content, "truncated": truncated},
            message=f"Read {len(content)} characters from {path}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to read file '{path}': {e}")


def write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    """
    Write content to a file, creating it if it doesn't exist.
    Creates parent directories automatically.

    Args:
        path: Path relative to the workspace directory.
        content: Text content to write.
        overwrite: If False and file exists, the operation fails.

    Returns:
        dict with success flag, message, and data.
    """
    try:
        file_path = resolve_path(path)
        if file_path.exists() and file_path.is_file() and not overwrite:
            return err(f"File already exists and overwrite=False: {path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return ok(
            data={"path": str(file_path.relative_to(WORKSPACE_DIR)), "bytes": len(content.encode("utf-8"))},
            message=f"Wrote {len(content)} characters to {path}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to write file '{path}': {e}")


def create_file(path: str, content: str = "") -> Dict[str, Any]:
    """
    Create a new file. Fails if the file already exists.

    Args:
        path: Path relative to the workspace directory.
        content: Initial content (default empty).

    Returns:
        dict with success flag, message, and data.
    """
    try:
        file_path = resolve_path(path)
        if file_path.exists():
            return err(f"File already exists: {path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return ok(
            data={"path": str(file_path.relative_to(WORKSPACE_DIR))},
            message=f"Created file {path}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to create file '{path}': {e}")


def delete_file(path: str) -> Dict[str, Any]:
    """
    Delete a file or directory (recursively) at the given path.

    Args:
        path: Path relative to the workspace directory.

    Returns:
        dict with success flag, message, and data.
    """
    try:
        target = resolve_path(path)
        if target == WORKSPACE_DIR:
            return err("Refusing to delete the workspace root directory.")
        if not target.exists():
            return err(f"Path not found: {path}")

        if target.is_dir():
            shutil.rmtree(target)
            kind = "directory"
        else:
            target.unlink()
            kind = "file"

        return ok(data={"path": path, "type": kind}, message=f"Deleted {kind}: {path}")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to delete '{path}': {e}")


def list_directory(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """
    List files and directories at the given path.

    Args:
        path: Path relative to the workspace directory (default: workspace root).
        recursive: If True, walk the entire subtree.

    Returns:
        dict with success flag, message, and data (list of relative paths).
    """
    try:
        dir_path = resolve_path(path)
        if not dir_path.exists():
            return err(f"Directory not found: {path}")
        if not dir_path.is_dir():
            return err(f"Path is not a directory: {path}")

        entries: List[str] = []
        if recursive:
            for p in sorted(dir_path.rglob("*")):
                entries.append(str(p.relative_to(WORKSPACE_DIR)) + ("/" if p.is_dir() else ""))
        else:
            for p in sorted(dir_path.iterdir()):
                entries.append(p.name + ("/" if p.is_dir() else ""))

        return ok(data={"entries": entries}, message=f"Listed {len(entries)} entries in {path}")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to list directory '{path}': {e}")


def file_exists(path: str) -> Dict[str, Any]:
    """Check whether a file or directory exists at the given path."""
    try:
        target = resolve_path(path)
        exists = target.exists()
        kind = "directory" if target.is_dir() else "file" if target.is_file() else None
        return ok(data={"exists": exists, "type": kind}, message=f"'{path}' exists: {exists}")
    except ToolError as e:
        return err(str(e))