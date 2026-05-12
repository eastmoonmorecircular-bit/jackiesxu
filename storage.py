"""存储层：本地 SQLite 与 Turso 云端 libSQL 自动切换

- 配置了 TURSO_DATABASE_URL（环境变量或 Streamlit Secrets）→ 用云端 Turso
- 否则 → 用本地 SQLite 文件
"""
from __future__ import annotations
import os
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
import datetime as dt

from utils import setup_logger

logger = setup_logger(__name__)

SCHEMA_STMTS = [
    """CREATE TABLE IF NOT EXISTS papers (
        arxiv_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        abstract TEXT,
        authors TEXT,
        published TEXT,
        updated TEXT,
        url TEXT,
        pdf_url TEXT,
        primary_category TEXT,
        categories TEXT,
        directions TEXT,
        summary TEXT,
        summary_raw TEXT,
        fetched_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_published ON papers(published)",
    "CREATE INDEX IF NOT EXISTS idx_fetched ON papers(fetched_at)",
]

COLS = ["arxiv_id", "title", "abstract", "authors", "published", "updated",
        "url", "pdf_url", "primary_category", "categories",
        "directions", "summary", "summary_raw", "fetched_at"]


def _get_secret(key: str) -> Optional[str]:
    """优先级：环境变量 > Streamlit Secrets"""
    v = os.getenv(key)
    if v:
        return v
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None


# =================== 后端实现 ===================

class _SqliteBackend:
    """本地 SQLite 文件后端"""
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as c:
            for s in SCHEMA_STMTS:
                c.execute(s)

    def execute(self, sql: str, args: tuple = ()):
        with self._conn() as c:
            c.execute(sql, args)

    def query(self, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
        with self._conn() as c:
            cur = c.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]


class _TursoBackend:
    """Turso 云端 libSQL 后端"""
    def __init__(self, url: str, auth_token: str):
        import libsql_client
        # libsql:// → 必须 https://
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        self._client_factory = lambda: libsql_client.create_client_sync(
            url=url, auth_token=auth_token
        )
        self._init_db()
        logger.info(f"使用 Turso 云数据库: {url[:40]}...")

    def _init_db(self):
        with self._client_factory() as c:
            for s in SCHEMA_STMTS:
                c.execute(s)

    def execute(self, sql: str, args: tuple = ()):
        with self._client_factory() as c:
            c.execute(sql, list(args))

    def query(self, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
        with self._client_factory() as c:
            rs = c.execute(sql, list(args))
            cols = rs.columns
            return [dict(zip(cols, row)) for row in rs.rows]


# =================== Storage 主类 ===================

class Storage:
    def __init__(self, db_path: str):
        turso_url = _get_secret("TURSO_DATABASE_URL")
        turso_token = _get_secret("TURSO_AUTH_TOKEN")
        if turso_url and turso_token:
            self.backend = _TursoBackend(turso_url, turso_token)
            self.is_remote = True
        else:
            self.backend = _SqliteBackend(db_path)
            self.is_remote = False

    # ---------- 写 ----------
    def exists(self, arxiv_id: str) -> bool:
        rows = self.backend.query("SELECT 1 FROM papers WHERE arxiv_id=?", (arxiv_id,))
        return len(rows) > 0

    def upsert(self, paper: dict):
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.backend.execute("""
            INSERT INTO papers (arxiv_id,title,abstract,authors,published,updated,
                                url,pdf_url,primary_category,categories,
                                directions,summary,summary_raw,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(arxiv_id) DO UPDATE SET
              title=excluded.title,
              abstract=excluded.abstract,
              directions=excluded.directions,
              summary=COALESCE(excluded.summary, papers.summary),
              summary_raw=COALESCE(excluded.summary_raw, papers.summary_raw),
              updated=excluded.updated
        """, (
            paper["arxiv_id"], paper["title"], paper.get("abstract", ""),
            paper.get("authors", ""), paper.get("published", ""),
            paper.get("updated", ""), paper.get("url", ""),
            paper.get("pdf_url", ""), paper.get("primary_category", ""),
            paper.get("categories", ""),
            json.dumps(paper.get("directions", []), ensure_ascii=False),
            json.dumps(paper["summary"], ensure_ascii=False) if paper.get("summary") else None,
            paper.get("summary_raw"),
            now,
        ))

    # ---------- 读 ----------
    def list_papers(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        directions: Optional[List[str]] = None,
        keyword: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Dict]:
        sql = "SELECT * FROM papers WHERE 1=1"
        args: list = []
        if date_from:
            sql += " AND published >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND published <= ?"
            args.append(date_to)
        if keyword:
            sql += " AND (title LIKE ? OR abstract LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        sql += " ORDER BY published DESC, arxiv_id DESC"

        rows = self.backend.query(sql, tuple(args))

        for r in rows:
            r["directions"] = json.loads(r["directions"]) if r.get("directions") else []
            r["summary"] = json.loads(r["summary"]) if r.get("summary") else None

        if directions:
            ds = set(directions)
            rows = [r for r in rows if ds & set(r["directions"])]
        if priority:
            rows = [r for r in rows
                    if r.get("summary") and r["summary"].get("reading_priority") == priority]
        return rows

    def all_dates(self) -> List[str]:
        rows = self.backend.query(
            "SELECT DISTINCT published FROM papers ORDER BY published DESC"
        )
        return [r["published"] for r in rows if r.get("published")]

    def stats_by_direction(self, date_from: Optional[str] = None) -> Dict[str, int]:
        papers = self.list_papers(date_from=date_from)
        stat: Dict[str, int] = {}
        for p in papers:
            for d in p["directions"] or ["其他"]:
                stat[d] = stat.get(d, 0) + 1
        return stat

    def papers_without_summary(self, limit: int = 30) -> List[Dict]:
        rows = self.backend.query(
            "SELECT * FROM papers WHERE summary IS NULL ORDER BY published DESC LIMIT ?",
            (limit,)
        )
        for r in rows:
            r["directions"] = json.loads(r["directions"]) if r.get("directions") else []
        return rows

    def update_summary(self, arxiv_id: str, summary: dict, summary_raw: str):
        self.backend.execute(
            "UPDATE papers SET summary=?, summary_raw=? WHERE arxiv_id=?",
            (json.dumps(summary, ensure_ascii=False) if summary else None,
             summary_raw, arxiv_id),
        )
