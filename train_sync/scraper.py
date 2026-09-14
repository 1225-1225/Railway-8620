# -*- coding: utf-8 -*-
"""
scraper.py —— 从 12306 公开接口拉取车次时刻表（原创实现）

数据来源：
  12306 两个公开 HTTP 接口（无需登录、无鉴权）：
    1. 车次号搜索:  GET https://search.12306.cn/search/v1/train/search
                    params: {keyword, date}
    2. 时刻表详情:  GET https://kyfw.12306.cn/otn/queryTrainInfo/query
                    params: {leftTicketDTO.train_no, leftTicketDTO.train_date, rand_code}

免责声明：
  本脚本仅拉取 12306 公开的车次运行时刻信息，用于个人学习研究。
  请控制请求频率，遵守目标网站的使用条款；如用于商业用途请先获取授权。

用法：
  python scraper.py              # 爬取今天，输出 raw/train_list{date}.json
  python scraper.py 2026-09-14   # 爬取指定日期
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

# ── 常量 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "raw")
LOG_PATH = os.path.join(BASE_DIR, "sync.log")

URL_TRAIN_NO = "https://search.12306.cn/search/v1/train/search"
URL_TRAIN_INFO = "https://kyfw.12306.cn/otn/queryTrainInfo/query"

# 车次字头 → 数字范围（与 12306 车次编码规则对应）
PREFIX_RANGES = {
    "G": range(1, 100),    # 高铁
    "D": range(1, 100),    # 动车
    "C": range(1, 100),    # 城际
    "Z": range(1, 10),     # 直达
    "T": range(1, 10),     # 特快
    "K": range(1, 100),    # 快速
    "S": range(1, 100),    # 市郊
    "Y": range(1, 10),     # 旅游
    "P": range(1, 10),     # 纯数字（P 占位）
}

# 爬取线程数：并发过高会触发反爬，8 是经验安全值
MAX_WORKERS = 8
# 单次请求失败重试次数
MAX_RETRY = 5
# 正常模式下每批次之间的间隔（秒）
BATCH_SLEEP = 0.5

# 模拟浏览器请求头（User-Agent 取自常见浏览器，可按需替换）
HEADERS = {
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Origin": "https://kyfw.12306.cn",
    "Referer": "https://kyfw.12306.cn/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# ── 日志 ──
def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── 接口调用（带重试）──
def fetch_train_no(keyword: str, date: str) -> list | str:
    """按车次关键字搜索，返回匹配的 train_no 列表；'empty' 表示无结果，'error' 表示失败"""
    params = {"keyword": keyword, "date": date}
    try:
        resp = requests.get(URL_TRAIN_NO, params=params, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return "error"
        js = resp.json()
        data = js.get("data")
        if not data:
            return "empty"
        return data
    except requests.RequestException:
        return "error"


def fetch_train_info(train_no: str, date: str) -> list | None:
    """按 train_no 拉取一个车次的完整时刻表站点列表；失败返回 None"""
    params = {
        "leftTicketDTO.train_no": train_no,
        "leftTicketDTO.train_date": date,
        "rand_code": "",
    }
    try:
        resp = requests.get(URL_TRAIN_INFO, params=params, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {}).get("data")
        if data is None:
            return None
        return data
    except requests.RequestException:
        return None


def compute_stop_time(station: dict) -> int:
    """计算停站时长（分钟），处理跨午夜"""
    if "is_start" in station:
        return 0
    arrive = station.get("arrive_time", "")
    start = station.get("start_time", "")
    if not arrive or not start or arrive == "----":
        return 0
    a_h, a_m = int(arrive[0:2]), int(arrive[3:5])
    s_h, s_m = int(start[0:2]), int(start[3:5])
    a_total = a_h * 60 + a_m
    s_total = s_h * 60 + s_m
    return s_total - a_total if s_total >= a_total else 24 * 60 - a_total + s_total


# ── 车次关键字生成 ──
def build_keywords(prefixes: str) -> list[str]:
    """生成要搜索的车次关键字列表，如 G1..G99, D1..D99, ..., 1..9"""
    keywords = []
    for ch in prefixes:
        if ch == "P":
            for n in PREFIX_RANGES["P"]:
                keywords.append(str(n))
        elif ch in PREFIX_RANGES:
            for n in PREFIX_RANGES[ch]:
                keywords.append(f"{ch}{n}")
    return keywords


# ── 主爬取流程 ──
def scrape(date: str) -> dict:
    """爬取指定日期的全部车次时刻表

    Returns:
        train_list: {train_no: [站点列表...]}
        no_list:    {车次代码: train_no}
    """
    date_compact = date.replace("-", "")
    train_list: dict = {}
    no_list: dict = {}
    train_lock = threading.Lock()
    no_lock = threading.Lock()
    failed_keywords: list = []

    keywords = build_keywords("GDCZTKSYP")

    def process_keyword(keyword: str):
        """处理单个关键字：搜 train_no → 拉每个车次的时刻表"""
        result = None
        for attempt in range(MAX_RETRY):
            result = fetch_train_no(keyword, date_compact)
            if result != "error":
                break
            time.sleep(1)
        if result == "error":
            with no_lock:
                failed_keywords.append(keyword)
            return
        if result == "empty":
            return

        trains = []
        for train in result:
            code = train.get("station_train_code", "")
            no = train.get("train_no", "")
            if not code or not no:
                continue
            if code in no_list:
                continue
            with no_lock:
                no_list[code] = no
            if no not in train_list:
                trains.append(no)

        def fetch_one(no: str):
            info = None
            for attempt in range(MAX_RETRY):
                info = fetch_train_info(no, date)
                if info is not None:
                    break
                time.sleep(1)
            if info:
                # 补全停站时长
                for station in info:
                    station["stop_time"] = compute_stop_time(station)
                with train_lock:
                    train_list[no] = info

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(fetch_one, no) for no in trains]
            for f in as_completed(futures):
                f.result()  # 冒泡异常

    log(f"开始爬取 {date}，共 {len(keywords)} 个关键字，{MAX_WORKERS} 线程...")
    start = time.time()

    # 分两阶段跑（第一阶段全部关键字）
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(process_keyword, kw) for kw in keywords]
        for i, f in enumerate(as_completed(futures), 1):
            f.result()
            if i % 50 == 0:
                log(f"  进度 {i}/{len(keywords)}，已获取 {len(no_list)} 个车次")

    elapsed = time.time() - start
    log(f"爬取完成，耗时 {elapsed:.1f}s，车次 {len(no_list)} 个，"
        f"失败关键字 {len(failed_keywords)} 个")
    if failed_keywords:
        log(f"  失败关键字: {failed_keywords[:20]}")

    return {"train_list": train_list, "no_list": no_list}


def main():
    parser = argparse.ArgumentParser(description="12306 车次时刻表爬取")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"),
                        help="目标日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--output", default="", help="输出目录（默认 ./raw）")
    args = parser.parse_args()

    date = args.date
    date_compact = date.replace("-", "")
    out_dir = args.output or RAW_DIR
    os.makedirs(out_dir, exist_ok=True)

    data = scrape(date)

    out_path = os.path.join(out_dir, f"train_list{date_compact}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data["train_list"], f, ensure_ascii=False)
    log(f"已保存: {out_path} ({len(data['train_list'])} 个车次)")

    out_path_no = os.path.join(out_dir, f"no_list{date_compact}.json")
    with open(out_path_no, "w", encoding="utf-8") as f:
        json.dump(data["no_list"], f, ensure_ascii=False)
    log(f"已保存: {out_path_no}")


if __name__ == "__main__":
    main()
