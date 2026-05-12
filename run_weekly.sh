#!/bin/bash
# ====================================================
# 每周一定时任务：抓取 arXiv 上周新论文 + 自动深度解读 + 生成 PPT
# 由 crontab 调用：0 9 * * 1 /Users/xusong/Desktop/agent/recsys-arxiv-agent/run_weekly.sh
# ====================================================

set -e

PROJECT_DIR="/Users/xusong/Desktop/agent/recsys-arxiv-agent"
cd "$PROJECT_DIR"

# 读取环境变量配置（敏感信息不放 crontab）
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

# 日志目录
mkdir -p data/logs
LOG_FILE="data/logs/cron_$(date +%Y%m%d_%H%M%S).log"

echo "==================== $(date) ====================" >> "$LOG_FILE"
echo "开始执行每周抓取任务..." >> "$LOG_FILE"

# 用绝对路径调用 python（crontab 中 PATH 很受限）
/usr/bin/python3 pipeline.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "完成，退出码: $EXIT_CODE，日志: $LOG_FILE" >> "$LOG_FILE"
echo "==================== END ====================" >> "$LOG_FILE"

exit $EXIT_CODE
