from gateway.run import _collect_existing_tool_media_tags


def test_collects_only_existing_tool_media(tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    messages = [
        {
            "role": "tool",
            "name": "skill_view",
            "content": "Example: MEDIA:/absolute/path/to/chart.png",
        },
        {
            "role": "tool",
            "name": "chart_renderer",
            "content": f"Rendered. MEDIA:{chart}",
        },
    ]

    tags, as_voice = _collect_existing_tool_media_tags(messages, set())

    assert tags == [f"MEDIA:{chart}"]
    assert as_voice is False


def test_voice_directive_requires_an_existing_media_file(tmp_path):
    messages = [
        {
            "role": "tool",
            "name": "skill_view",
            "content": "[[audio_as_voice]]\nMEDIA:/path/to/audio.ogg",
        }
    ]

    tags, as_voice = _collect_existing_tool_media_tags(messages, set())

    assert tags == []
    assert as_voice is False


def test_skips_media_already_delivered_in_history(tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    messages = [{"role": "tool", "content": f"MEDIA:{chart}"}]

    tags, _ = _collect_existing_tool_media_tags(messages, {str(chart)})

    assert tags == []
