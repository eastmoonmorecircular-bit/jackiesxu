"""定时调度：每周触发一次 pipeline.run_once()，对上周新论文做收集+解读+PPT"""
from apscheduler.schedulers.blocking import BlockingScheduler

from utils import load_config, setup_logger
from pipeline import run_once

logger = setup_logger(__name__)

WEEKDAY_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def main():
    cfg = load_config()
    sched_cfg = cfg["scheduler"]

    day = sched_cfg.get("day_of_week", 0)
    hour = sched_cfg.get("hour", 9)
    minute = sched_cfg.get("minute", 0)
    day_str = WEEKDAY_MAP.get(day, "mon")

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        run_once,
        trigger="cron",
        day_of_week=day_str,
        hour=hour,
        minute=minute,
        id="weekly_fetch",
    )
    logger.info(f"调度已启动：每周 {day_str.upper()} {hour:02d}:{minute:02d} "
                f"抓取过去 {cfg['arxiv'].get('days_back', 7)} 天的论文并自动深度解读")

    # 启动时先跑一次
    try:
        run_once()
    except Exception as e:
        logger.error(f"首次运行失败: {e}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度退出")


if __name__ == "__main__":
    main()
