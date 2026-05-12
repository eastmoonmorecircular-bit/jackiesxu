# 推荐系统 arXiv 日报 Agent

每天自动从 arXiv 抓取推荐系统领域最新论文，按方向分类，使用 LLM 生成中文详细解读，并提供 Streamlit 可视化 Dashboard 浏览。

## 功能

- 🔍 **自动抓取**：基于 arXiv API，按 `cs.IR` 分类 + 关键词过滤
- 🏷 **方向分类**：13+ 推荐细分方向（LLM4Rec / 序列推荐 / CTR / 召回 / 图推荐 / 多模态 / 冷启动 ...）
- 🤖 **LLM 解读**：调用 DeepSeek / OpenAI 等，输出问题、方法、创新点、价值评分、阅读优先级
- 📊 **可视化 Dashboard**：按日期/方向/关键词/优先级筛选，方向分布图表
- ⏰ **定时调度**：每日自动运行
- 💾 **去重存储**：SQLite 本地持久化

## 快速开始

### 1. 安装依赖

```bash
cd recsys-arxiv-agent
pip install -r requirements.txt
```

### 2. 配置 LLM API Key

编辑 `config.yaml`，填入你的 API Key：

```yaml
llm:
  provider: deepseek
  api_key: "sk-xxxxxxxx"     # 这里填
  base_url: https://api.deepseek.com/v1
  model: deepseek-chat
```

或使用环境变量（推荐）：
```bash
export LLM_API_KEY="sk-xxxxxxxx"
```

> 推荐 DeepSeek（注册即送额度，单篇解读约 0.001 元）。也兼容任何 OpenAI 协议接口，改 `base_url` 与 `model` 即可。

### 3. 首次运行（手动抓取一次）

```bash
python pipeline.py
```

### 4. 启动可视化 Dashboard

```bash
streamlit run app.py
```

浏览器自动打开 http://localhost:8501

### 5. 启用每日定时

**方式 A：常驻调度脚本（开发推荐）**
```bash
python scheduler.py
```

**方式 B：macOS / Linux crontab**
```bash
crontab -e
# 添加（每天上午 9 点跑）
0 9 * * * cd /Users/xusong/Desktop/agent/recsys-arxiv-agent && /usr/bin/env python pipeline.py >> data/cron.log 2>&1
```

## 目录结构

```
recsys-arxiv-agent/
├── config.yaml          # 配置（关键词、方向规则、LLM、调度）
├── requirements.txt
├── utils.py             # 配置加载/日志
├── fetcher.py           # arXiv 抓取
├── classifier.py        # 关键词规则分类
├── summarizer.py        # LLM 解读
├── storage.py           # SQLite 存储/查询
├── pipeline.py          # 主流程（抓取->分类->解读->入库）
├── scheduler.py         # APScheduler 定时
├── app.py               # Streamlit Dashboard
└── data/                # SQLite 数据库（自动创建）
    └── papers.db
```

## 自定义

- **添加方向**：在 `config.yaml` 的 `directions` 增加 `方向名: [关键词列表]`
- **调整抓取范围**：修改 `arxiv.categories` / `keywords` / `max_results` / `days_back`
- **更换 LLM**：把 `llm.base_url` 与 `llm.model` 换成 OpenAI / 通义 / 混元 等任何 OpenAI 兼容接口
- **关闭 LLM 省钱**：`llm.enabled: false`，则只做抓取+分类，不消耗 token
