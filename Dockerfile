FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir supervisor

# 复制项目
COPY . .

# 创建数据目录
RUN mkdir -p data

EXPOSE 8501

# 用 supervisor 同时跑 streamlit + scheduler
COPY supervisord.conf /etc/supervisord.conf

CMD ["supervisord", "-c", "/etc/supervisord.conf"]
