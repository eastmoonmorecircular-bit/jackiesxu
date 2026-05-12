"""SQLite 存储与去重"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import datetime as dt

from utils import setup_logger

logger = setup_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
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
    directions TEXT,        -- JSON 数组
    summary TEXT,           -- JSON 对象（LLM 解读）
    summary_raw TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_published ON papers(published);
CREATE INDEX IF NOT EXISTS idx_fetched ON papers(fetched_at);
"""


class Storage:
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
            c.executescript(SCHEMA)

    # ---------- 写 ----------
    def exists(self, arxiv_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM papers WHERE arxiv_id=?", (arxiv_id,))
            return cur.fetchone() is not None

    def upsert(self, paper: dict):
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as c:
            c.execute("""
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

        with self._conn() as c:
            rows = [dict(r) for r in c.execute(sql, args).fetchall()]

        # 解析 JSON 字段
        for r in rows:
            r["directions"] = json.loads(r["directions"]) if r["directions"] else []
            r["summary"] = json.loads(r["summary"]) if r["summary"] else None

        # 方向 / 优先级过滤（在 Python 端做，更灵活）
        if directions:
            ds = set(directions)
            rows = [r for r in rows if ds & set(r["directions"])]
        if priority:
            rows = [r for r in rows
                    if r.get("summary") and r["summary"].get("reading_priority") == priority]
        return rows

    def all_dates(self) -> List[str]:
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT published FROM papers ORDER BY published DESC").fetchall()
        return [r["published"] for r in rows if r["published"]]

    def stats_by_direction(self, date_from: Optional[str] = None) -> Dict[str, int]:
        papers = self.list_papers(date_from=date_from)
        stat: Dict[str, int] = {}
        for p in papers:
            for d in p["directions"] or ["其他"]:
                stat[d] = stat.get(d, 0) + 1
        return stat

    def papers_without_summary(self, limit: int = 30) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM papers WHERE summary IS NULL ORDER BY published DESC LIMIT ?",
                (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["directions"] = json.loads(d["directions"]) if d["directions"] else []
            out.append(d)
        return out

    def update_summary(self, arxiv_id: str, summary: dict, summary_raw: str):
        with self._conn() as c:
            c.execute(
                "UPDATE papers SET summary=?, summary_raw=? WHERE arxiv_id=?",
                (json.dumps(summary, ensure_ascii=False) if summary else None,
                 summary_raw, arxiv_id),
            )
