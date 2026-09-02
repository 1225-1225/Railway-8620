"""
LangGraph SqliteSaver checkpoint 二进制解析模块。

背景：
  LangGraph 把完整对话状态用 msgpack 序列化后存入 SQLite 的 checkpoint 字段。
  JsonPlusSerializer.dumps_typed() 返回 ('msgpack', <bytes>)，其中 <bytes> 解包后：
    - 外层是 checkpoint dict: {v, ts, channel_values: {messages: [...]}}
    - 每条消息是 ['msgpack', <bytes>]，<bytes> 再解包是 ExtType(5)，
      ExtType(5).data 再解包是 ['module', 'ClassName', {kwargs}]

  本模块负责把这类二进制安全地还原为可读消息列表，供历史会话侧边栏使用。
  解析失败不抛异常，而是记录 warning 并返回空结果，保证读历史不影响主流程。
"""

import logging
import msgpack

logger = logging.getLogger("agent.checkpoint_parser")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(_handler)

# LangGraph 消息序列化内部使用的 msgpack ExtType code
_MSGPACK_EXT_CODE = 5


def _unpack_bytes(data) -> object:
    """安全解包 bytes，非 bytes 原样返回"""
    if isinstance(data, bytes):
        return msgpack.unpackb(data)
    return data


def _extract_typed_message(ext) -> dict | None:
    """从 ExtType(5) 中提取 {role, content}

    ExtType(5).data 解包后是 ['module', 'ClassName', {kwargs}]
    """
    if not (hasattr(ext, "code") and ext.code == _MSGPACK_EXT_CODE and hasattr(ext, "data")):
        return None
    inner = _unpack_bytes(ext.data)
    if not (isinstance(inner, (list, tuple)) and len(inner) >= 3):
        return None

    class_name = inner[1]
    kw = inner[2]
    if isinstance(kw, bytes):
        kw = msgpack.unpackb(kw)
    if not isinstance(kw, dict):
        return None

    content = kw.get("content", "")
    if isinstance(content, bytes):
        content = content.decode()
    if isinstance(class_name, bytes):
        class_name = class_name.decode()

    if class_name == "HumanMessage":
        role = "user"
    elif class_name in ("AIMessage", "AIMessageChunk"):
        role = "assistant"
    else:
        return None

    if not content:
        return None
    return {"role": role, "content": content}


def _extract_plain_dict_message(msg: dict) -> dict | None:
    """从纯 dict 格式的消息中提取 {role, content}"""
    role = msg.get("role", msg.get(b"role", ""))
    content = msg.get("content", msg.get(b"content", ""))
    if isinstance(role, bytes):
        role = role.decode()
    if isinstance(content, bytes):
        content = content.decode()
    if role in ("user", "assistant") and content:
        return {"role": role, "content": content}
    return None


def _extract_one(msg) -> dict | None:
    """从单条消息（任意格式）提取 {role, content}

    支持三种格式：
      1. ExtType(5) 直接出现
      2. JsonPlusSerializer 的 ['msgpack', <bytes>] 包装（bytes 内是 ExtType(5)）
      3. 纯 dict
    """
    # 格式 1：ExtType(5)
    if hasattr(msg, "code") and msg.code == _MSGPACK_EXT_CODE:
        return _extract_typed_message(msg)

    # 格式 2：['msgpack', <bytes>] 包装
    if isinstance(msg, (list, tuple)) and len(msg) >= 2:
        data = _unpack_bytes(msg[1])
        if hasattr(data, "code") and data.code == _MSGPACK_EXT_CODE:
            return _extract_typed_message(data)
        if isinstance(data, dict):
            return _extract_plain_dict_message(data)
        return None

    # 格式 3：纯 dict
    if isinstance(msg, dict):
        return _extract_plain_dict_message(msg)

    return None


def _extract_messages_list(cv: dict) -> list:
    """从 channel_values 中统一提取 messages 列表（兼容 dict 包装 / __start__ 兜底）"""
    for key in (b"messages", "messages"):
        val = cv.get(key)
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            return val
        if isinstance(val, dict):
            inner = val.get(b"messages", val.get("messages", []))
            if isinstance(inner, (list, tuple)):
                return inner

    # 兜底：从 __start__ 中提取
    start = cv.get(b"__start__", cv.get("__start__", {}))
    if isinstance(start, dict):
        raw = start.get(b"messages", start.get("messages", []))
        if isinstance(raw, dict):
            raw = raw.get(b"messages", raw.get("messages", []))
        if isinstance(raw, (list, tuple)):
            return raw
    return []


def parse_messages_from_checkpoint(blob: bytes) -> list:
    """从最新的 checkpoint msgpack blob 中提取所有人类可读的消息

    Args:
        blob: SqliteSaver checkpoint 字段的原始 bytes

    Returns:
        list[dict]: [{"role": "user"|"assistant", "content": str}, ...]
        解析失败返回空列表（不抛异常）
    """
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b"channel_values", data.get("channel_values", {}))
        if isinstance(cv, bytes):
            cv = msgpack.unpackb(cv)
        if not isinstance(cv, dict):
            return []

        raw_messages = _extract_messages_list(cv)
        result = []
        for msg in raw_messages:
            parsed = _extract_one(msg)
            if parsed:
                result.append(parsed)
        return result
    except Exception as e:
        logger.warning("解析 checkpoint 消息列表失败（可能为 langgraph 版本升级导致格式变更）: %s", e)
        return []


def parse_first_message(blob: bytes) -> str:
    """从 msgpack 编码的 checkpoint 中提取第一条用户消息（用于会话列表预览）"""
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b"channel_values", data.get("channel_values", {}))
        if isinstance(cv, bytes):
            cv = msgpack.unpackb(cv)
        if not isinstance(cv, dict):
            return ""

        raw_messages = _extract_messages_list(cv)
        if not raw_messages:
            return ""
        parsed = _extract_one(raw_messages[0])
        if parsed and parsed["role"] == "user":
            return parsed["content"][:100]
        return ""
    except Exception as e:
        logger.warning("解析 checkpoint 首条消息失败: %s", e)
        return ""


def parse_checkpoint_ts(blob: bytes) -> str:
    """从 msgpack 编码的 checkpoint 中提取 ISO 时间戳"""
    try:
        data = msgpack.unpackb(blob)
        ts = data.get(b"ts", data.get("ts", b""))
        if isinstance(ts, bytes):
            ts = ts.decode()
        return ts or ""
    except Exception as e:
        logger.warning("解析 checkpoint 时间戳失败: %s", e)
        return ""
