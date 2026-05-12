"""arXiv 论文抓取模块"""
from __future__ import annotations
import datetime as dt
import time
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
    """从 arXiv 抓取符合条件的论文，返回字典列表。429 会自动退避重试"""
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

    # 加大延迟与重试，缓解 429
    client = arxiv.Client(page_size=50, delay_seconds=5, num_retries=5)

    last_err = None
    for attempt in range(3):
        try:
            papers = []
            for r in client.results(search):
                if r.published < cutoff:
                    continue
                papers.append({
                    "arxiv_id": r.entry_id.split("/")[-1],
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
        except Exception as e:
            last_err = e
            msg = str(e)
            wait = 30 * (attempt + 1)  # 30s, 60s, 90s
            logger.warning(f"抓取失败 (尝试 {attempt+1}/3): {msg[:120]}，{wait}s 后重试")
            if "429" in msg:
                time.sleep(wait)
            else:
                time.sleep(5)
    raise RuntimeError(f"arXiv 抓取多次失败: {last_err}")


if __name__ == "__main__":
    from utils import load_config
    cfg = load_config()
    ps = fetch_papers(cfg)
    for p in ps[:3]:
        print(p["published"], "-", p["title"])
