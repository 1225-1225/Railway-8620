import os
import logging
import functools
import time
from langchain_core.tools import tool
from settings import settings as config_data

from agent.route_map_service import RouteMapService
from agent.vector_store import VectorStoreService

# ========== 日志配置 ==========
# 创建日志器
logger = logging.getLogger("tool_calls")
logger.setLevel(logging.DEBUG)

# 确保日志目录存在
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# 文件处理器：输出到 logs/tool_calls.log
file_handler = logging.FileHandler(os.path.join(log_dir, "tool_calls.log"), encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 定义日志格式
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器到日志器
logger.addHandler(file_handler)
logger.addHandler(console_handler)


# ========== 日志装饰器 ==========
def log_tool_call(func):
    """装饰器：记录工具调用的参数、结果和耗时"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        start_time = time.time()
        logger.info(f"调用工具: {tool_name}，参数: args={args}, kwargs={kwargs}")

        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"工具 {tool_name} 执行成功，耗时: {elapsed:.3f}秒，返回值: {result}")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"工具 {tool_name} 执行失败，耗时: {elapsed:.3f}秒，错误: {e}", exc_info=True)
            raise  # 重新抛出异常，保持原有行为
    return wrapper


# ========== 服务单例 ==========
# VectorStoreService 与 RouteMapService 构造时需加载持久化向量库 / 全国铁路图，
# 重复 new 会带来显著开销，因此用模块级单例懒加载。
_vector_store_service: "VectorStoreService | None" = None
_route_map_service: "RouteMapService | None" = None


def get_vector_store_service() -> "VectorStoreService":
    """返回 VectorStoreService 单例（懒加载）"""
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
    return _vector_store_service


def get_route_map_service() -> "RouteMapService":
    """返回 RouteMapService 单例（懒加载）

    RouteMapService 构造时需加载 GPKG（222MB）+ line_graph.json + timetable（56MB），
    并预构建 way 几何和 bbox 索引，重复 new 会带来显著开销。
    复用单例可让 per-line 图缓存和全图 A* 缓存跨请求命中。
    """
    global _route_map_service
    if _route_map_service is None:
        _route_map_service = RouteMapService()
    return _route_map_service


def reset_service_singletons():
    """重置单例（仅用于测试隔离：每个测试用例mock掉底层前调用一次，确保不残留旧实例）"""
    global _vector_store_service, _route_map_service
    _vector_store_service = None
    _route_map_service = None


# ========== 工具函数（应用装饰器） ==========
@tool(description="检索向量库, 寻找匹配的知识")
@log_tool_call
def retriever_tool(query: str):
    retriever = get_vector_store_service().get_retriever()
    docs = retriever.invoke(query)
    if not docs:
        return "未找到相关消息"
    return "\n\n".join(doc.page_content for doc in docs)


@tool(description="根据列车车次代码绘制运行路线图。参数 train_code 为车次代码（如 G1、K4174、Z227、T109、D4 等）。使用 OSM 真实轨道几何绘制精确路线。")
@log_tool_call
def route_map_drawing_tool(train_code: str) -> str:
    # 复用单例路线图服务
    service = get_route_map_service()

    # 绘制路线图
    output_dir = config_data.maps_output_dir
    os.makedirs(output_dir, exist_ok=True)
    try:
        filepath, stations = service.draw_train_route(train_code, output_dir)
    except Exception as e:
        logger.error(f"绘制车次 {train_code} 路线图失败: {e}")
        return f"绘制路线图时出错：{str(e)}"

    if not filepath:
        return f"未找到车次 {train_code}，请确认车次代码是否正确。"

    filename = os.path.basename(filepath)
    map_url = f"/maps/{filename}"

    # 构造返回消息
    route_desc = f"{stations[0]} → {stations[-1]}" if stations else "未知路线"
    station_count = len(stations) if stations else 0
    return (
        f"车次 {train_code} 的运行路线图已生成：\n"
        f"- 路线：{route_desc}\n"
        f"- 共 {station_count} 站\n"
        f"\n[MAP]{map_url}[/MAP]"
    )


@tool(description="根据起点站和终点站查找所有车次并绘制每趟车的运行路线图。参数 start_station：起点站名（如’合肥’）；参数 end_station：终点站名（如‘北京西‘）。返回按发车时间从早到晚排序的车次列表，每趟车单独一张路线图。适用于用户说‘X到Y‘、‘从X去Y‘等场景。")
@log_tool_call
def station_route_drawing_tool(start_station: str, end_station: str) -> str:
    # 复用单例路线图服务
    service = get_route_map_service()

    # 1. 查找所有经过这两站的车次（已按发车时间排序）
    trains = service.find_trains_between_stations(start_station, end_station)
    if not trains:
        return f"未找到从 {start_station} 到 {end_station} 的列车，请确认站名是否正确。"

    total = len(trains)
    # 限制最多 20 趟，避免响应过慢
    max_trains = 20
    if total > max_trains:
        trains = trains[:max_trains]
        note = f"（仅展示前 {max_trains} 趟，共 {total} 趟）"
    else:
        note = f"（共 {total} 趟）"

    # 2. 一一绘制路线图
    output_dir = config_data.maps_output_dir
    os.makedirs(output_dir, exist_ok=True)

    train_lines = []
    map_blocks = []
    for code, dep_time, _, _, _ in trains:
        try:
            filepath, stations = service.draw_train_route(code, output_dir)
            if filepath:
                filename = os.path.basename(filepath)
                map_url = f"/maps/{filename}"
                route_desc = f"{stations[0]} → {stations[-1]}" if stations else ""
                train_lines.append(f"- {code}（{dep_time} 发车，{route_desc}）")
                map_blocks.append(f"[MAP]{map_url}[/MAP]")
            else:
                train_lines.append(f"- {code}（{dep_time} 发车）：未找到时刻表数据")
        except Exception as e:
            logger.error(f"绘制车次 {code} 路线图失败: {e}")
            train_lines.append(f"- {code}（{dep_time} 发车）：绘制失败 - {str(e)}")

    # 3. 构造返回消息
    header = f"从 {start_station} 到 {end_station} 的列车路线图已生成{note}：\n"
    train_list = "\n".join(train_lines)
    maps = "\n".join(map_blocks)
    return f"{header}{train_list}\n\n{maps}"