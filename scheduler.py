"""定时调度：每天定时跑一次 pipeline.run_once()"""
from apscheduler.schedulers.blocking import BlockingScheduler

from utils import load_config, setup_logger
from pipeline import run_once

logger = setup_logger(__name__)


def main():
    cfg = load_config()
    sched_cfg = cfg["scheduler"]

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        run_once,
        trigger="cron",
        hour=sched_cfg.get("hour", 9),
        minute=sched_cfg.get("minute", 0),
        id="daily_fetch",
    )
    logger.info(f"调度已启动：每天 {sched_cfg.get('hour',9):02d}:{sched_cfg.get('minute',0):02d} 抓取")

    # 启动时先跑一次（首次部署常用）
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
