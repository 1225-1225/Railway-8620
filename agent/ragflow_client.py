"""
RAGFlow API 客户端封装

通过 REST API 对接 RAGFlow 知识库，替代原有的 Chroma 向量检索。
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger("tool_calls")


class RAGFlowClient:
    """RAGFlow 检索客户端"""

    def __init__(
        self,
        host: str = "http://localhost:9380",
        api_key: str = "",
        dataset_id: str = "",
    ):
        self.base_url = host.rstrip("/")
        self.api_key = api_key
        self.dataset_id = dataset_id
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        if self.api_key:
            self._session.headers["Authorization"] = f"Bearer {self.api_key}"

    def search(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> list[dict]:
        """检索知识库

        Args:
            query: 查询文本
            top_k: 返回结果数量
            similarity_threshold: 相似度阈值 (0.0 ~ 1.0)

        Returns:
            list[dict]: 每个元素包含:
                - content: 文本内容
                - source: 来源文件名
                - similarity: 相似度分数
                - img_id: 图片ID（如有）
        """
        url = f"{self.base_url}/api/v1/retrieval"
        payload = {
            "question": query,
            "dataset_ids": [self.dataset_id],
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
        }

        try:
            resp = self._session.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.error(f"RAGFlow 检索失败: {data.get('message', '未知错误')}")
                return []

            chunks = data.get("data", {}).get("chunks", [])
            results = []
            for chunk in chunks:
                results.append({
                    "content": chunk.get("content", ""),
                    "source": chunk.get("source", ""),
                    "similarity": chunk.get("similarity", 0.0),
                    "img_id": chunk.get("img_id", ""),
                })
            return results

        except requests.RequestException as e:
            logger.error(f"RAGFlow API 请求失败: {e}")
            return []

    def list_datasets(self) -> list[dict]:
        """列出所有知识库"""
        url = f"{self.base_url}/api/v1/datasets"
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", [])
            return []
        except requests.RequestException as e:
            logger.error(f"获取知识库列表失败: {e}")
            return []

    def upload_document(self, file_path: str, dataset_id: Optional[str] = None) -> bool:
        """上传文档到知识库

        Args:
            file_path: 本地文件路径
            dataset_id: 目标知识库 ID，默认使用初始化时指定的

        Returns:
            bool: 是否成功
        """
        ds_id = dataset_id or self.dataset_id
        if not ds_id:
            logger.error("未指定知识库 ID")
            return False

        url = f"{self.base_url}/api/v1/datasets/{ds_id}/documents"
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                resp = self._session.post(url, files=files, timeout=300)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0:
                    logger.info(f"上传成功: {file_path}")
                    return True
                logger.error(f"上传失败: {data.get('message', '未知错误')}")
                return False
        except requests.RequestException as e:
            logger.error(f"上传文档请求失败: {e}")
            return False

    # ================================================================
    #  以下方法用于自动化初始化（首次部署时由 ragflow_init.py 调用）
    #
    #  ⚠️ 注意：RAGFlow v0.26.4 更换了 API 端点、改用 RSA 加密密码、
    #  并且不再提供创建 API Key 的 REST 端点。
    #  推荐使用 agent/ragflow_init.py 通过 docker exec 完成初始化。
    # ================================================================

    def register(self, email: str, password: str, nickname: str = "admin") -> bool:
        """注册 RAGFlow 用户 (v0.26.4)

        POST /api/v1/users

        Args:
            email: 邮箱（用户名）
            password: 密码（明文）
            nickname: 昵称

        Returns:
            bool: 是否成功
        """
        url = f"{self.base_url}/api/v1/users"
        try:
            # v0.26.4 注册接口需要 nickname + email + password
            resp = requests.post(url, json={
                "nickname": nickname,
                "email": email,
                "password": password,
            }, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                logger.info(f"用户注册成功: {email}")
                return True
            logger.warning(f"用户注册失败: {data.get('message', resp.text[:100])}")
            return False
        except requests.RequestException as e:
            logger.warning(f"用户注册请求失败: {e}")
            return False

    def login(self, email: str, encrypted_password: str) -> Optional[dict]:
        """登录 RAGFlow (v0.26.4)

        POST /api/v1/auth/login

        ⚠️ 密码必须先经过 RSA 加密（通过 docker exec 调用 crypt()）。

        Args:
            email: 邮箱
            encrypted_password: RSA 加密后的密码

        Returns:
            Optional[dict]: 包含 access_token 等字段的完整响应 data，
                           失败返回 None
        """
        url = f"{self.base_url}/api/v1/auth/login"
        try:
            resp = requests.post(url, json={
                "email": email,
                "password": encrypted_password,
            }, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                logger.info(f"登录成功: {email}")
                return data.get("data", {})
            logger.error(f"登录失败: {data.get('message', resp.text[:100])}")
            return None
        except requests.RequestException as e:
            logger.error(f"登录请求失败: {e}")
            return None

    def create_api_key(self, token: str) -> Optional[str]:
        """创建 API Key

        ⚠️ RAGFlow v0.26.4 没有公开的 REST 端点用于创建 API Key。
        请使用 agent/ragflow_init.py 中的 docker exec 方式，
        或手动在 Web UI (http://localhost:9380) 中创建。

        Returns:
            None（已废弃）
        """
        logger.warning(
            "create_api_key: v0.26.4 不再提供此 REST 端点，"
            "请通过 Web UI 或 docker exec 创建"
        )
        return None

    def create_dataset(self, token: str, name: str = "铁路知识库") -> Optional[str]:
        """创建知识库 (v0.26.4)

        POST /api/v1/datasets

        ⚠️ v0.26.4 使用 session cookie 认证，而非 Bearer token。
        推荐使用 agent/ragflow_init.py 中的完整流程。

        Args:
            token: 登录后的 access_token（用作 Bearer）
            name: 知识库名称

        Returns:
            Optional[str]: 知识库 ID，失败返回 None
        """
        url = f"{self.base_url}/api/v1/datasets"
        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {token}"
        try:
            resp = session.post(url, json={"name": name}, timeout=15)
            data = resp.json()
            if data.get("code") == 0:
                ds = data.get("data", {})
                ds_id = ds.get("id", "") or ds.get("dataset_id", "")
                if ds_id:
                    logger.info(f"知识库创建成功: {name} (id={ds_id})")
                    return ds_id
            logger.error(f"创建知识库失败: {data.get('message', resp.text[:100])}")
            return None
        except requests.RequestException as e:
            logger.error(f"创建知识库请求失败: {e}")
            return None