import base64
import json

from tools import github_tool


def test_invalid_repo_returns_structured_error():
    result = json.loads(github_tool.github_tool(action="list_dir", repo="not-a-repo"))

    assert result == {
        "error": "repo must be in owner/name format",
        "code": "github_invalid_arguments",
    }


def test_unknown_action_returns_structured_error():
    result = json.loads(github_tool.github_tool(action="clone"))

    assert result["code"] == "github_unknown_action"
    assert "unknown action" in result["error"]


def test_list_dir_uses_gh_api_and_normalizes_entries(monkeypatch):
    payload = json.dumps([
        {
            "name": "README.md",
            "path": "README.md",
            "type": "file",
            "size": 42,
            "sha": "abc123",
        }
    ])
    calls = []

    def fake_run(args, *, timeout=30):
        calls.append(args)
        return 0, payload

    monkeypatch.setattr(github_tool, "_run_gh", fake_run)

    result = json.loads(
        github_tool.github_tool(
            action="list_dir",
            repo="owner/repo",
            path="docs",
            ref="main",
        )
    )

    assert calls == [["api", "repos/owner/repo/contents/docs?ref=main"]]
    assert result == {
        "repo": "owner/repo",
        "path": "docs",
        "entries": [
            {
                "name": "README.md",
                "path": "README.md",
                "type": "file",
                "size": 42,
                "sha": "abc123",
            }
        ],
    }


def test_read_file_decodes_base64_content(monkeypatch):
    content = base64.b64encode(b"hello\n").decode()
    payload = json.dumps({
        "type": "file",
        "path": "README.md",
        "sha": "abc123",
        "size": 6,
        "content": content,
    })

    monkeypatch.setattr(github_tool, "_run_gh", lambda args, *, timeout=30: (0, payload))

    result = json.loads(
        github_tool.github_tool(
            action="read_file",
            repo="owner/repo",
            path="README.md",
        )
    )

    assert result["repo"] == "owner/repo"
    assert result["path"] == "README.md"
    assert result["sha"] == "abc123"
    assert result["size"] == 6
    assert result["content"] == "hello\n"
