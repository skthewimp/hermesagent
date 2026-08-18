"""Regression tests for ephemeral context on multimodal user turns."""

from run_agent import _inject_user_message_context


def test_injects_context_into_plain_text_content():
    assert _inject_user_message_context("Fix this chart", ["guard token"]) == (
        "Fix this chart\n\nguard token"
    )


def test_injects_context_into_multimodal_content_without_mutating_history():
    original = [
        {"type": "text", "text": "Fix this chart"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]

    injected = _inject_user_message_context(
        original,
        ["Hermes release guard: use --session 'hermes-guard-123'"],
    )

    assert injected == [
        *original,
        {
            "type": "text",
            "text": "Hermes release guard: use --session 'hermes-guard-123'",
        },
    ]
    assert injected is not original
    assert len(original) == 2


def test_joins_multiple_context_sources_for_multimodal_content():
    injected = _inject_user_message_context(
        [{"type": "text", "text": "Describe this image"}],
        ["memory context", "plugin context"],
    )

    assert injected[-1] == {
        "type": "text",
        "text": "memory context\n\nplugin context",
    }


def test_empty_context_leaves_content_unchanged():
    content = [{"type": "text", "text": "hello"}]

    assert _inject_user_message_context(content, []) is content
