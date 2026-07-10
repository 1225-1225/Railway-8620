"""
地图生成工具（LangChain tool）
"""

import os
import logging
import functools
import time
from langchain_core.tools import tool
from agent.route_map_generator import generate_train_route_map, generate_multi_train_route_map

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

# 地图文件的 URL 前缀（通过 API 静态文件服务访问）
_MAP_URL_PREFIX = "/maps"


@tool(description="为指定车次生成基于真实铁路线路的运行路线交互式地图（HTML格式）。"
                  "输入为车次号列表，例如 ['Z227'] 绘制单条路线，"
                  "或 ['G1', 'G2'] 绘制多条路线对比。"
                  "返回地图文件的访问URL。")
@log_tool_call
def generate_route_map(train_codes: list) -> str:
    """为车次生成运行路线地图
    
    Args:
        train_codes: 车次号列表，如 ['Z227'] 或 ['G1', 'G2']
    
    Returns:
        地图的访问 URL 和简短说明
    """
    if not train_codes:
        return "请提供至少一个车次号"
    
    if len(train_codes) == 1:
        code = train_codes[0].upper().strip()
        result = generate_train_route_map(code)
    else:
        codes = [c.upper().strip() for c in train_codes]
        result = generate_multi_train_route_map(codes)
    
    if result.startswith("需要") or result.startswith("未找到") or result.startswith("无法"):
        return result
    
    # result 是文件路径，转换为 URL
    filename = os.path.basename(result)
    url = f"{_MAP_URL_PREFIX}/{filename}"
    
    codes_str = '、'.join(train_codes)
    return f"已生成车次 {codes_str} 的运行路线地图\n请访问：{url}\n（在浏览器中打开此链接可查看交互式地图，支持缩放、悬停查看站名）"