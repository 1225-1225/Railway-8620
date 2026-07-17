import os
import logging
import functools
import time
from langchain_core.tools import tool

from agent.ragflow_client import RAGFlowClient
from settings import settings as config_data

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


# ========== RAGFlow 客户端单例 ==========
_ragflow_client: RAGFlowClient | None = None


def get_ragflow_client() -> RAGFlowClient:
    """返回 RAGFlowClient 单例（懒加载）"""
    global _ragflow_client
    if _ragflow_client is None:
        _ragflow_client = RAGFlowClient(
            host=config_data.ragflow_host,
            api_key=config_data.ragflow_api_key,
            dataset_id=config_data.ragflow_dataset_id,
        )
    return _ragflow_client


def reset_service_singletons():
    """重置单例（仅用于测试隔离）"""
    global _ragflow_client
    _ragflow_client = None


# ========== 工具函数（应用装饰器） ==========
@tool(description="检索向量库, 寻找匹配的知识")
@log_tool_call
def retriever_tool(query: str):
    """从 RAGFlow 知识库中检索相关知识"""
    client = get_ragflow_client()
    results = client.search(
        query=query,
        top_k=config_data.kwargs,
        similarity_threshold=config_data.ragflow_similarity_threshold,
    )

    if not results:
        return "未找到相关消息"

    # 格式化返回结果
    formatted = []
    for i, r in enumerate(results, 1):
        source = f"（来源: {r['source']}）" if r['source'] else ""
        formatted.append(f"{i}. {r['content']}{source}")
    return "\n\n".join(formatted)


# ========== 地图生成工具 ==========
_MAP_URL_PREFIX = "/maps"

from agent.route_map_generator import generate_train_route_map

@tool(description="为指定车次生成运行路线交互式地图（HTML格式）。"
                  "输入车次号，例如 ['Z227']。"
                  "返回地图文件的访问URL。")
@log_tool_call
def generate_route_map(train_codes: list) -> str:
    """为车次生成运行路线地图

    Args:
        train_codes: 车次号列表，如 ['Z227']

    Returns:
        地图的访问 URL 和简短说明
    """
    if not train_codes:
        return "请提供至少一个车次号"

    code = train_codes[0].upper().strip()
    result = generate_train_route_map(code)

    if result.startswith("需要") or result.startswith("未找到") or result.startswith("无法"):
        return result

    # result 是文件路径，转换为 URL
    filename = os.path.basename(result)
    url = f"{_MAP_URL_PREFIX}/{filename}"

    return f"已生成车次 {code} 的运行路线地图\n请访问：{url}\n（在浏览器中打开此链接可查看交互式地图，支持缩放、悬停查看站名）"


# ========== 铁路查询工具 ==========
from agent.railway_tools import query_train_info, query_trains_by_route