# -*- coding: utf-8 -*-
"""
transform.py —— 将 12306 原始格式转换为 Railway-8620 主项目使用的格式

输入：train_sync/raw/train_list{YYYYMMDD}.json（12306 原始格式）
输出：../data/train_details.json 和 ../data/train_stations.json（主项目格式）

主项目格式（train_details.json）：
{
  "D8079": {
    "train_code": "D8079",
    "from": "锦州北",
    "to": "丹东",
    "class": "动车",
    "stations": ["锦州北", "盘锦", ...],
    "station_details": [
      {"name": "锦州北", "arrive": "----", "depart": "16:01", "no": 1}, ...
    ]
  }
}

主项目格式（train_stations.json）：
{
  "D8079": {"from": "锦州北", "to": "丹东", "class": "动车", "stations": [...]}
}

用法：
  python transform.py              # 用 raw/ 里最新日期的数据
  python transform.py 2026-09-14   # 用指定日期
"""

import argparse
import glob
import json
import os
import sys
import tempfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "raw")
# 主项目数据目录（train_sync 在项目根下，所以上一级是项目根）
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUT_DETAILS = os.path.join(PROJECT_ROOT, "data", "train_details.json")
OUT_STATIONS = os.path.join(PROJECT_ROOT, "data", "train_stations.json")

# 12306 原始分类 → 主项目分类映射
CLASS_MAP = {
    "动车": "动车",
    "高速": "高铁",
    "城际": "城际",
    "直达": "直达特快",
    "特快": "特快",
    "快速": "快速",
    "普快": "普快",
    "普客": "普客",
    "市郊": "市郊",
    "旅游": "旅游",
}


def find_latest_raw() -> str:
    """找到 raw/ 目录下日期最新的 train_list 文件"""
    files = glob.glob(os.path.join(RAW_DIR, "train_list*.json"))
    if not files:
        print(f"❌ {RAW_DIR} 下没有 train_list*.json 文件，请先运行 scraper.py")
        sys.exit(1)
    # 文件名形如 train_list20260914.json → 提取日期排序
    def date_key(f):
        name = os.path.basename(f)
        d = name.replace("train_list", "").replace(".json", "")
        return d
    return max(files, key=date_key)


def to_station_details(stations: list) -> list:
    """12306 站点列表 → 主项目 station_details 格式"""
    details = []
    for i, st in enumerate(stations, 1):
        details.append({
            "name": st.get("station_name", "").strip(),
            "arrive": st.get("arrive_time", "----"),
            "depart": st.get("start_time", "----"),
            "no": i,
        })
    return details


def convert(raw_train_list: dict) -> tuple[dict, dict]:
    """转换主数据结构

    Returns:
        (train_details, train_stations)
    """
    train_details = {}
    train_stations = {}

    for train_no, stations in raw_train_list.items():
        if not stations:
            continue
        first = stations[0]
        code = first.get("station_train_code", "").strip()
        if not code:
            continue

        from_name = first.get("start_station_name", "").strip()
        to_name = first.get("end_station_name", "").strip()
        cls = CLASS_MAP.get(first.get("train_class_name", ""), first.get("train_class_name", ""))

        station_names = [s.get("station_name", "").strip() for s in stations]
        station_names = [n for n in station_names if n]

        train_details[code] = {
            "train_code": code,
            "from": from_name,
            "to": to_name,
            "class": cls,
            "stations": station_names,
            "station_details": to_station_details(stations),
        }
        train_stations[code] = {
            "from": from_name,
            "to": to_name,
            "class": cls,
            "stations": station_names,
        }

    return train_details, train_stations


def atomic_write(path: str, data: dict):
    """先写临时文件再原子替换，避免写一半崩溃留下损坏 JSON"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def main():
    parser = argparse.ArgumentParser(description="转换 12306 数据为主项目格式")
    parser.add_argument("date", nargs="?", default="", help="日期 YYYY-MM-DD（默认用最新）")
    args = parser.parse_args()

    if args.date:
        date_compact = args.date.replace("-", "")
        raw_path = os.path.join(RAW_DIR, f"train_list{date_compact}.json")
        if not os.path.exists(raw_path):
            print(f"❌ 找不到 {raw_path}")
            sys.exit(1)
    else:
        raw_path = find_latest_raw()

    print(f"读取原始数据: {raw_path}")
    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    details, stations = convert(raw)
    print(f"转换完成: {len(details)} 个车次")

    atomic_write(OUT_DETAILS, details)
    print(f"✅ 已写入 {OUT_DETAILS}")
    atomic_write(OUT_STATIONS, stations)
    print(f"✅ 已写入 {OUT_STATIONS}")


if __name__ == "__main__":
    main()
