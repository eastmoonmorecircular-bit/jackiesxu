"""LLM 论文解读模块（兼容 OpenAI / DeepSeek 等 OpenAI 协议）"""
from __future__ import annotations
import json
import re
from typing import Dict, Optional
import requests

from utils import setup_logger

logger = setup_logger(__name__)

PROMPT_TEMPLATE = """你是推荐系统领域的资深研究员，请用中文严谨而精炼地解读以下 arXiv 论文。

【标题】{title}
【摘要】{abstract}

请严格输出 JSON（不要带 markdown 代码块标记），字段如下：
{{
  "problem": "本文解决什么问题（1-2句）",
  "method": "核心方法概述（3-5句，写清关键模块、建模思路）",
  "innovation": ["创新点1", "创新点2", "创新点3"],
  "experiment": "实验数据集与基线（一句话）",
  "value_score": 1-5的整数，评估工业落地价值,
  "reading_priority": "高/中/低",
  "tags": ["细分关键词标签1", "标签2"]
}}
"""


def _call_llm(cfg: dict, prompt: str) -> Optional[str]:
    llm_cfg = cfg["llm"]
    api_key = llm_cfg.get("api_key", "").strip()
    if not api_key:
        logger.warning("LLM api_key 为空，跳过解读")
        return None

    url = f"{llm_cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": llm_cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": llm_cfg.get("temperature", 0.3),
        "max_tokens": llm_cfg.get("max_tokens", 1200),
        "stream": False,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def _parse_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    # 去除 ```json ... ``` 包裹
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    # 提取首个 { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    raw = m.group(0)
    # 第一次尝试
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 容错修复：常见错误是字符串内有未转义的换行/引号、或缺少逗号
    fixed = raw
    # 1) 去掉行尾多余逗号 ,}  ,]
    fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
    # 2) 把中文引号替换为英文引号
    fixed = fixed.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # 3) 把字符串值内的裸换行替换为空格
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}")
        # 最后兜底：保留原始文本到一个 problem 字段
        return {
            "problem": raw[:300],
            "method": "（LLM 输出格式异常，已保留原始文本）",
            "innovation": [],
            "experiment": "",
            "value_score": 3,
            "reading_priority": "中",
            "tags": [],
            "_parse_error": True,
        }


def summarize(paper: dict, cfg: dict) -> dict:
    """对单篇论文调用 LLM 解读，结果写入 paper['summary']"""
    if not cfg["llm"].get("enabled", True):
        return paper
    prompt = PROMPT_TEMPLATE.format(title=paper["title"], abstract=paper["abstract"])
    raw = _call_llm(cfg, prompt)
    parsed = _parse_json(raw) if raw else None
    if parsed:
        paper["summary"] = parsed
        paper["summary_raw"] = raw
    else:
        paper["summary"] = None
        paper["summary_raw"] = raw or ""
    return paper
