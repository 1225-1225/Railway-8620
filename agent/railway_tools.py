"""
铁路查询工具：车次查询、路线查询

提供两个Agent工具：
  - query_train_info: 按车次号查详细信息
  - query_trains_by_route: 按起讫站查车次

数据来源：data/train_details.json (含时间信息)
"""

import json
import os
import logging
import functools
import time
from langchain_core.tools import tool

logger = logging.getLogger("tool_calls")


def log_tool_call(func):
    """记录工具调用的参数、结果和耗时（本地副本，避免循环引用）"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        start_time = time.time()
        logger.info(f"调用工具: {tool_name}，参数: args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"工具 {tool_name} 执行成功，耗时: {elapsed:.3f}秒")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"工具 {tool_name} 执行失败，耗时: {elapsed:.3f}秒，错误: {e}")
            raise
    return wrapper

# ===== 数据加载 =====
_data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_train_details_path = os.path.join(_data_dir, 'train_details.json')
_train_stations_path = os.path.join(_data_dir, 'train_stations.json')

# 缓存数据
_train_details = None
_train_stations = None


def _load_train_details():
    global _train_details
    if _train_details is None:
        with open(_train_details_path, 'r', encoding='utf-8') as f:
            _train_details = json.load(f)
        logger.info(f"加载 train_details.json: {len(_train_details)} 个车次")
    return _train_details


def _load_train_stations():
    global _train_stations
    if _train_stations is None:
        with open(_train_stations_path, 'r', encoding='utf-8') as f:
            _train_stations = json.load(f)
        logger.info(f"加载 train_stations.json: {len(_train_stations)} 个车次")
    return _train_stations


# ===== 工具函数 =====

def format_train_info(train_code: str, info: dict) -> str:
    """格式化单个车次信息为可读文本"""
    lines = []
    code = info.get('train_code', train_code)
    cls = info.get('class', info.get('train_class', ''))
    from_st = info.get('from', info.get('start_station', ''))
    to_st = info.get('to', info.get('end_station', ''))
    
    lines.append(f"🚄 {code} ({cls})")
    lines.append(f"  起讫站: {from_st} → {to_st}")
    lines.append(f"  经停 {len(info.get('stations', []))} 站:")
    
    station_details = info.get('station_details', [])
    stations = info.get('stations', [])
    
    if station_details:
        # 有详细时间信息
        for sd in station_details:
            arrive = sd.get('arrive', '') or '----'
            depart = sd.get('depart', '') or '----'
            lines.append(f"    {sd.get('no', 0)}. {sd['name']} 到:{arrive} 发:{depart}")
    else:
        # 只有站名
        for i, s in enumerate(stations, 1):
            lines.append(f"    {i}. {s}")
    
    return '\n'.join(lines)


def _search_train_stations(from_station: str, to_station: str, limit: int):
    """在 train_stations.json 中搜索符合条件的车次"""
    data = _load_train_stations()
    results = []
    
    for code, info in data.items():
        if info.get('from', '') == from_station and info.get('to', '') == to_station:
            results.append((code, info))
    
    # 排序：G > D > C > Z > T > K > 其他
    priority = {'G': 0, 'D': 1, 'C': 2, 'Z': 3, 'T': 4, 'K': 5}
    results.sort(key=lambda x: (
        priority.get(x[0][0], 9),
        x[0]
    ))
    
    # 从 train_details 获取详细信息
    details = _load_train_details()
    formatted = []
    for code, info in results[:limit]:
        if code in details:
            formatted.append(format_train_info(code, details[code]))
        else:
            # fallback to basic info
            cls = info.get('class', '')
            stations = info.get('stations', [])
            line = f"🚄 {code} ({cls})"
            line += f"\n  起讫站: {info.get('from', '')} → {info.get('to', '')}"
            line += f"\n  经停 {len(stations)} 站: {' → '.join(stations[:5])}"
            if len(stations) > 5:
                line += f" ... → {stations[-1]}"
            formatted.append(line)
    
    return formatted


# ===== LangChain 工具 =====

@tool(description="查询指定车次的详细信息，包括起讫站、列车类型、各站到达/发车时间。"
                  "输入为车次列表，例如 ['Z227'] 或 ['G1', 'G2']")
@log_tool_call
def query_train_info(train_codes: list) -> str:
    """查询一个或多个车次的详细信息
    
    Args:
        train_codes: 车次号列表，如 ['Z227', 'G1']
    
    Returns:
        每个车次的完整经停站和时间信息
    """
    details = _load_train_details()
    stations_basic = _load_train_stations()
    
    result_parts = []
    not_found = []
    
    for code in train_codes:
        code = code.upper().strip()
        if code in details:
            result_parts.append(format_train_info(code, details[code]))
        elif code in stations_basic:
            result_parts.append(format_train_info(code, stations_basic[code]))
        else:
            not_found.append(code)
    
    if not_found:
        result_parts.append(f"\n❌ 未找到以下车次信息: {', '.join(not_found)}")
    
    return '\n\n'.join(result_parts) if result_parts else '未找到任何车次信息'


@tool(description="根据起讫站查询符合条件的车次列表。"
                  "例如从北京到合肥的车次，输入 from_station='北京', to_station='合肥'")
@log_tool_call
def query_trains_by_route(from_station: str, to_station: str, limit: int = 3) -> str:
    """查询从某站到某站的车次
    
    Args:
        from_station: 出发站名称，如 '北京'
        to_station: 到达站名称，如 '合肥'
        limit: 最多返回车次数，默认3
    
    Returns:
        符合条件的车次详细信息列表
    """
    results = _search_train_stations(from_station, to_station, limit)
    
    if not results:
        return f"未找到从「{from_station}」到「{to_station}」的车次。"
    
    header = f"从「{from_station}」到「{to_station}」的 {len(results)} 个车次:\n"
    return header + '\n\n'.join(results)