"""Regression tests for the local Noenthuda archive and search script."""

import os
from unittest.mock import patch

from scripts import noenthuda_archive as archive


def _post(post_id: int = 1) -> archive.Post:
    return archive.Post(
        post_id=post_id,
        slug="sample-post",
        url="https://example.test/sample-post/",
        title="Studs and fighters",
        published_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        excerpt="A sample excerpt",
        content_html="<p>A sample post about football.</p>",
        content_text="A sample post about football.",
        categories=["Sport"],
        tags=["Football"],
        content_hash="fixed-content-hash",
    )


def test_hash_embeddings_are_deterministic_and_normalized():
    embedder = archive.HashEmbeddingBackend(32)

    first = embedder.embed(["studs and fighters"])[0]
    second = embedder.embed(["studs and fighters"])[0]

    assert first == second
    assert archive.cosine_similarity(first, second) == 1.0


def test_opening_archive_does_not_overwrite_embedding_metadata(tmp_path):
    db_path = tmp_path / "archive.sqlite3"
    original = archive.ArchiveStore(db_path, archive.HashEmbeddingBackend(8))
    original.close()

    reopened = archive.ArchiveStore(db_path, archive.HashEmbeddingBackend(16))
    try:
        assert reopened.meta_value("embed_provider") == "hash"
        assert reopened.meta_value("embed_model") == "feature-hash-8d"
        assert reopened.meta_value("embed_dim") == "8"
    finally:
        reopened.close()


def test_same_content_is_reembedded_when_embedding_model_changes(tmp_path):
    db_path = tmp_path / "archive.sqlite3"
    first = archive.ArchiveStore(db_path, archive.HashEmbeddingBackend(8))
    assert first.upsert_post(_post()) is True
    first.conn.commit()
    first.close()

    second = archive.ArchiveStore(db_path, archive.HashEmbeddingBackend(16))
    try:
        assert second.upsert_post(_post()) is True
        row = second.conn.execute(
            "SELECT embedding_model, embedding_dim FROM chunks WHERE post_id = 1"
        ).fetchone()
        assert row["embedding_model"] == "feature-hash-16d"
        assert row["embedding_dim"] == 16

        second.record_embedding_config()
        second.conn.commit()
        assert second.meta_value("embed_model") == "feature-hash-16d"
        assert second.meta_value("embed_dim") == "16"
    finally:
        second.close()


def test_env_file_values_are_applied_before_parser_defaults(tmp_path):
    env_file = tmp_path / ".env"
    db_path = tmp_path / "configured.sqlite3"
    env_file.write_text(
        "\n".join(
            [
                "NOENTHUDA_BASE_URL=https://notes.example.test/",
                f"NOENTHUDA_DB_PATH={db_path}",
                "NOENTHUDA_EMBED_DIM=64",
                "NOENTHUDA_REQUEST_TIMEOUT=12",
            ]
        ),
        encoding="utf-8",
    )
    names = (
        "NOENTHUDA_BASE_URL",
        "NOENTHUDA_API_BASE",
        "NOENTHUDA_DB_PATH",
        "NOENTHUDA_EMBED_PROVIDER",
        "NOENTHUDA_EMBED_DIM",
        "NOENTHUDA_EMBED_MODEL",
        "NOENTHUDA_REQUEST_TIMEOUT",
        "NOENTHUDA_USER_AGENT",
    )
    old_values = {
        name: getattr(archive, name)
        for name in (
            "NOENTHUDA_BASE_URL",
            "NOENTHUDA_API_BASE",
            "DEFAULT_DB_PATH",
            "DEFAULT_EMBED_PROVIDER",
            "DEFAULT_EMBED_DIM",
            "DEFAULT_OPENAI_MODEL",
            "DEFAULT_TIMEOUT",
            "DEFAULT_USER_AGENT",
        )
    }

    try:
        with patch.dict(os.environ, {"HERMES_ENV_FILE": str(env_file)}, clear=False):
            for name in names:
                os.environ.pop(name, None)
            archive.load_env()
            archive.refresh_runtime_config()

            parser = archive.build_parser()
            args = parser.parse_args(["stats"])
            assert archive.NOENTHUDA_BASE_URL == "https://notes.example.test"
            assert archive.NOENTHUDA_API_BASE == "https://notes.example.test/wp-json/wp/v2"
            assert archive.DEFAULT_DB_PATH == db_path
            assert archive.DEFAULT_EMBED_DIM == 64
            assert archive.DEFAULT_TIMEOUT == 12
            assert args.db == str(db_path)
    finally:
        for name, value in old_values.items():
            setattr(archive, name, value)
