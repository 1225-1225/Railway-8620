import os
import logging
import functools
import time
from langchain_core.tools import tool
import json
from settings import settings as config_data

from agent.llm import LLMService
from agent.railway_drawing import RailwayDrawingService
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


# ========== 工具函数（应用装饰器） ==========
@tool(description="检索向量库, 寻找匹配的知识")
@log_tool_call
def retriever_tool(query: str):
    retriever = VectorStoreService().get_retriever()
    docs = retriever.invoke(query)
    if not docs:
        return "未找到相关消息"
    return "\n\n".join(doc.page_content for doc in docs)


@tool(description="根据起点和终点城市名称绘制铁路线路图，并标注至少三条实际运行的车次")
@log_tool_call
def railway_drawing_tool(query: str) -> str:
    # 1. 从 query 中提取起点和终点（使用 LLM）
    try:
        prompt = f"从以下问题中提取起点和终点城市，并以 JSON 格式返回，例如 {{\"start\": \"北京\", \"end\": \"合肥\"}}。问题：{query}"
        response = LLMService().get_model().invoke(prompt).content
        if response.startswith("```json"):
            response = response.strip("```json\n").strip("```")
        elif response.startswith("```"):
            response = response.strip("```\n").strip("```")
        data = json.loads(response)
        start = data["start"]
        end = data["end"]
    except Exception as e:
        logger.error(f"解析城市名失败: {e}")
        return f"无法从您的描述中提取起点和终点，请明确说明例如“北京到合肥”。"

    # 2. 初始化路径查找器
    finder = RailwayDrawingService()

    # 3. 查找所有经过的车次，获取实际站名
    trains_info, actual_start, actual_end = finder.find_trains_between(start, end)
    if not trains_info:
        return f"未找到从 {start} 到 {end} 的列车车次。"

    # 4. 限制最多三条车次（已在 find_trains_between 中完成，但这里保留注释）
    if len(trains_info) > 3:
        trains_info = trains_info[:3]
        note = f"（仅展示前3个车次，共 {len(trains_info)} 个）"
    else:
        note = f"（共 {len(trains_info)} 个车次）"

    # 5. 生成地图
    output_dir = config_data.maps_output_dir
    os.makedirs(output_dir, exist_ok=True)
    try:
        filepath, valid_trains = finder.draw_trains_map(trains_info, actual_start, actual_end, output_dir)
    except Exception as e:
        logger.error(f"生成地图失败: {e}")
        return f"生成地图时出错：{str(e)}"

    filename = os.path.basename(filepath)
    map_url = f"/maps/{filename}"

    # 构造返回消息，列出车次（使用 name 字段）
    train_list = "\n".join([f"- {t.get('name', '未知')}" for t in valid_trains])
    return f"地图已生成，包含以下车次：\n{train_list}\n{note}\n\n[MAP]{map_url}[/MAP]"