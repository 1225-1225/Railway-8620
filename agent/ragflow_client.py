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
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

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