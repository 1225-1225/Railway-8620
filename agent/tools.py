import os
import logging
import functools
import time
from langchain_core.tools import tool

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
# VectorStoreService 构造时需加载持久化向量库，
# 重复 new 会带来显著开销，因此用模块级单例懒加载。
_vector_store_service: "VectorStoreService | None" = None


def get_vector_store_service() -> "VectorStoreService":
    """返回 VectorStoreService 单例（懒加载）"""
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
    return _vector_store_service


def reset_service_singletons():
    """重置单例（仅用于测试隔离：每个测试用例mock掉底层前调用一次，确保不残留旧实例）"""
    global _vector_store_service
    _vector_store_service = None


# ========== 工具函数（应用装饰器） ==========
@tool(description="检索向量库, 寻找匹配的知识")
@log_tool_call
def retriever_tool(query: str):
    retriever = get_vector_store_service().get_retriever()
    docs = retriever.invoke(query)
    if not docs:
        return "未找到相关消息"
    return "\n\n".join(doc.page_content for doc in docs)


# ========== 铁路查询 / 地图工具 ==========
from agent.railway_tools import query_train_info, query_trains_by_route
from agent.map_tool import generate_route_map