"""通用工具：配置加载、日志"""
import os
import logging
import yaml
from pathlib import Path

ROOT = Path(__file__).parent

def load_config(path: str = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # 优先级：环境变量 > Streamlit Secrets > config.yaml
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            if "LLM_API_KEY" in st.secrets:
                api_key = st.secrets["LLM_API_KEY"]
        except Exception:
            pass
    if api_key:
        cfg["llm"]["api_key"] = api_key
    return cfg


def setup_logger(name: str = "recsys_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(h)
    return logger
