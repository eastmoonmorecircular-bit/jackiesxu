"""Streamlit 可视化 Dashboard"""
from __future__ import annotations
import datetime as dt
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import load_config
from storage import Storage
from pipeline import run_once

# ---------- 页面基础配置 ----------
st.set_page_config(
    page_title="推荐系统 arXiv 日报",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def get_store():
    cfg = load_config()
    return Storage(cfg["storage"]["db_path"]), cfg

store, cfg = get_store()

# 首次部署若数据库为空，自动抓取一次（仅一次，避免每次刷新都跑）
@st.cache_resource
def _bootstrap():
    if not store.all_dates():
        try:
            run_once()
        except Exception as e:
            st.warning(f"初始化抓取失败：{e}")
    return True

_bootstrap()

# ---------- 顶部 ----------
col1, col2 = st.columns([6, 1])
with col1:
    st.title("📚 推荐系统 arXiv 日报")
    st.caption("自动抓取 arXiv cs.IR 最新论文，按方向分类并由 LLM 进行中文解读")
with col2:
    if st.button("🔄 立即抓取", use_container_width=True, type="primary"):
        with st.spinner("正在抓取与解读，请稍候..."):
            n = run_once()
        st.success(f"完成，新增 {n} 篇")
        st.rerun()

# ---------- 侧边栏筛选 ----------
st.sidebar.header("🔍 筛选")

# 日期范围
all_dates = store.all_dates()
default_from = dt.date.today() - dt.timedelta(days=7)
default_to = dt.date.today()
if all_dates:
    default_from = max(default_from, dt.datetime.strptime(all_dates[-1], "%Y-%m-%d").date())

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

# 关键词
kw = st.sidebar.text_input("🔎 关键词搜索（标题/摘要）", "")

# 优先级
priority = st.sidebar.selectbox("⭐ 阅读优先级", options=["全部", "高", "中", "低"], index=0)
priority_arg = None if priority == "全部" else priority

# 系统状态
st.sidebar.divider()
backend_label = "☁️ Turso 云端" if store.is_remote else "💾 本地 SQLite"
st.sidebar.caption(f"**存储后端**：{backend_label}")
st.sidebar.caption(f"**总入库量**：{len(store.list_papers())} 篇")

# ---------- 取数 ----------
papers = store.list_papers(
    date_from=date_from,
    date_to=date_to,
    directions=sel_dirs or None,
    keyword=kw or None,
    priority=priority_arg,
)

# ---------- 顶部指标 ----------
m1, m2, m3, m4 = st.columns(4)
m1.metric("筛选结果", f"{len(papers)} 篇")
m2.metric("已解读", sum(1 for p in papers if p.get("summary")))
high_n = sum(1 for p in papers if p.get("summary") and p["summary"].get("reading_priority") == "高")
m3.metric("高优先级", high_n)
m4.metric("总入库量", len(store.list_papers()))

# ---------- 方向分布图 ----------
if papers:
    rows = []
    for p in papers:
        for d in (p.get("directions") or ["其他"]):
            rows.append({"direction": d})
    df_dir = pd.DataFrame(rows)
    stat = df_dir["direction"].value_counts().reset_index()
    stat.columns = ["direction", "count"]

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(stat, x="direction", y="count", title="方向分布",
                     color="direction", text="count")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="数量")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = px.pie(stat, names="direction", values="count", title="方向占比", hole=0.4)
        st.plotly_chart(fig2, use_container_width=True)

# ---------- 论文列表 ----------
st.divider()
st.subheader(f"📄 论文列表（{len(papers)} 篇）")

if not papers:
    st.info("暂无符合条件的论文。试试点击右上角「立即抓取」拉取最新论文。")
else:
    # 排序：有解读的高优先级在前
    def _sort_key(p):
        s = p.get("summary") or {}
        prio_map = {"高": 0, "中": 1, "低": 2}
        return (prio_map.get(s.get("reading_priority"), 3),
                -(s.get("value_score") or 0),
                p.get("published") or "")
    papers.sort(key=_sort_key)

    for p in papers:
        s = p.get("summary") or {}
        prio = s.get("reading_priority")
        score = s.get("value_score")
        prio_emoji = {"高": "🔥", "中": "✨", "低": "·"}.get(prio, "")

        title_line = f"{prio_emoji} **{p['title']}**"
        meta = f"`{p['published']}` · {' / '.join(p.get('directions') or ['其他'])}"
        if score:
            meta += f" · 价值 {'⭐'*int(score)}"

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
                st.info("尚未生成 LLM 解读（可在配置中启用 LLM 后点击右上角刷新）")

            with st.popover("查看英文摘要"):
                st.write(p.get("abstract", ""))
