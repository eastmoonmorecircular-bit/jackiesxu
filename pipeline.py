"""主流程：抓取 -> 分类 -> 浅解读 -> 深度解读 -> PPT -> 入库"""
from __future__ import annotations
import time
from typing import Set, Optional

from utils import load_config, setup_logger
from fetcher import fetch_papers
from classifier import classify_paper
from summarizer import summarize
from storage import Storage

logger = setup_logger(__name__)


def _should_deep_summarize(paper: dict, allow_dirs: Optional[Set[str]]) -> bool:
    """根据方向决定该论文是否需要做深度解读"""
    if not allow_dirs:
        return True
    return bool(set(paper.get("directions") or []) & allow_dirs)


def run_once(skip_existing: bool = True):
    cfg = load_config()
    store = Storage(cfg["storage"]["db_path"])
    rules = cfg["directions"]
    llm_cfg = cfg["llm"]

    # ============ 1. 抓取 ============
    papers = fetch_papers(cfg)

    # ============ 2. 分类 + 入库 ============
    new_count = 0
    for p in papers:
        if skip_existing and store.exists(p["arxiv_id"]):
            continue
        classify_paper(p, rules)
        store.upsert(p)
        new_count += 1
    logger.info(f"新增 {new_count} 篇论文入库")

    if not (llm_cfg.get("enabled", True) and llm_cfg.get("api_key")):
        logger.info("LLM 未启用或缺失 api_key，跳过解读")
        return new_count

    # ============ 3. 浅解读（所有未解读） ============
    todo = store.papers_without_summary(limit=llm_cfg.get("max_summarize_per_run", 100))
    logger.info(f"准备浅解读 {len(todo)} 篇")
    for i, p in enumerate(todo, 1):
        logger.info(f"[浅解读 {i}/{len(todo)}] {p['title'][:60]}...")
        try:
            summarize(p, cfg)
            store.update_summary(p["arxiv_id"], p.get("summary"), p.get("summary_raw", ""))
        except Exception as e:
            logger.error(f"  失败: {e}")
        time.sleep(1)

    # ============ 4. 深度解读（按方向过滤） ============
    if not llm_cfg.get("auto_deep_summarize", False):
        logger.info("auto_deep_summarize=false，跳过深度解读")
        return new_count

    # 延迟导入，避免没装 PyMuPDF/python-pptx 时 pipeline 整体失败
    from deep_summarizer import deep_summarize
    auto_ppt = llm_cfg.get("auto_generate_ppt", False)
    if auto_ppt:
        from ppt_generator import generate_ppt

    allow_dirs = llm_cfg.get("deep_summarize_directions")
    allow_dirs_set = set(allow_dirs) if allow_dirs else None

    # 找出尚未深度解读的论文
    all_papers = store.list_papers()
    deep_todo = [p for p in all_papers
                 if not p.get("deep_summary")
                 and _should_deep_summarize(p, allow_dirs_set)]
    max_deep = llm_cfg.get("max_deep_summarize_per_run", 30)
    deep_todo = deep_todo[:max_deep]
    logger.info(f"准备深度解读 {len(deep_todo)} 篇 "
                f"（过滤方向: {allow_dirs_set or '全部'}）")

    for i, p in enumerate(deep_todo, 1):
        logger.info(f"[深度 {i}/{len(deep_todo)}] {p['title'][:60]}...")
        try:
            deep = deep_summarize(p, cfg)
            store.update_deep_summary(p["arxiv_id"], deep)
            # 自动生成 PPT
            if auto_ppt:
                p2 = store.get_paper(p["arxiv_id"])
                try:
                    fp = generate_ppt(p2)
                    logger.info(f"  PPT: {fp}")
                except Exception as e:
                    logger.error(f"  PPT 生成失败: {e}")
        except Exception as e:
            logger.error(f"  深度解读失败: {e}")
        time.sleep(2)

    return new_count


if __name__ == "__main__":
    n = run_once()
    print(f"完成，新增 {n} 篇")
