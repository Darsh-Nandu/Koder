"""
git_tools.py
=============
Local git operations: init, add, commit, status, branch, checkout,
push, pull, remote, log, diff. Built on top of shell_tools.run_command.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from .common import ok, err
from .shell_tools import run_command


def git_init(path: str = ".") -> Dict[str, Any]:
    """Initialize a new git repository in the given directory (relative to workspace)."""
    result = run_command("git init", cwd=path)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Initialized git repo in {path}")
    return err(f"git init failed: {result.get('data', result['message'])}")


def git_add(paths: str = ".", cwd: str = ".") -> Dict[str, Any]:
    """
    Stage files for commit.

    Args:
        paths: Files/paths to add (default "." for everything).
        cwd: Working directory relative to workspace.
    """
    result = run_command(f"git add {paths}", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Staged '{paths}' in {cwd}")
    return err(f"git add failed: {result.get('data', result['message'])}")


def git_commit(message: str, cwd: str = ".", allow_empty: bool = False) -> Dict[str, Any]:
    """
    Commit staged changes.

    Args:
        message: Commit message.
        cwd: Working directory relative to workspace.
        allow_empty: Allow committing with no changes.
    """
    flag = "--allow-empty " if allow_empty else ""
    safe_message = message.replace('"', '\\"')
    result = run_command(f'git commit {flag}-m "{safe_message}"', cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Committed: {message}")
    return err(f"git commit failed: {result.get('data', result['message'])}")


def git_status(cwd: str = ".") -> Dict[str, Any]:
    """Get the current git status (porcelain format)."""
    result = run_command("git status --porcelain -b", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message="Fetched git status")
    return err(f"git status failed: {result.get('data', result['message'])}")


def git_branch(name: Optional[str] = None, cwd: str = ".", list_all: bool = False) -> Dict[str, Any]:
    """
    Create a new branch, or list branches.

    Args:
        name: Name of the branch to create. If None and list_all is True, lists branches.
        cwd: Working directory relative to workspace.
        list_all: If True (and name is None), list all branches.
    """
    if name:
        command = f"git branch {name}"
    elif list_all:
        command = "git branch -a"
    else:
        return err("Provide either 'name' to create a branch or set list_all=True to list branches.")

    result = run_command(command, cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"git branch executed: {command}")
    return err(f"git branch failed: {result.get('data', result['message'])}")


def git_checkout(branch: str, create_new: bool = False, cwd: str = ".") -> Dict[str, Any]:
    """
    Switch branches, optionally creating a new one.

    Args:
        branch: Branch name to switch to (or create).
        create_new: If True, creates the branch (git checkout -b).
        cwd: Working directory relative to workspace.
    """
    flag = "-b " if create_new else ""
    result = run_command(f"git checkout {flag}{branch}", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Checked out branch '{branch}'")
    return err(f"git checkout failed: {result.get('data', result['message'])}")


def git_push(remote: str = "origin", branch: Optional[str] = None, cwd: str = ".", set_upstream: bool = False) -> Dict[str, Any]:
    """
    Push commits to a remote.

    Args:
        remote: Remote name (default "origin").
        branch: Branch to push (default: current branch).
        cwd: Working directory relative to workspace.
        set_upstream: If True, adds -u flag to set upstream tracking.
    """
    flag = "-u " if set_upstream else ""
    branch_part = f" {branch}" if branch else ""
    result = run_command(f"git push {flag}{remote}{branch_part}", cwd=cwd, timeout=120)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Pushed to {remote}{branch_part}")
    return err(f"git push failed: {result.get('data', result['message'])}")


def git_pull(remote: str = "origin", branch: Optional[str] = None, cwd: str = ".") -> Dict[str, Any]:
    """
    Pull changes from a remote.

    Args:
        remote: Remote name (default "origin").
        branch: Branch to pull (default: current branch's tracked branch).
        cwd: Working directory relative to workspace.
    """
    branch_part = f" {branch}" if branch else ""
    result = run_command(f"git pull {remote}{branch_part}", cwd=cwd, timeout=120)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Pulled from {remote}{branch_part}")
    return err(f"git pull failed: {result.get('data', result['message'])}")


def git_remote_add(name: str, url: str, cwd: str = ".") -> Dict[str, Any]:
    """
    Add a git remote.

    Args:
        name: Remote name (e.g. "origin").
        url: Remote URL.
        cwd: Working directory relative to workspace.
    """
    result = run_command(f"git remote add {name} {url}", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Added remote '{name}' -> {url}")
    return err(f"git remote add failed: {result.get('data', result['message'])}")


def git_log(cwd: str = ".", max_count: int = 10) -> Dict[str, Any]:
    """Get recent commit history (oneline format)."""
    result = run_command(f"git log --oneline -n {max_count}", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message=f"Fetched last {max_count} commits")
    return err(f"git log failed: {result.get('data', result['message'])}")


def git_diff(cwd: str = ".", staged: bool = False) -> Dict[str, Any]:
    """
    Show diff of changes.

    Args:
        cwd: Working directory relative to workspace.
        staged: If True, show staged changes (--cached).
    """
    flag = "--cached" if staged else ""
    result = run_command(f"git diff {flag}", cwd=cwd)
    if result["success"] and result["data"]["returncode"] == 0:
        return ok(data=result["data"], message="Fetched git diff")
    return err(f"git diff failed: {result.get('data', result['message'])}")