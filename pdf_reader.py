"""PDF 下载、全文提取、章节切分、关键图提取"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
import urllib.request

import fitz  # PyMuPDF

from utils import setup_logger

logger = setup_logger(__name__)

CACHE_DIR = Path("data/pdf_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = Path("data/images")
IMG_DIR.mkdir(parents=True, exist_ok=True)


# ==================== 下载 ====================

def download_pdf(arxiv_id: str, pdf_url: str = None) -> Path:
    """下载 PDF 到本地缓存，已存在则直接返回"""
    arxiv_id_clean = arxiv_id.replace("/", "_")
    fp = CACHE_DIR / f"{arxiv_id_clean}.pdf"
    if fp.exists() and fp.stat().st_size > 1024:
        return fp
    if not pdf_url:
        # 由 arxiv_id 推 URL
        base_id = arxiv_id_clean.split("v")[0]
        pdf_url = f"https://arxiv.org/pdf/{base_id}.pdf"
    logger.info(f"下载 PDF: {pdf_url}")
    req = urllib.request.Request(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(fp, "wb") as f:
        f.write(r.read())
    return fp


# ==================== 文本提取 ====================

def extract_text(pdf_path: Path) -> str:
    """提取 PDF 全文（纯文本）"""
    doc = fitz.open(pdf_path)
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)


# ==================== 章节切分 ====================

# 常见论文章节标题模式（容忍编号、大小写）
SECTION_PATTERNS = [
    ("abstract", r"^\s*(?:\d+\.?\s*)?abstract\s*$"),
    ("introduction", r"^\s*(?:\d+\.?\s*)?(introduction|1\s+introduction)\s*$"),
    ("related_work", r"^\s*(?:\d+\.?\s*)?(related\s+work|background)\s*$"),
    ("preliminary", r"^\s*(?:\d+\.?\s*)?(preliminaries?|problem\s+(formulation|definition|statement))\s*$"),
    ("method", r"^\s*(?:\d+\.?\s*)?(method(ology)?s?|approach|proposed\s+(method|model|approach|framework)|model)\s*$"),
    ("experiment", r"^\s*(?:\d+\.?\s*)?(experiments?|evaluation|empirical\s+study|results?)\s*$"),
    ("ablation", r"^\s*(?:\d+\.?\s*)?(ablation\s+(study|studies|analysis)|ablations?)\s*$"),
    ("discussion", r"^\s*(?:\d+\.?\s*)?(discussion|analysis)\s*$"),
    ("conclusion", r"^\s*(?:\d+\.?\s*)?(conclusion|conclusions?|summary|future\s+work)\s*$"),
    ("limitation", r"^\s*(?:\d+\.?\s*)?(limitations?)\s*$"),
    ("reference", r"^\s*(references?|bibliography)\s*$"),
]


def split_sections(text: str) -> Dict[str, str]:
    """按常见学术论文章节切分；找不到则统一塞 'body'"""
    lines = text.split("\n")
    # 标记每行属于哪个 section
    cur = "header"
    bucket: Dict[str, List[str]] = {cur: []}
    for ln in lines:
        ln_strip = ln.strip()
        matched = None
        if 2 < len(ln_strip) < 80:
            for sec, pat in SECTION_PATTERNS:
                if re.match(pat, ln_strip, re.IGNORECASE):
                    matched = sec
                    break
        if matched:
            cur = matched
            bucket.setdefault(cur, [])
            continue
        bucket.setdefault(cur, []).append(ln)

    # 引用之后的内容丢弃
    out: Dict[str, str] = {}
    for k, v in bucket.items():
        if k == "reference":
            continue
        s = "\n".join(v).strip()
        if s:
            out[k] = s
    # 如果章节切得太烂（关键字段都没有），退回全文 body
    if not any(k in out for k in ["method", "experiment"]):
        out = {"body": text}
    return out


# ==================== 图片提取 ====================

def extract_top_images(
    pdf_path: Path, arxiv_id: str, max_images: int = 4, min_kb: int = 30
) -> List[Path]:
    """提取 PDF 中较大的几张图片（很可能是模型架构图/实验结果图）"""
    arxiv_id_clean = arxiv_id.replace("/", "_")
    out_dir = IMG_DIR / arxiv_id_clean
    out_dir.mkdir(parents=True, exist_ok=True)

    # 已经提取过则直接返回
    existed = sorted(out_dir.glob("*.png"))
    if existed:
        return existed[:max_images]

    doc = fitz.open(pdf_path)
    candidates: List[Tuple[int, bytes, str]] = []  # (size, bytes, ext)
    seen_xrefs = set()
    for page_idx, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base = doc.extract_image(xref)
            except Exception:
                continue
            data = base.get("image")
            ext = base.get("ext", "png")
            if not data:
                continue
            size = len(data)
            if size < min_kb * 1024:  # 太小的多半是 logo
                continue
            candidates.append((size, data, ext))
    doc.close()

    # 按大小取 top N
    candidates.sort(key=lambda x: -x[0])
    saved: List[Path] = []
    for i, (_, data, ext) in enumerate(candidates[:max_images]):
        fp = out_dir / f"fig_{i+1}.{ext}"
        with open(fp, "wb") as f:
            f.write(data)
        saved.append(fp)
    logger.info(f"提取关键图 {len(saved)} 张 → {out_dir}")
    return saved


# ==================== 综合接口 ====================

def parse_paper(arxiv_id: str, pdf_url: str = None) -> Dict:
    """对一篇论文做全套：下载 → 提取文本 → 切章节 → 提关键图"""
    pdf = download_pdf(arxiv_id, pdf_url)
    text = extract_text(pdf)
    sections = split_sections(text)
    images = extract_top_images(pdf, arxiv_id)
    return {
        "pdf_path": str(pdf),
        "full_text_len": len(text),
        "sections": sections,
        "image_paths": [str(p) for p in images],
    }


if __name__ == "__main__":
    import sys
    aid = sys.argv[1] if len(sys.argv) > 1 else "2310.06770"
    info = parse_paper(aid)
    print(f"全文 {info['full_text_len']} 字符")
    print(f"章节: {list(info['sections'].keys())}")
    print(f"图片: {info['image_paths']}")
