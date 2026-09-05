#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway-8620 Locust 压测脚本（可选，更专业的分布式压测）

用法：
    pip install locust
    locust -f benchmarks/locustfile.py --host http://localhost:8000
    然后打开 http://localhost:8080 配置并发数与速率

说明：
    - 每个虚拟用户启动时注册/登录一次，复用 JWT token
    - 压测 /chat 非流式接口（结果更稳定，便于对比）
"""

from locust import HttpUser, between, task

TEST_USERNAME = "locust_user"
TEST_PASSWORD = "locust_pass_123"


class RailwayChatUser(HttpUser):
    """模拟真实用户：登录后持续提问"""

    wait_time = between(1, 3)  # 每个用户两次请求间隔 1~3 秒

    def on_start(self):
        """每个虚拟用户启动时注册/登录，获取 token"""
        # 尝试注册（首次）
        resp = self.client.post(
            "/auth/register",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        if resp.status_code != 200:
            # 已存在则登录
            resp = self.client.post(
                "/auth/login",
                data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
        self.token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def chat(self):
        """非流式对话（权重 3）"""
        self.client.post(
            "/chat",
            json={"message": "介绍一下前进型蒸汽机车", "session_id": "locust"},
            headers=self.headers,
        )

    @task(1)
    def list_sessions(self):
        """历史会话列表（权重 1）"""
        self.client.get("/chat/sessions", headers=self.headers)
