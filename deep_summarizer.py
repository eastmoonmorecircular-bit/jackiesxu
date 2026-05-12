"""分章节深度解读：将一篇论文拆成 7 个解读维度调用 LLM，合成 deep_summary"""
from __future__ import annotations
import json
import re
import time
from typing import Dict, Optional

from utils import setup_logger
from summarizer import _call_llm, _parse_json
from pdf_reader import parse_paper

logger = setup_logger(__name__)

MAX_CHARS_PER_CALL = 12000  # 单次塞给 LLM 的最大字符（约 4-5K token）


def _trim(text: str, n: int = MAX_CHARS_PER_CALL) -> str:
    if len(text) <= n:
        return text
    # 保留首尾，丢掉中间
    head = int(n * 0.6)
    tail = n - head
    return text[:head] + "\n...[省略]...\n" + text[-tail:]


# 七个解读维度的 Prompt 模板（输入：标题 + 相关章节文本；输出：结构化 JSON）

PROMPTS = {
    "motivation": """你是推荐系统资深研究员。基于论文标题与 Introduction 内容，用中文深入解读 Motivation。
【标题】{title}
【Introduction 节选】
{text}

输出 JSON（严格格式，不要 markdown）：
{{
  "real_world_pain": "现实世界中存在什么痛点（2-4 句，要具体）",
  "existing_limitations": ["现有方法的不足1（具体到哪类方法）", "不足2", "不足3"],
  "this_paper_angle": "本文从什么独特角度切入解决",
  "why_it_matters": "为什么这个工作重要（学术 / 工业 / 应用价值）"
}}""",

    "problem": """你是推荐系统资深研究员。基于论文中"问题定义/Preliminaries"部分，用中文清晰说明本文要解决的具体问题。
【标题】{title}
【相关内容】
{text}

输出 JSON：
{{
  "task_type": "任务类型（如：序列推荐 / CTR 预估 / 召回）",
  "formal_definition": "形式化定义（用通俗语言描述输入输出，可含简化公式）",
  "input": "输入是什么（数据形式）",
  "output": "输出是什么（预测目标）",
  "key_constraints": ["关键假设/约束1", "约束2"]
}}""",

    "method": """你是推荐系统资深研究员。基于论文 Method/Approach 章节，用中文详细拆解本文方法。
【标题】{title}
【Method 章节】
{text}

输出 JSON：
{{
  "overview": "整体框架概述（3-5 句，要看完能想象出系统结构）",
  "key_modules": [
    {{"name": "模块名", "role": "做什么", "how": "如何实现（含关键技术/网络结构）", "formula": "如有关键公式则用文字描述，无则空字符串"}}
  ],
  "training_strategy": "训练目标与损失函数（含正则、采样等技巧）",
  "inference_pipeline": "推理流程（在线服务时如何工作）",
  "key_insights": ["设计的关键洞见1", "洞见2", "洞见3"]
}}""",

    "experiment": """你是推荐系统资深研究员。基于论文实验章节，提炼实验设置与主结果。
【标题】{title}
【实验内容】
{text}

输出 JSON：
{{
  "datasets": [{{"name": "数据集名", "scale": "规模", "domain": "领域"}}],
  "metrics": ["评价指标1（如 HR@10）", "指标2"],
  "baselines": [{{"name": "基线名", "type": "类别（如GNN/Transformer/经典）"}}],
  "main_results": "主实验关键发现（3-5 句，含具体数字提升如 +5.2%）",
  "win_or_lose": "本文方法在哪些场景胜出，哪些场景表现一般"
}}""",

    "ablation": """你是推荐系统资深研究员。基于论文 Ablation 与分析章节，逐项剖析消融实验。
【标题】{title}
【消融与分析内容】
{text}

输出 JSON：
{{
  "ablations": [
    {{"removed_component": "去掉的模块", "impact": "性能变化（具体指标和数字）", "interpretation": "说明该模块为什么重要"}}
  ],
  "hyperparameter_analysis": "超参敏感性分析（学习率/embedding维度/层数等）",
  "case_study": "如有 Case Study/可视化，简述发现",
  "robustness": "对噪声/稀疏/冷启动等场景的鲁棒性"
}}""",

    "comparison": """你是推荐系统资深研究员。请对比本文方法与当前主流 SOTA 方法，给出深度评价。
【标题】{title}
【相关上下文（含 Related Work / 实验对比）】
{text}

输出 JSON：
{{
  "vs_sota": [
    {{"competitor": "对比方法名", "advantage": "本文优势", "disadvantage": "本文相对劣势/未解决"}}
  ],
  "complexity_compare": "时间/空间复杂度与 SOTA 对比",
  "engineering_friendliness": "工程实现难度与可扩展性",
  "industry_value": "工业落地价值评估（数据需求/服务时延/迭代成本）"
}}""",

    "limitation": """你是推荐系统资深研究员。基于全文，提炼本文局限与未来方向。
【标题】{title}
【相关内容】
{text}

输出 JSON：
{{
  "limitations": ["局限1（具体）", "局限2", "局限3"],
  "future_directions": ["可拓展方向1", "方向2"],
  "open_questions": ["仍待回答的开放问题1", "问题2"],
  "reading_advice": "给读者的阅读建议（应该重点看哪几节、跳过哪些）"
}}""",
}


def _pick_text_for(section_key: str, sections: Dict[str, str]) -> str:
    """为不同解读维度挑选合适的章节文本"""
    s = sections
    full = "\n".join(s.values()) if "body" in s and len(s) == 1 else None

    if section_key == "motivation":
        return s.get("introduction") or s.get("abstract") or full or ""
    if section_key == "problem":
        return s.get("preliminary") or s.get("introduction") or s.get("abstract") or full or ""
    if section_key == "method":
        return s.get("method") or full or ""
    if section_key == "experiment":
        return s.get("experiment") or s.get("ablation") or full or ""
    if section_key == "ablation":
        return s.get("ablation") or s.get("experiment") or s.get("discussion") or ""
    if section_key == "comparison":
        return (s.get("related_work", "") + "\n\n" + s.get("experiment", "")) or full or ""
    if section_key == "limitation":
        return s.get("limitation") or s.get("conclusion") or s.get("discussion") or ""
    return ""


def deep_summarize(paper: dict, cfg: dict, sections_to_run=None) -> Dict:
    """对一篇论文做完整深度解读，返回 deep_summary dict"""
    if not cfg["llm"].get("enabled", True) or not cfg["llm"].get("api_key"):
        raise RuntimeError("LLM 未启用或缺失 api_key")

    arxiv_id = paper["arxiv_id"]
    title = paper["title"]

    # 1. 解析 PDF
    logger.info(f"[深度解读] {title[:60]}...")
    info = parse_paper(arxiv_id, paper.get("pdf_url"))
    sections = info["sections"]
    logger.info(f"  章节: {list(sections.keys())}")

    # 2. 分维度调用 LLM
    sections_to_run = sections_to_run or list(PROMPTS.keys())
    deep: Dict[str, dict] = {}
    for key in sections_to_run:
        text = _pick_text_for(key, sections)
        if not text.strip():
            logger.warning(f"  跳过 {key}（无内容）")
            deep[key] = None
            continue
        prompt = PROMPTS[key].format(title=title, text=_trim(text))
        logger.info(f"  调用 LLM: {key} ...")
        raw = _call_llm(cfg, prompt)
        parsed = _parse_json(raw) if raw else None
        deep[key] = parsed or {"_raw": raw, "_parse_failed": True}
        time.sleep(1)

    # 3. 附加元信息
    deep["_meta"] = {
        "image_paths": info["image_paths"],
        "pdf_path": info["pdf_path"],
        "full_text_len": info["full_text_len"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return deep


if __name__ == "__main__":
    from utils import load_config
    cfg = load_config()
    paper = {
        "arxiv_id": "2310.06770",
        "title": "Test Paper",
        "pdf_url": None,
    }
    r = deep_summarize(paper, cfg)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
