"""arXiv 论文抓取模块"""
from __future__ import annotations
import datetime as dt
from typing import List, Dict
import arxiv

from utils import setup_logger

logger = setup_logger(__name__)


def _build_query(categories: List[str], keywords: List[str]) -> str:
    cat_q = " OR ".join(f"cat:{c}" for c in categories)
    if keywords:
        # arXiv 字段语法：ti=title, abs=abstract，all=全文
        kw_q = " OR ".join(f'all:"{kw}"' for kw in keywords)
        return f"({cat_q}) AND ({kw_q})"
    return cat_q


def fetch_papers(cfg: dict) -> List[Dict]:
    """从 arXiv 抓取符合条件的论文，返回字典列表"""
    a_cfg = cfg["arxiv"]
    query = _build_query(a_cfg["categories"], a_cfg.get("keywords", []))
    logger.info(f"arXiv query: {query}")

    search = arxiv.Search(
        query=query,
        max_results=a_cfg.get("max_results", 50),
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    days_back = a_cfg.get("days_back", 2)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)

    client = arxiv.Client(page_size=50, delay_seconds=3, num_retries=3)
    papers = []
    for r in client.results(search):
        if r.published < cutoff:
            continue
        papers.append({
            "arxiv_id": r.entry_id.split("/")[-1],   # 例 2405.12345v1
            "title": r.title.strip().replace("\n", " "),
            "abstract": r.summary.strip().replace("\n", " "),
            "authors": ", ".join(a.name for a in r.authors),
            "published": r.published.strftime("%Y-%m-%d"),
            "updated": r.updated.strftime("%Y-%m-%d"),
            "url": r.entry_id,
            "pdf_url": r.pdf_url,
            "primary_category": r.primary_category,
            "categories": ",".join(r.categories),
        })
    logger.info(f"Fetched {len(papers)} papers (after date filter)")
    return papers


if __name__ == "__main__":
    from utils import load_config
    cfg = load_config()
    ps = fetch_papers(cfg)
    for p in ps[:3]:
        print(p["published"], "-", p["title"])
