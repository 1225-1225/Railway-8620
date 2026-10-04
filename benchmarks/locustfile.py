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
    - 压测 **/chat/stream**（SSE 流式接口）——前端实际链路的对应压测目标
    - Locust 内置的 SSE 支持有限，因此这里只发请求不消费完整流，
      测的是"服务端建立流并开始推送"的能力；完整链路耗时请用
      benchmark_api.py（它用 httpx 惰性读取，能测 TTFT 与总时长）
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
    def chat_stream(self):
        """SSE 流式对话（权重 3）"""
        with self.client.post(
            "/chat/stream",
            json={"message": "介绍一下前进型蒸汽机车", "session_id": "locust"},
            headers=self.headers,
            stream=True,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            # 确认响应头是 SSE，且能读到第一个块就认为流已建立
            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" not in content_type:
                resp.failure(f"Content-Type 异常: {content_type}")
                return
            got_first = False
            for _ in resp.iter_lines():
                got_first = True
                break
            if got_first:
                resp.success()
            else:
                resp.failure("流中未收到任何数据")

    @task(1)
    def list_sessions(self):
        """历史会话列表（权重 1）"""
        self.client.get("/chat/sessions", headers=self.headers)
