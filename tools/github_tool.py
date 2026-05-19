#!/usr/bin/env python3
"""Host-side GitHub access through the authenticated GitHub CLI.

This tool intentionally does not expose an arbitrary ``gh`` command runner.
Hermes normally executes shell commands in Docker for isolation; private repo
access is a narrow host capability because the GitHub CLI token lives in the
host user's Secret Service keyring.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import quote

from tools.registry import registry, tool_error

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_MAX_FILE_BYTES = 200_000


def _gh_path() -> str | None:
    home_gh = os.path.join(os.path.expanduser("~"), ".local", "bin", "gh")
    if os.path.exists(home_gh) and os.access(home_gh, os.X_OK):
        return home_gh
    return shutil.which("gh")


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    home = os.path.expanduser("~")
    local_bin = os.path.join(home, ".local", "bin")
    env["PATH"] = f"{local_bin}:{env.get('PATH', '')}"
    env.setdefault("HOME", home)
    env.setdefault("GH_PAGER", "cat")
    return env


def _run_gh(args: list[str], *, timeout: int = 30) -> tuple[int, str]:
    gh = _gh_path()
    if not gh:
        return 127, "gh not found on host PATH"
    try:
        proc = subprocess.run(
            [gh, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            env=_gh_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"gh timed out after {timeout}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _json_result(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _validate_repo(repo: str) -> str:
    repo = (repo or "").strip()
    if not _REPO_RE.match(repo):
        raise ValueError("repo must be in owner/name format")
    return repo


def _validate_owner(owner: str) -> str:
    owner = (owner or "").strip()
    if owner and not _OWNER_RE.match(owner):
        raise ValueError("owner contains invalid characters")
    return owner


def _contents_endpoint(repo: str, path: str, ref: str) -> str:
    quoted_path = quote((path or "").strip().lstrip("/"), safe="/")
    endpoint = f"repos/{repo}/contents/{quoted_path}"
    if ref:
        endpoint += f"?ref={quote(ref, safe='')}"
    return endpoint


def github_tool(
    action: str,
    repo: str = "",
    path: str = "",
    ref: str = "",
    owner: str = "",
    visibility: str = "private",
    limit: int = 30,
) -> str:
    action = (action or "").strip().lower()
    try:
        if action == "status":
            code, output = _run_gh(["auth", "status"], timeout=15)
            return _json_result({"ok": code == 0, "status": output})

        if action == "list_repos":
            owner = _validate_owner(owner)
            visibility = visibility if visibility in {"all", "public", "private", "internal"} else "private"
            limit = max(1, min(int(limit or 30), 100))
            args = ["repo", "list"]
            if owner:
                args.append(owner)
            args.extend([
                "--visibility", visibility,
                "--limit", str(limit),
                "--json", "nameWithOwner,isPrivate,description,updatedAt",
            ])
            code, output = _run_gh(args, timeout=30)
            if code != 0:
                return tool_error(
                    output or "gh repo list failed",
                    code="github_list_repos_failed",
                )
            return output

        if action == "list_dir":
            repo = _validate_repo(repo)
            endpoint = _contents_endpoint(repo, path, ref)
            code, output = _run_gh(["api", endpoint], timeout=30)
            if code != 0:
                return tool_error(output or "gh api failed", code="github_list_dir_failed")
            data = json.loads(output or "[]")
            if isinstance(data, dict) and data.get("type") == "file":
                return _json_result({
                    "repo": repo,
                    "path": data.get("path"),
                    "type": "file",
                    "size": data.get("size"),
                    "sha": data.get("sha"),
                })
            entries = []
            for item in data if isinstance(data, list) else []:
                entries.append({
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "size": item.get("size"),
                    "sha": item.get("sha"),
                })
            return _json_result({"repo": repo, "path": path or "", "entries": entries})

        if action == "read_file":
            repo = _validate_repo(repo)
            if not path.strip():
                raise ValueError("path is required for read_file")
            endpoint = _contents_endpoint(repo, path, ref)
            code, output = _run_gh(["api", endpoint], timeout=30)
            if code != 0:
                return tool_error(output or "gh api failed", code="github_read_file_failed")
            data = json.loads(output)
            if data.get("type") != "file":
                return tool_error("path is not a file", code="github_path_not_file")
            size = int(data.get("size") or 0)
            if size > _MAX_FILE_BYTES:
                return tool_error(
                    f"file is {size} bytes; max supported is {_MAX_FILE_BYTES}",
                    code="github_file_too_large",
                )
            content = base64.b64decode((data.get("content") or "").encode()).decode(
                "utf-8", errors="replace"
            )
            return _json_result({
                "repo": repo,
                "path": data.get("path"),
                "sha": data.get("sha"),
                "size": size,
                "content": content,
            })

        return tool_error(
            "unknown action; use status, list_repos, list_dir, or read_file",
            code="github_unknown_action",
        )
    except ValueError as exc:
        return tool_error(str(exc), code="github_invalid_arguments")
    except json.JSONDecodeError:
        return tool_error("gh returned invalid JSON", code="github_invalid_json")
    except Exception as exc:
        return tool_error(str(exc), code="github_unexpected_error")


GITHUB_SCHEMA = {
    "name": "github",
    "description": (
        "Read private and public GitHub repositories through the host's "
        "authenticated GitHub CLI. Use this instead of terminal for private "
        "repo listing or file reads; terminal remains Docker-isolated."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "list_repos", "list_dir", "read_file"],
            },
            "repo": {
                "type": "string",
                "description": "Repository in owner/name format for list_dir/read_file.",
            },
            "path": {
                "type": "string",
                "description": "Repository path for list_dir/read_file.",
            },
            "ref": {
                "type": "string",
                "description": "Optional branch, tag, or commit SHA.",
            },
            "owner": {
                "type": "string",
                "description": "Optional owner for list_repos; omit for authenticated account.",
            },
            "visibility": {
                "type": "string",
                "enum": ["all", "public", "private", "internal"],
                "default": "private",
            },
            "limit": {
                "type": "integer",
                "default": 30,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": ["action"],
    },
}


def check_github_requirements() -> bool:
    gh = _gh_path()
    if not gh:
        return False
    code, _ = _run_gh(["auth", "status"], timeout=15)
    return code == 0


registry.register(
    name="github",
    toolset="github",
    schema=GITHUB_SCHEMA,
    handler=lambda args, **kw: github_tool(
        action=args.get("action", ""),
        repo=args.get("repo", ""),
        path=args.get("path", ""),
        ref=args.get("ref", ""),
        owner=args.get("owner", ""),
        visibility=args.get("visibility", "private"),
        limit=args.get("limit", 30),
    ),
    check_fn=check_github_requirements,
    emoji="GH",
)
