# -*- coding: utf-8 -*-
"""
run_daily.py —— 一键更新车次数据

流程：
  1. 爬取（scraper.py 逻辑）
  2. 转换（transform.py 逻辑）
  3. 只有全部成功才替换主项目 data/ 下的文件

失败保护：
  - 爬取失败 → 保留旧数据，不覆盖
  - 转换失败 → 保留旧数据，不覆盖

用法：
  python run_daily.py              # 用今天日期
  python run_daily.py 2026-09-14   # 用指定日期
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 复用子模块
from scraper import scrape, log
from transform import convert, atomic_write

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUT_DETAILS = os.path.join(PROJECT_ROOT, "data", "train_details.json")
OUT_STATIONS = os.path.join(PROJECT_ROOT, "data", "train_stations.json")


def main():
    parser = argparse.ArgumentParser(description="一键更新车次数据")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"),
                        help="目标日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只爬取转换，不覆盖主项目 data/ 文件")
    args = parser.parse_args()

    date = args.date
    log(f"===== 开始每日更新 {date} =====")

    # 1. 爬取
    data = scrape(date)

    # 2. 质量检查：车次太少视为爬取失败
    if len(data["train_list"]) < 1000:
        log(f"❌ 爬取结果异常（仅 {len(data['train_list'])} 个车次），"
            f"可能被反爬，放弃更新，保留旧数据")
        sys.exit(1)

    # 3. 转换
    details, stations = convert(data["train_list"])
    log(f"转换完成: {len(details)} 个车次")

    # 4. 写入（原子替换）
    if args.dry_run:
        log("dry-run 模式：不写入主项目 data/")
        return

    atomic_write(OUT_DETAILS, details)
    atomic_write(OUT_STATIONS, stations)
    log(f"✅ 已更新 {OUT_DETAILS}")
    log(f"✅ 已更新 {OUT_STATIONS}")
    log(f"===== 每日更新完成 {date} =====")


if __name__ == "__main__":
    main()
