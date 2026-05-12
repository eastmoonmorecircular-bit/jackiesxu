"""方向分类：基于关键词规则（快速、零成本）"""
from typing import Dict, List


def classify(title: str, abstract: str, rules: Dict[str, List[str]]) -> List[str]:
    """返回命中的方向标签列表，可能命中多个；若无命中返回 ['其他']"""
    text = (title + " " + abstract).lower()
    hits = []
    for direction, kws in rules.items():
        for kw in kws:
            if kw.lower() in text:
                hits.append(direction)
                break
    return hits if hits else ["其他"]


def classify_paper(paper: dict, rules: Dict[str, List[str]]) -> dict:
    paper["directions"] = classify(paper["title"], paper["abstract"], rules)
    return paper
