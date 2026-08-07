#!/usr/bin/env python3
"""Archive and search the Noenthuda / Pertinent Observations WordPress site.

The archive is stored in a local SQLite database under ~/.hermes/noenthuda_archive/.
It uses hybrid retrieval:
- offline feature-hash embeddings by default
- optional OpenAI embeddings if NOENTHUDA_EMBED_PROVIDER=openai and OPENAI_API_KEY is set
- FTS5 lexical fallback when available

Examples:
  python scripts/noenthuda_archive.py sync
  python scripts/noenthuda_archive.py search "studs and fighters"
  python scripts/noenthuda_archive.py stats
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode

HERMES_APP = Path(
    os.getenv("HERMES_APP_DIR", str(Path(__file__).resolve().parents[1]))
).expanduser()
if str(HERMES_APP) not in sys.path:
    sys.path.insert(0, str(HERMES_APP))

NOENTHUDA_BASE_URL = os.getenv("NOENTHUDA_BASE_URL", "https://www.noenthuda.com").rstrip("/")
NOENTHUDA_API_BASE = os.getenv("NOENTHUDA_API_BASE", f"{NOENTHUDA_BASE_URL}/wp-json/wp/v2")
DEFAULT_DB_PATH = Path(
    os.getenv(
        "NOENTHUDA_DB_PATH",
        str(Path.home() / ".hermes" / "noenthuda_archive" / "noenthuda.sqlite3"),
    )
).expanduser()
DEFAULT_EMBED_PROVIDER = os.getenv("NOENTHUDA_EMBED_PROVIDER", "hash").strip().lower()
DEFAULT_EMBED_DIM = int(os.getenv("NOENTHUDA_EMBED_DIM", "1536"))
DEFAULT_OPENAI_MODEL = os.getenv("NOENTHUDA_EMBED_MODEL", "text-embedding-3-small")
DEFAULT_TIMEOUT = int(float(os.getenv("NOENTHUDA_REQUEST_TIMEOUT", "30")))
DEFAULT_USER_AGENT = os.getenv(
    "NOENTHUDA_USER_AGENT",
    "HermesNoenthudaArchive/1.0 (+https://github.com/NousResearch/Hermes-Agent)",
)

WORD_RE = re.compile(r"[a-z0-9']+")
WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")


def load_env() -> None:
    env_path = Path(os.getenv("HERMES_ENV_FILE", str(Path.home() / ".hermes" / ".env")))
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def refresh_runtime_config() -> None:
    """Refresh module configuration after loading the Hermes env file."""
    global NOENTHUDA_BASE_URL
    global NOENTHUDA_API_BASE
    global DEFAULT_DB_PATH
    global DEFAULT_EMBED_PROVIDER
    global DEFAULT_EMBED_DIM
    global DEFAULT_OPENAI_MODEL
    global DEFAULT_TIMEOUT
    global DEFAULT_USER_AGENT

    NOENTHUDA_BASE_URL = os.getenv("NOENTHUDA_BASE_URL", "https://www.noenthuda.com").rstrip("/")
    NOENTHUDA_API_BASE = os.getenv(
        "NOENTHUDA_API_BASE", f"{NOENTHUDA_BASE_URL}/wp-json/wp/v2"
    ).rstrip("/")
    DEFAULT_DB_PATH = Path(
        os.getenv(
            "NOENTHUDA_DB_PATH",
            str(Path.home() / ".hermes" / "noenthuda_archive" / "noenthuda.sqlite3"),
        )
    ).expanduser()
    DEFAULT_EMBED_PROVIDER = os.getenv("NOENTHUDA_EMBED_PROVIDER", "hash").strip().lower()
    DEFAULT_EMBED_DIM = int(os.getenv("NOENTHUDA_EMBED_DIM", "1536"))
    DEFAULT_OPENAI_MODEL = os.getenv("NOENTHUDA_EMBED_MODEL", "text-embedding-3-small")
    DEFAULT_TIMEOUT = int(float(os.getenv("NOENTHUDA_REQUEST_TIMEOUT", "30")))
    DEFAULT_USER_AGENT = os.getenv(
        "NOENTHUDA_USER_AGENT",
        "HermesNoenthudaArchive/1.0 (+https://github.com/NousResearch/Hermes-Agent)",
    )


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif tag in {"p", "br", "div", "li", "section", "article", "blockquote", "tr"}:
            self.parts.append("\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in {"p", "li", "div", "section", "article", "blockquote", "tr"}:
            self.parts.append("\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data:
            self.parts.append(data)

    def text(self) -> str:
        return html.unescape("".join(self.parts))


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    parser = HTMLTextExtractor()
    parser.feed(raw)
    parser.close()
    text = parser.text()
    text = TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", (text or "").strip())


def listify(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def chunk_text(text: str, *, max_words: int = 220, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        out.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(end - overlap, start + 1)
    return out


def utc_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return dt.astimezone(timezone.utc).date().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if not na or not nb:
        return 0.0
    return dot / math.sqrt(na * nb)


def _parse_headers(raw: str) -> dict[str, str]:
    blocks = [block for block in re.split(r"\r?\n\r?\n", raw.strip()) if block.strip()]
    if not blocks:
        return {}
    headers: dict[str, str] = {}
    for line in blocks[-1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def curl_json(url: str, params: dict[str, Any] | None = None) -> tuple[dict[str, str], Any]:
    full_url = url
    if params:
        full_url = f"{url}?{urlencode(params, doseq=True)}"
    with tempfile.TemporaryDirectory(prefix="noenthuda-curl-") as tmpdir:
        tmp = Path(tmpdir)
        header_path = tmp / "headers.txt"
        body_path = tmp / "body.json"
        cmd = [
            "curl",
            "-sS",
            "-L",
            "--http1.1",
            "--compressed",
            "-A",
            DEFAULT_USER_AGENT,
            "--max-time",
            str(DEFAULT_TIMEOUT),
            "-D",
            str(header_path),
            "-o",
            str(body_path),
            full_url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "curl failed").strip())
        headers = _parse_headers(header_path.read_text(encoding="utf-8", errors="replace") if header_path.exists() else "")
        body = body_path.read_text(encoding="utf-8", errors="replace") if body_path.exists() else ""
    return headers, json.loads(body) if body.strip() else []


@dataclass(slots=True)
class Post:
    post_id: int
    slug: str
    url: str
    title: str
    published_at: str
    updated_at: str
    excerpt: str
    content_html: str
    content_text: str
    categories: list[str]
    tags: list[str]
    content_hash: str


class EmbeddingBackend:
    name = "hash"
    model = "feature-hash"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddingBackend(EmbeddingBackend):
    def __init__(self, dim: int | None = None) -> None:
        self.name = "hash"
        self.dim = DEFAULT_EMBED_DIM if dim is None else dim
        if self.dim <= 0:
            raise ValueError("embedding dimension must be positive")
        self.model = f"feature-hash-{self.dim}d"

    def _vectorize(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = WORD_RE.findall(text.lower())
        if not tokens:
            return vec
        prev = None
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            idx = int.from_bytes(digest[:8], "big") % self.dim
            sign = -1.0 if digest[8] & 1 else 1.0
            vec[idx] += sign * (1.0 + min(len(token), 12) / 12.0)
            if prev is not None:
                bigram = f"{prev}_{token}".encode("utf-8")
                bdigest = hashlib.blake2b(bigram, digest_size=16).digest()
                bidx = int.from_bytes(bdigest[:8], "big") % self.dim
                bsign = -1.0 if bdigest[8] & 1 else 1.0
                vec[bidx] += bsign * 0.5
            prev = token
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vectorize(text) for text in texts]


class OpenAIEmbeddingBackend(EmbeddingBackend):
    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self.client = OpenAI()
        self.name = "openai"
        self.model = model or DEFAULT_OPENAI_MODEL

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=list(texts))
        return [list(item.embedding) for item in response.data]


def build_embedder() -> EmbeddingBackend:
    if DEFAULT_EMBED_PROVIDER == "openai":
        try:
            return OpenAIEmbeddingBackend(DEFAULT_OPENAI_MODEL)
        except Exception as exc:
            print(f"[warn] OpenAI embeddings unavailable, falling back to hash: {exc}", file=sys.stderr)
    return HashEmbeddingBackend(DEFAULT_EMBED_DIM)


class ArchiveStore:
    def __init__(self, path: Path, embedder: EmbeddingBackend) -> None:
        self.path = path
        self.embedder = embedder
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.has_fts = False
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                excerpt TEXT NOT NULL,
                content_html TEXT NOT NULL,
                content_text TEXT NOT NULL,
                categories_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL,
                embedding_blob BLOB NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(post_id, chunk_index)
            );
            """
        )
        try:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(
                    post_title,
                    chunk_text,
                    post_id UNINDEXED,
                    chunk_id UNINDEXED,
                    tokenize='unicode61 remove_diacritics 2'
                )
                """
            )
            self.has_fts = True
        except sqlite3.OperationalError:
            self.has_fts = False

        self._set_meta_if_missing("embed_provider", self.embedder.name)
        self._set_meta_if_missing("embed_model", self.embedder.model)
        self._set_meta_if_missing(
            "embed_dim",
            str(self.embedder.dim if isinstance(self.embedder, HashEmbeddingBackend) else 0),
        )
        self.conn.commit()

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _set_meta_if_missing(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
            (key, value),
        )

    def record_embedding_config(self) -> None:
        """Record the embedding configuration after a successful archive sync."""
        self._set_meta("embed_provider", self.embedder.name)
        self._set_meta("embed_model", self.embedder.model)
        self._set_meta(
            "embed_dim",
            str(self.embedder.dim if isinstance(self.embedder, HashEmbeddingBackend) else 0),
        )

    def meta_value(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def count_posts(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"])

    def count_chunks(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"])

    def fetch_post(self, post_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()

    def upsert_post(self, post: Post) -> bool:
        existing = self.fetch_post(post.post_id)
        embedding_matches = (
            self.meta_value("embed_provider") == self.embedder.name
            and self.meta_value("embed_model") == self.embedder.model
        )
        if existing and existing["content_hash"] == post.content_hash and embedding_matches:
            return False

        self.conn.execute(
            """
            INSERT INTO posts (
                post_id, slug, url, title, published_at, updated_at, excerpt,
                content_html, content_text, categories_json, tags_json,
                content_hash, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                slug = excluded.slug,
                url = excluded.url,
                title = excluded.title,
                published_at = excluded.published_at,
                updated_at = excluded.updated_at,
                excerpt = excluded.excerpt,
                content_html = excluded.content_html,
                content_text = excluded.content_text,
                categories_json = excluded.categories_json,
                tags_json = excluded.tags_json,
                content_hash = excluded.content_hash,
                synced_at = excluded.synced_at
            """,
            (
                post.post_id,
                post.slug,
                post.url,
                post.title,
                post.published_at,
                post.updated_at,
                post.excerpt,
                post.content_html,
                post.content_text,
                json.dumps(post.categories, ensure_ascii=False),
                json.dumps(post.tags, ensure_ascii=False),
                post.content_hash,
                now_iso(),
            ),
        )
        self.conn.execute("DELETE FROM chunks WHERE post_id = ?", (post.post_id,))
        if self.has_fts:
            self.conn.execute("DELETE FROM chunks_fts WHERE post_id = ?", (post.post_id,))

        pieces = chunk_text(f"{post.title}\n\n{post.excerpt}\n\n{post.content_text}")
        embeds = self.embedder.embed(pieces)
        for idx, (piece, emb) in enumerate(zip(pieces, embeds, strict=True)):
            blob = struct.pack(f"<{len(emb)}f", *emb)
            cur = self.conn.execute(
                """
                INSERT INTO chunks (
                    post_id, chunk_index, chunk_text, embedding_model,
                    embedding_dim, embedding_blob, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (post.post_id, idx, piece, self.embedder.model, len(emb), blob, post.content_hash, now_iso()),
            )
            if self.has_fts:
                self.conn.execute(
                    "INSERT INTO chunks_fts(rowid, post_title, chunk_text, post_id, chunk_id) VALUES (?, ?, ?, ?, ?)",
                    (cur.lastrowid, post.title, piece, post.post_id, cur.lastrowid),
                )
        return True

    def delete_missing_posts(self, keep_ids: set[int]) -> int:
        rows = self.conn.execute("SELECT post_id FROM posts").fetchall()
        delete_ids = [int(row["post_id"]) for row in rows if int(row["post_id"]) not in keep_ids]
        for post_id in delete_ids:
            self.conn.execute("DELETE FROM posts WHERE post_id = ?", (post_id,))
            self.conn.execute("DELETE FROM chunks WHERE post_id = ?", (post_id,))
            if self.has_fts:
                self.conn.execute("DELETE FROM chunks_fts WHERE post_id = ?", (post_id,))
        return len(delete_ids)

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        qvec = self.embedder.embed([query])[0]
        if not any(qvec):
            return []

        tokens = [t for t in WORD_RE.findall(query.lower()) if len(t) > 1]
        fts_hits: set[int] = set()
        if self.has_fts and tokens:
            fts_query = " AND ".join(tokens[:8])
            try:
                rows = self.conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 300", (fts_query,)).fetchall()
                fts_hits = {int(row["rowid"]) for row in rows}
            except sqlite3.OperationalError:
                fts_hits = set()

        rows = self.conn.execute(
            """
            SELECT
                c.chunk_id,
                c.post_id,
                c.chunk_index,
                c.chunk_text,
                c.embedding_blob,
                c.embedding_dim,
                p.title,
                p.url,
                p.published_at,
                p.excerpt,
                p.categories_json,
                p.tags_json
            FROM chunks c
            JOIN posts p ON p.post_id = c.post_id
            """
        ).fetchall()

        best: dict[int, dict[str, Any]] = {}
        for row in rows:
            emb = list(struct.unpack(f"<{row['embedding_dim']}f", row["embedding_blob"]))
            score = cosine_similarity(qvec, emb)
            if int(row["chunk_id"]) in fts_hits:
                score += 0.15
            post_id = int(row["post_id"])
            current = best.get(post_id)
            if current is None or score > float(current["score"]):
                best[post_id] = {
                    "score": score,
                    "chunk_id": int(row["chunk_id"]),
                    "chunk_index": int(row["chunk_index"]),
                    "post_id": post_id,
                    "title": row["title"],
                    "url": row["url"],
                    "published_at": row["published_at"],
                    "excerpt": row["excerpt"],
                    "categories": listify(json.loads(row["categories_json"])),
                    "tags": listify(json.loads(row["tags_json"])),
                    "chunk_text": row["chunk_text"],
                }
        return sorted(best.values(), key=lambda item: float(item["score"]), reverse=True)[:top_k]


def fetch_taxonomy_map(taxonomy: str) -> dict[int, str]:
    mapping: dict[int, str] = {}
    page = 1
    while True:
        headers, items = curl_json(
            f"{NOENTHUDA_API_BASE}/{taxonomy}",
            {"per_page": 100, "page": page, "_fields": "id,name,slug"},
        )
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                mapping[int(item["id"])] = str(item.get("name") or item.get("slug") or item["id"])
            except (KeyError, TypeError, ValueError):
                continue
        total_pages = int(headers.get("x-wp-totalpages", page))
        if page >= total_pages:
            break
        page += 1
    return mapping


def fetch_all_posts() -> list[Post]:
    categories = fetch_taxonomy_map("categories")
    tags = fetch_taxonomy_map("tags")
    posts: list[Post] = []
    page = 1
    seen: set[int] = set()
    while True:
        headers, items = curl_json(
            f"{NOENTHUDA_API_BASE}/posts",
            {
                "per_page": 100,
                "page": page,
                "orderby": "date",
                "order": "asc",
                "_fields": "id,slug,link,date,modified,title,excerpt,content,categories,tags",
            },
        )
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            post_id = int(item["id"])
            if post_id in seen:
                continue
            seen.add(post_id)
            title = normalize_text(strip_html(item.get("title", {}).get("rendered", "")))
            excerpt = normalize_text(strip_html(item.get("excerpt", {}).get("rendered", "")))
            content_html = str(item.get("content", {}).get("rendered", ""))
            content_text = normalize_text(strip_html(content_html))
            published_at = str(item.get("date") or "")
            updated_at = str(item.get("modified") or published_at)
            category_names = [categories.get(int(cid), str(cid)) for cid in item.get("categories", [])]
            tag_names = [tags.get(int(tid), str(tid)) for tid in item.get("tags", [])]
            content_hash = hashlib.sha256(
                json.dumps(
                    {
                        "title": title,
                        "excerpt": excerpt,
                        "content_text": content_text,
                        "categories": category_names,
                        "tags": tag_names,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            posts.append(
                Post(
                    post_id=post_id,
                    slug=str(item.get("slug") or post_id),
                    url=str(item.get("link") or f"{NOENTHUDA_BASE_URL}/{item.get('slug') or post_id}/"),
                    title=title,
                    published_at=published_at,
                    updated_at=updated_at,
                    excerpt=excerpt,
                    content_html=content_html,
                    content_text=content_text,
                    categories=category_names,
                    tags=tag_names,
                    content_hash=content_hash,
                )
            )
        total_pages = int(headers.get("x-wp-totalpages", page))
        if page >= total_pages:
            break
        page += 1
    return posts


def highlight(text: str, query: str) -> str:
    terms = [re.escape(tok) for tok in WORD_RE.findall(query.lower()) if len(tok) > 1]
    if not terms:
        return text
    pattern = re.compile(r"(" + "|".join(terms) + r")", re.IGNORECASE)
    return pattern.sub(lambda m: f"**{m.group(0)}**", text)


def render_result(item: dict[str, Any], query: str) -> str:
    snippet = str(item["chunk_text"])
    if len(snippet) > 360:
        snippet = snippet[:360].rstrip() + "…"
    snippet = highlight(snippet, query)
    parts = [
        f"- {item['title']}  ({utc_date(str(item['published_at']))})",
        f"  score: {float(item['score']):.3f}",
        f"  url: {item['url']}",
        f"  snippet: {snippet}",
    ]
    if item.get("categories"):
        parts.append(f"  categories: {', '.join(listify(item['categories']))}")
    if item.get("tags"):
        parts.append(f"  tags: {', '.join(listify(item['tags']))}")
    return "\n".join(parts)


def load_store(embedder: EmbeddingBackend) -> ArchiveStore:
    return ArchiveStore(DEFAULT_DB_PATH, embedder)


def cmd_sync(args: argparse.Namespace) -> int:
    embedder = build_embedder()
    store = load_store(embedder)
    try:
        posts = fetch_all_posts()
        if not posts:
            print("No posts found.")
            return 1
        changed = 0
        for post in posts:
            if store.upsert_post(post):
                changed += 1
        removed = store.delete_missing_posts({p.post_id for p in posts}) if args.prune else 0
        store.record_embedding_config()
        store.conn.commit()
        print(
            f"Synced Noenthuda archive\n"
            f"- source: {NOENTHUDA_BASE_URL}\n"
            f"- posts fetched: {len(posts)}\n"
            f"- posts changed: {changed}\n"
            f"- posts removed: {removed}\n"
            f"- total posts in db: {store.count_posts()}\n"
            f"- total chunks in db: {store.count_chunks()}\n"
            f"- db: {DEFAULT_DB_PATH}\n"
            f"- embeddings: {embedder.name} ({embedder.model})"
        )
        return 0
    finally:
        store.close()


def cmd_search(args: argparse.Namespace) -> int:
    if not DEFAULT_DB_PATH.exists():
        print(f"Archive database not found: {DEFAULT_DB_PATH}")
        print("Run `python scripts/noenthuda_archive.py sync` first.")
        return 1
    embedder = build_embedder()
    store = load_store(embedder)
    try:
        expected_provider = store.meta_value("embed_provider")
        expected_model = store.meta_value("embed_model")
        if expected_provider and expected_provider != embedder.name:
            print(
                f"[warn] archive was built with embed_provider={expected_provider} but current provider is {embedder.name}; results may be less relevant.",
                file=sys.stderr,
            )
        if expected_model and expected_model != embedder.model:
            print(
                f"[warn] archive was built with embed_model={expected_model} but current model is {embedder.model}; results may be less relevant.",
                file=sys.stderr,
            )
        results = store.search(args.query, top_k=args.top_k)
        if not results:
            print("No matches found.")
            return 0
        print(f"Top {len(results)} matches for: {args.query!r}\n")
        for item in results:
            print(render_result(item, args.query))
            print()
        return 0
    finally:
        store.close()


def cmd_stats(args: argparse.Namespace) -> int:
    if not DEFAULT_DB_PATH.exists():
        print(f"Archive database not found: {DEFAULT_DB_PATH}")
        return 1
    embedder = build_embedder()
    store = load_store(embedder)
    try:
        print(f"database: {DEFAULT_DB_PATH}")
        print(f"posts: {store.count_posts()}")
        print(f"chunks: {store.count_chunks()}")
        print(f"fts: {'yes' if store.has_fts else 'no'}")
        print(f"embed_provider: {store.meta_value('embed_provider')}")
        print(f"embed_model: {store.meta_value('embed_model')}")
        return 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path (default: ~/.hermes/noenthuda_archive/noenthuda.sqlite3)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Fetch and archive all posts from noenthuda.com")
    sync.add_argument("--prune", action="store_true", help="Remove posts that disappeared upstream")
    sync.set_defaults(func=cmd_sync)

    search = sub.add_parser("search", help="Hybrid semantic search over archived posts")
    search.add_argument("query", help="Search query")
    search.add_argument("--top-k", type=int, default=8, help="Number of results to show")
    search.set_defaults(func=cmd_search)

    stats = sub.add_parser("stats", help="Show archive stats")
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_env()
    refresh_runtime_config()
    parser = build_parser()
    args = parser.parse_args(argv)
    global DEFAULT_DB_PATH
    DEFAULT_DB_PATH = Path(args.db).expanduser()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
