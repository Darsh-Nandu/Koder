"""
github_tools.py
=================
GitHub API operations via PyGithub: repo info, file read/write,
branches, pull requests, issues, code search, and cloning.

Requires GITHUB_TOKEN in .env.
Install dependency: pip install PyGithub --break-system-packages
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

from .common import ok, err, ToolError, GITHUB_TOKEN
from .shell_tools import run_command


def _get_github_client():
    """Lazily import and construct a PyGithub client using GITHUB_TOKEN."""
    if not GITHUB_TOKEN:
        raise ToolError("GITHUB_TOKEN is not set in the environment (.env).")
    try:
        from github import Github, Auth
    except ImportError as e:
        raise ToolError(
            "PyGithub is not installed. Run: pip install PyGithub --break-system-packages"
        ) from e
    return Github(auth=Auth.Token(GITHUB_TOKEN))


def github_get_repo(repo_full_name: str) -> Dict[str, Any]:
    """
    Get basic information about a GitHub repository.

    Args:
        repo_full_name: e.g. "owner/repo"

    Returns:
        dict with success flag, message, and data (repo metadata).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        data = {
            "full_name": repo.full_name,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "open_issues": repo.open_issues_count,
            "url": repo.html_url,
            "private": repo.private,
            "language": repo.language,
        }
        return ok(data=data, message=f"Fetched repo info for {repo_full_name}")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to get repo '{repo_full_name}': {e}")


def github_list_files(repo_full_name: str, path: str = "", ref: Optional[str] = None) -> Dict[str, Any]:
    """
    List files/directories in a GitHub repo path.

    Args:
        repo_full_name: e.g. "owner/repo"
        path: Path within the repo (default: root).
        ref: Optional branch/tag/commit SHA.

    Returns:
        dict with success flag, message, and data (list of {name, path, type}).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        kwargs = {"ref": ref} if ref else {}
        contents = repo.get_contents(path, **kwargs)
        if not isinstance(contents, list):
            contents = [contents]

        entries = [
            {"name": c.name, "path": c.path, "type": c.type, "size": c.size}
            for c in contents
        ]
        return ok(data={"entries": entries}, message=f"Listed {len(entries)} entries in {repo_full_name}:{path or '/'}")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to list files in '{repo_full_name}': {e}")


def github_read_file(repo_full_name: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Read a file's contents from a GitHub repository.

    Args:
        repo_full_name: e.g. "owner/repo"
        path: File path within the repo.
        ref: Optional branch/tag/commit SHA.

    Returns:
        dict with success flag, message, and data (file content as text).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        kwargs = {"ref": ref} if ref else {}
        content_file = repo.get_contents(path, **kwargs)
        if isinstance(content_file, list):
            return err(f"Path '{path}' is a directory, not a file.")

        decoded = content_file.decoded_content.decode("utf-8", errors="replace")
        return ok(
            data={"content": decoded, "sha": content_file.sha},
            message=f"Read {path} from {repo_full_name}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to read file '{path}' from '{repo_full_name}': {e}")


def github_create_or_update_file(
    repo_full_name: str,
    path: str,
    content: str,
    commit_message: str,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new file or update an existing file in a GitHub repo, committing directly.

    Args:
        repo_full_name: e.g. "owner/repo"
        path: File path within the repo.
        content: New file content.
        commit_message: Commit message.
        branch: Branch to commit to (default: repo's default branch).

    Returns:
        dict with success flag, message, and data (commit info).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        branch = branch or repo.default_branch

        try:
            existing = repo.get_contents(path, ref=branch)
            result = repo.update_file(
                path=path,
                message=commit_message,
                content=content,
                sha=existing.sha,
                branch=branch,
            )
            action = "updated"
        except Exception:
            result = repo.create_file(
                path=path,
                message=commit_message,
                content=content,
                branch=branch,
            )
            action = "created"

        commit = result["commit"]
        return ok(
            data={"sha": commit.sha, "url": commit.html_url, "action": action},
            message=f"File '{path}' {action} in {repo_full_name}@{branch}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to create/update file '{path}' in '{repo_full_name}': {e}")


def github_create_branch(repo_full_name: str, new_branch: str, source_branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new branch from an existing branch (default: repo's default branch).

    Args:
        repo_full_name: e.g. "owner/repo"
        new_branch: Name of the new branch.
        source_branch: Branch to branch off from (default: repo default branch).

    Returns:
        dict with success flag, message, and data.
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        source_branch = source_branch or repo.default_branch

        source_ref = repo.get_git_ref(f"heads/{source_branch}")
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=source_ref.object.sha)

        return ok(
            data={"branch": new_branch, "from": source_branch},
            message=f"Created branch '{new_branch}' from '{source_branch}' in {repo_full_name}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to create branch '{new_branch}' in '{repo_full_name}': {e}")


def github_create_pull_request(
    repo_full_name: str,
    title: str,
    head: str,
    base: Optional[str] = None,
    body: str = "",
) -> Dict[str, Any]:
    """
    Create a pull request.

    Args:
        repo_full_name: e.g. "owner/repo"
        title: PR title.
        head: Branch containing changes (e.g. "feature-branch", or "user:branch" for forks).
        base: Branch to merge into (default: repo's default branch).
        body: PR description.

    Returns:
        dict with success flag, message, and data (PR info).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        base = base or repo.default_branch

        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        return ok(
            data={"number": pr.number, "url": pr.html_url, "state": pr.state},
            message=f"Created PR #{pr.number} in {repo_full_name}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to create pull request in '{repo_full_name}': {e}")


def github_create_issue(repo_full_name: str, title: str, body: str = "", labels: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Create an issue in a GitHub repository.

    Args:
        repo_full_name: e.g. "owner/repo"
        title: Issue title.
        body: Issue description.
        labels: Optional list of label names.

    Returns:
        dict with success flag, message, and data (issue info).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        issue = repo.create_issue(title=title, body=body, labels=labels or [])
        return ok(
            data={"number": issue.number, "url": issue.html_url},
            message=f"Created issue #{issue.number} in {repo_full_name}",
        )
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to create issue in '{repo_full_name}': {e}")


def github_list_issues(repo_full_name: str, state: str = "open") -> Dict[str, Any]:
    """
    List issues in a GitHub repository.

    Args:
        repo_full_name: e.g. "owner/repo"
        state: "open", "closed", or "all" (default: "open").

    Returns:
        dict with success flag, message, and data (list of issues).
    """
    try:
        gh = _get_github_client()
        repo = gh.get_repo(repo_full_name)
        issues = repo.get_issues(state=state)

        data = [
            {"number": i.number, "title": i.title, "state": i.state, "url": i.html_url}
            for i in issues
        ]
        return ok(data={"issues": data}, message=f"Found {len(data)} issues ({state}) in {repo_full_name}")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Failed to list issues in '{repo_full_name}': {e}")


def github_search_code(query: str, repo_full_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Search code on GitHub.

    Args:
        query: Search query (GitHub code search syntax).
        repo_full_name: Optionally restrict search to a single repo "owner/repo".

    Returns:
        dict with success flag, message, and data (list of matching files).
    """
    try:
        gh = _get_github_client()
        full_query = f"{query} repo:{repo_full_name}" if repo_full_name else query
        results = gh.search_code(query=full_query)

        data = []
        for item in results[:20]:
            data.append({"path": item.path, "repo": item.repository.full_name, "url": item.html_url})

        return ok(data={"results": data}, message=f"Found {len(data)} code search results for '{query}'")
    except ToolError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Code search failed for '{query}': {e}")


def github_clone_repo(repo_full_name: str, dest_path: str, branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Clone a GitHub repository into the workspace using git (via run_command).
    Uses GITHUB_TOKEN for authentication on private repos.

    Args:
        repo_full_name: e.g. "owner/repo"
        dest_path: Destination directory relative to the workspace.
        branch: Optional branch to clone.

    Returns:
        dict with success flag, message, and data (stdout/stderr from git).
    """
    try:
        if GITHUB_TOKEN:
            url = f"https://{GITHUB_TOKEN}@github.com/{repo_full_name}.git"
        else:
            url = f"https://github.com/{repo_full_name}.git"

        branch_flag = f"-b {branch}" if branch else ""
        command = f"git clone {branch_flag} {url} {dest_path}"

        result = run_command(command, timeout=120)
        if result["success"] and result["data"]["returncode"] == 0:
            return ok(data=result["data"], message=f"Cloned {repo_full_name} into {dest_path}")
        return err(f"git clone failed: {result['data']}")
    except Exception as e:
        return err(f"Failed to clone '{repo_full_name}': {e}")