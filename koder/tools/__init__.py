"""
tools package
==============
A collection of tools for a coding agent, split by category:

    - common.py          : shared config, helpers, errors
    - filesystem_tools.py: read/write/create/delete/list files
    - shell_tools.py      : run terminal commands
    - git_tools.py        : local git operations (init, add, commit, push, ...)
    - github_tools.py      : GitHub API operations (PyGithub)
    - search_tools.py      : web search (Tavily / Serper)

Usage:
    from tools import read_file, write_file, run_command, git_commit, web_search
    from tools import TOOL_REGISTRY
"""

from .common import ToolError

from .filesystem_tools import (
    read_file,
    write_file,
    create_file,
    delete_file,
    list_directory,
    file_exists,
)

from .shell_tools import run_command

from .git_tools import (
    git_init,
    git_add,
    git_commit,
    git_status,
    git_branch,
    git_checkout,
    git_push,
    git_pull,
    git_remote_add,
    git_log,
    git_diff,
)

from .github_tools import (
    github_get_repo,
    github_list_files,
    github_read_file,
    github_create_or_update_file,
    github_create_branch,
    github_create_pull_request,
    github_create_issue,
    github_list_issues,
    github_search_code,
    github_clone_repo,
)

from .search_tools import web_search


__all__ = [
    "ToolError",
    # Filesystem
    "read_file",
    "write_file",
    "create_file",
    "delete_file",
    "list_directory",
    "file_exists",
    # Shell
    "run_command",
    # Git (local)
    "git_init",
    "git_add",
    "git_commit",
    "git_status",
    "git_branch",
    "git_checkout",
    "git_push",
    "git_pull",
    "git_remote_add",
    "git_log",
    "git_diff",
    # GitHub API
    "github_get_repo",
    "github_list_files",
    "github_read_file",
    "github_create_or_update_file",
    "github_create_branch",
    "github_create_pull_request",
    "github_create_issue",
    "github_list_issues",
    "github_search_code",
    "github_clone_repo",
    # Web search
    "web_search",
    # Registry
    "TOOL_REGISTRY",
]


# ----------------------------------------------------------------------
# Tool Registry (for easy introspection / agent binding)
# ----------------------------------------------------------------------

TOOL_REGISTRY = {
    # Filesystem
    "read_file": read_file,
    "write_file": write_file,
    "create_file": create_file,
    "delete_file": delete_file,
    "list_directory": list_directory,
    "file_exists": file_exists,
    # Shell
    "run_command": run_command,
    # Git (local)
    "git_init": git_init,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_status": git_status,
    "git_branch": git_branch,
    "git_checkout": git_checkout,
    "git_push": git_push,
    "git_pull": git_pull,
    "git_remote_add": git_remote_add,
    "git_log": git_log,
    "git_diff": git_diff,
    # GitHub API
    "github_get_repo": github_get_repo,
    "github_list_files": github_list_files,
    "github_read_file": github_read_file,
    "github_create_or_update_file": github_create_or_update_file,
    "github_create_branch": github_create_branch,
    "github_create_pull_request": github_create_pull_request,
    "github_create_issue": github_create_issue,
    "github_list_issues": github_list_issues,
    "github_search_code": github_search_code,
    "github_clone_repo": github_clone_repo,
    # Web search
    "web_search": web_search,
}