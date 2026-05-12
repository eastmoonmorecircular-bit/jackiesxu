"""主流程：抓取 -> 分类 -> 解读 -> 入库"""
from __future__ import annotations
import time
from utils import load_config, setup_logger
from fetcher import fetch_papers
from classifier import classify_paper
from summarizer import summarize
from storage import Storage

logger = setup_logger(__name__)


def run_once(skip_existing: bool = True):
    cfg = load_config()
    store = Storage(cfg["storage"]["db_path"])
    rules = cfg["directions"]

    # 1. 抓取
    papers = fetch_papers(cfg)

    # 2. 分类 + 入库（先不解读，保证基础数据落库）
    new_count = 0
    for p in papers:
        if skip_existing and store.exists(p["arxiv_id"]):
            continue
        classify_paper(p, rules)
        store.upsert(p)
        new_count += 1
    logger.info(f"新增 {new_count} 篇论文入库")

    # 3. LLM 解读（只处理没有 summary 的）
    if cfg["llm"].get("enabled", True) and cfg["llm"].get("api_key"):
        todo = store.papers_without_summary(limit=cfg["llm"].get("max_summarize_per_run", 30))
        logger.info(f"准备解读 {len(todo)} 篇")
        for i, p in enumerate(todo, 1):
            logger.info(f"[{i}/{len(todo)}] {p['title'][:60]}...")
            summarize(p, cfg)
            store.update_summary(p["arxiv_id"], p.get("summary"), p.get("summary_raw", ""))
            time.sleep(1)  # 简单限速
    else:
        logger.info("LLM 解读未启用或未配置 api_key，跳过")

    return new_count


if __name__ == "__main__":
    n = run_once()
    print(f"完成，新增 {n} 篇")
