"""Streamlit 可视化 Dashboard - 精排 / 混排 论文周报"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import load_config
from storage import Storage
from pipeline import run_once

# ---------- 页面基础配置 ----------
st.set_page_config(
    page_title="精排 & 混排 arXiv 周报",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 主题方向分组
RANKING_DIRS = ["精排-CTR预估", "精排-CVR/多任务", "精排-LTR排序", "精排-用户兴趣建模"]
RERANK_DIRS = ["混排-Reranking", "混排-多目标融合", "混排-多样性/新颖性", "混排-广告/自然结果混排"]


@st.cache_resource
def get_store():
    cfg = load_config()
    return Storage(cfg["storage"]["db_path"]), cfg

store, cfg = get_store()


@st.cache_resource
def _bootstrap():
    if not store.all_dates():
        try:
            run_once()
        except Exception as e:
            st.warning(f"初始化抓取失败：{e}")
    return True

_bootstrap()


# ============================================================
# 深度解读渲染
# ============================================================

def _render_deep_summary(deep: dict, key_prefix: str = ""):
    """在网页上展示分章节深度解读"""
    sections = [
        ("🎯 Motivation", "motivation", [
            ("现实痛点", "real_world_pain"),
            ("现有方法不足", "existing_limitations"),
            ("本文切入角度", "this_paper_angle"),
            ("为什么重要", "why_it_matters"),
        ]),
        ("❓ 问题定义", "problem", [
            ("任务类型", "task_type"),
            ("形式化定义", "formal_definition"),
            ("输入", "input"),
            ("输出", "output"),
            ("关键约束", "key_constraints"),
        ]),
        ("🛠 方法详解", "method", [
            ("整体框架", "overview"),
            ("关键模块", "key_modules"),
            ("训练策略", "training_strategy"),
            ("推理流程", "inference_pipeline"),
            ("关键洞见", "key_insights"),
        ]),
        ("🧪 实验 & 主结果", "experiment", [
            ("数据集", "datasets"),
            ("评价指标", "metrics"),
            ("基线", "baselines"),
            ("主要发现", "main_results"),
            ("胜负分析", "win_or_lose"),
        ]),
        ("🔍 消融实验", "ablation", [
            ("消融逐项", "ablations"),
            ("超参敏感性", "hyperparameter_analysis"),
            ("Case Study", "case_study"),
            ("鲁棒性", "robustness"),
        ]),
        ("⚖️ 与 SOTA 对比", "comparison", [
            ("vs SOTA", "vs_sota"),
            ("复杂度对比", "complexity_compare"),
            ("工程友好度", "engineering_friendliness"),
            ("工业落地价值", "industry_value"),
        ]),
        ("⚠️ 局限 & 未来", "limitation", [
            ("局限", "limitations"),
            ("未来方向", "future_directions"),
            ("开放问题", "open_questions"),
            ("阅读建议", "reading_advice"),
        ]),
    ]

    tabs = st.tabs([title for title, _, _ in sections])
    for tab, (_, key, fields) in zip(tabs, sections):
        with tab:
            data = deep.get(key)
            if not data:
                st.info("（无内容或未解读）")
                continue
            if data.get("_parse_failed"):
                st.warning("LLM 输出解析失败，原始内容：")
                st.code(data.get("_raw", ""), language="text")
                continue
            for label, fkey in fields:
                v = data.get(fkey)
                if v is None or v == "" or v == []:
                    continue
                if isinstance(v, list):
                    st.markdown(f"**{label}**：")
                    for item in v:
                        if isinstance(item, dict):
                            cells = " &nbsp; ".join(
                                f"**{k}**: {item[k]}" for k in item if item[k]
                            )
                            st.markdown(f"- {cells}")
                        else:
                            st.markdown(f"- {item}")
                else:
                    st.markdown(f"**{label}**：{v}")

    meta = deep.get("_meta") or {}
    imgs = meta.get("image_paths") or []
    if imgs:
        st.markdown("---")
        st.markdown("**📎 PDF 中提取的关键图（按大小排序）**")
        cols = st.columns(min(len(imgs), 4))
        for col, img in zip(cols, imgs[:4]):
            try:
                if Path(img).exists():
                    col.image(img, use_container_width=True)
            except Exception:
                pass


# ============================================================
# 单篇论文卡片
# ============================================================

def render_paper_card(p: dict, idx: int = 0, scope: str = "all"):
    s = p.get("summary") or {}
    deep = p.get("deep_summary")
    prio = s.get("reading_priority")
    score = s.get("value_score")
    prio_emoji = {"高": "🔥", "中": "✨", "低": "·"}.get(prio, "")
    deep_badge = " 📖" if deep else ""

    title_line = f"{prio_emoji}{deep_badge} **{p['title']}**"
    meta_parts = [f"`{p['published']}`", " / ".join(p.get('directions') or ['其他'])]
    if score:
        meta_parts.append(f"价值 {'⭐'*int(score)}")
    if prio:
        meta_parts.append(f"优先级 {prio}")
    meta = " · ".join(meta_parts)

    arxiv_id = p["arxiv_id"]
    uniq = f"{scope}_{idx}_{arxiv_id}"

    with st.expander(title_line, expanded=False):
        st.markdown(meta)
        st.markdown(f"👥 {p.get('authors', '')[:200]}")
        st.markdown(f"🔗 [arXiv]({p['url']}) · [PDF]({p.get('pdf_url','')})")

        if s:
            st.markdown("---")
            st.markdown(f"**🎯 解决问题**：{s.get('problem','')}")
            st.markdown(f"**🛠 核心方法**：{s.get('method','')}")
            innovs = s.get("innovation") or []
            if innovs:
                st.markdown("**💡 创新点**：")
                for it in innovs:
                    st.markdown(f"- {it}")
            if s.get("experiment"):
                st.markdown(f"**🧪 实验**：{s.get('experiment')}")
            if s.get("tags"):
                st.markdown("**🏷 细分标签**：" + " ".join(f"`{t}`" for t in s["tags"]))
        else:
            st.info("尚未生成浅解读")

        # ===== 深度解读区 =====
        st.markdown("---")
        col_a, col_b, _ = st.columns([1.2, 1.5, 4])
        with col_a:
            btn_label = "🔄 重新深度解读" if deep else "📖 生成深度解读"
            if st.button(btn_label, key=f"deep_{uniq}"):
                with st.spinner("正在下载 PDF + 调用 LLM 深度解读..."):
                    from deep_summarizer import deep_summarize
                    try:
                        new_deep = deep_summarize(p, cfg)
                        store.update_deep_summary(arxiv_id, new_deep)
                        st.success("深度解读完成")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"深度解读失败：{ex}")
        with col_b:
            if deep:
                from ppt_generator import OUT_DIR as PPT_DIR
                ppt_path = PPT_DIR / f"{arxiv_id.replace('/', '_')}.pptx"
                if not ppt_path.exists():
                    if st.button("📥 生成 PPT", key=f"ppt_{uniq}"):
                        with st.spinner("正在生成 PPT..."):
                            from ppt_generator import generate_ppt
                            try:
                                generate_ppt(p)
                                st.rerun()
                            except Exception as ex:
                                st.error(f"PPT 生成失败：{ex}")
                if ppt_path.exists():
                    with open(ppt_path, "rb") as f:
                        st.download_button(
                            "⬇️ 下载 .pptx",
                            data=f.read(),
                            file_name=ppt_path.name,
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            key=f"dl_{uniq}",
                        )

        if deep:
            _render_deep_summary(deep, key_prefix=uniq)

        with st.popover("查看英文摘要"):
            st.write(p.get("abstract", ""))


def _sort_papers(papers):
    def _k(p):
        s = p.get("summary") or {}
        prio_map = {"高": 0, "中": 1, "低": 2}
        return (prio_map.get(s.get("reading_priority"), 3),
                -(s.get("value_score") or 0),
                p.get("published") or "")
    return sorted(papers, key=_k)


def render_papers_section(papers, scope_name: str):
    if not papers:
        st.info("该方向本周无新论文。")
        return
    papers = _sort_papers(papers)
    for i, p in enumerate(papers):
        render_paper_card(p, idx=i, scope=scope_name)


def render_chart(papers, title: str = "方向分布"):
    if not papers:
        return
    rows = []
    for p in papers:
        for d in (p.get("directions") or ["其他"]):
            rows.append({"direction": d})
    df_dir = pd.DataFrame(rows)
    stat = df_dir["direction"].value_counts().reset_index()
    stat.columns = ["direction", "count"]
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(stat, x="direction", y="count", title=title,
                     color="direction", text="count")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="数量",
                          xaxis={"tickangle": -25})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = px.pie(stat, names="direction", values="count", hole=0.4,
                      title=f"{title}（占比）")
        st.plotly_chart(fig2, use_container_width=True)


# ============================================================
# 顶部 Header
# ============================================================
col1, col2, col3 = st.columns([5, 1.2, 1.2])
with col1:
    st.title("📚 精排 & 混排 arXiv 周报")
    st.caption("每周自动抓取 arXiv 推荐系统精排/混排环节最新论文，LLM 深度解读 + PPT 一键导出")
with col2:
    if st.button("🔄 立即抓取本周", use_container_width=True, type="primary"):
        with st.spinner("正在抓取 + 浅解读 + 深度解读，本次可能耗时较长..."):
            n = run_once()
        st.success(f"完成，新增 {n} 篇")
        st.rerun()
with col3:
    if st.button("ℹ️ 流程说明", use_container_width=True):
        st.session_state["show_help"] = not st.session_state.get("show_help", False)

if st.session_state.get("show_help"):
    st.info(
        "**自动流程**：每周一 9:00 抓取过去 7 天 cs.IR + cs.LG 中精排/混排相关论文 → "
        "规则分类 → 浅解读（一句话总结） → 自动深度解读（动机/问题/方法/实验/消融/对比/局限） → "
        "自动生成 PPT。**精排/混排方向论文**默认全部深度解读，其他方向只做浅解读。"
    )

# ============================================================
# 侧边栏
# ============================================================
st.sidebar.header("🔍 筛选")

all_dates = store.all_dates()
default_to = dt.date.today()
default_from = default_to - dt.timedelta(days=7)
date_range = st.sidebar.date_input(
    "📅 发布日期",
    value=(default_from, default_to),
    max_value=dt.date.today(),
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    date_from, date_to = [d.strftime("%Y-%m-%d") for d in date_range]
else:
    date_from = date_to = date_range.strftime("%Y-%m-%d")

# 方向多选
all_dirs = list(cfg["directions"].keys()) + ["其他"]
sel_dirs = st.sidebar.multiselect("🏷 方向", options=all_dirs, default=[])

kw = st.sidebar.text_input("🔎 关键词搜索（标题/摘要）", "")
priority = st.sidebar.selectbox("⭐ 阅读优先级", options=["全部", "高", "中", "低"], index=0)
priority_arg = None if priority == "全部" else priority

only_deep = st.sidebar.checkbox("仅看已生成深度解读的论文", value=False)

st.sidebar.divider()
backend_label = "☁️ Turso 云端" if store.is_remote else "💾 本地 SQLite"
st.sidebar.caption(f"**存储后端**：{backend_label}")
st.sidebar.caption(f"**总入库量**：{len(store.list_papers())} 篇")

# ============================================================
# 取数
# ============================================================
papers = store.list_papers(
    date_from=date_from,
    date_to=date_to,
    directions=sel_dirs or None,
    keyword=kw or None,
    priority=priority_arg,
)
if only_deep:
    papers = [p for p in papers if p.get("deep_summary")]


def filter_by_dirs(items, dirs):
    s = set(dirs)
    return [p for p in items if s & set(p.get("directions") or [])]


ranking_papers = filter_by_dirs(papers, RANKING_DIRS)
rerank_papers = filter_by_dirs(papers, RERANK_DIRS)
focus_ids = {p["arxiv_id"] for p in ranking_papers + rerank_papers}
other_papers = [p for p in papers if p["arxiv_id"] not in focus_ids]

# ============================================================
# 顶部指标
# ============================================================
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("筛选总数", f"{len(papers)} 篇")
m2.metric("🎯 精排", f"{len(ranking_papers)} 篇")
m3.metric("🔀 混排", f"{len(rerank_papers)} 篇")
deep_n = sum(1 for p in papers if p.get("deep_summary"))
m4.metric("已深度解读", f"{deep_n} 篇")
high_n = sum(1 for p in papers if p.get("summary") and p["summary"].get("reading_priority") == "高")
m5.metric("🔥 高优先级", f"{high_n} 篇")

# ============================================================
# 主体：4 个 Tab（总览 / 精排 / 混排 / 其他）
# ============================================================
tab_overview, tab_ranking, tab_rerank, tab_others = st.tabs([
    f"📊 总览",
    f"🎯 精排专题（{len(ranking_papers)}）",
    f"🔀 混排专题（{len(rerank_papers)}）",
    f"📦 其他（{len(other_papers)}）",
])

with tab_overview:
    if not papers:
        st.info("当前筛选条件下无论文。")
    else:
        render_chart(papers, "全部论文方向分布")
        st.divider()
        st.subheader(f"📄 全部论文（{len(papers)}）")
        render_papers_section(papers, scope_name="overview")

with tab_ranking:
    st.subheader("🎯 精排环节专题")
    st.caption("聚焦 CTR/CVR 预估、多任务建模、Learning to Rank、用户兴趣建模等")
    if ranking_papers:
        render_chart(ranking_papers, "精排子方向分布")
        st.divider()
    render_papers_section(ranking_papers, scope_name="ranking")

with tab_rerank:
    st.subheader("🔀 混排环节专题")
    st.caption("聚焦 Re-Ranking、多目标融合、多样性、广告/自然结果混排等")
    if rerank_papers:
        render_chart(rerank_papers, "混排子方向分布")
        st.divider()
    render_papers_section(rerank_papers, scope_name="rerank")

with tab_others:
    st.subheader("📦 其他相关方向")
    st.caption("LLM4Rec / 序列推荐 / 图推荐 / 公平去偏 / 对比学习 / 生成式推荐 等")
    if other_papers:
        render_chart(other_papers, "其他方向分布")
        st.divider()
    render_papers_section(other_papers, scope_name="others")
