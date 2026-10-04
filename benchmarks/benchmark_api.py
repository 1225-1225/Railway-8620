#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway-8620 API 性能压测脚本（纯 Python，零额外依赖）

压测目标：**POST /chat/stream**（SSE 流式接口）——这是前端实际使用的链路，
因此压测它比压测非流式接口更贴近真实负载。

功能：
  1. 自动注册一个测试用户（或复用已有用户）
  2. 用线程池并发发送请求到 /chat/stream，完整消费 SSE 流
  3. 统计 QPS、**TTFT（首 token 时间）**、总时长 P50/P95/P99、成功率
  4. 可选输出 JSON 结果文件

为什么同时测 TTFT 和总时长：
  - 总时长反映后端整体吞吐（受 LLM 生成速度主导）
  - TTFT 反映用户**感知**的等待——流式架构的价值就是把首字时间从"总时长"
    降到"首 token 时间"，这两个指标一起看才能说明流式的意义

用法：
    python benchmarks/benchmark_api.py
    python benchmarks/benchmark_api.py --concurrency 20 --requests 200
    python benchmarks/benchmark_api.py --base-url http://localhost:8000 --output results.json

依赖：httpx（已在 requirements.txt 中）
"""

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

# Windows 控制台默认 GBK 编码，无法输出 emoji/中文特殊字符。
# 强制 stdout/stderr 使用 UTF-8，保证脚本在 Windows 上也能正常运行。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 项目根目录（用于导入 backend 相关配置）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BASE_URL = "http://localhost:8000"
TEST_USERNAME = "benchmark_user"
TEST_PASSWORD = "benchmark_pass_123"


class Result:
    """单次请求的测量结果"""

    __slots__ = ("ttft", "total", "status", "tokens", "error")

    def __init__(self, ttft: float, total: float, status: int,
                 tokens: int = 0, error: str = ""):
        self.ttft = ttft        # 首 token 时间（秒）；未收到任何 token 时为 total
        self.total = total      # 完整响应耗时（秒）
        self.status = status
        self.tokens = tokens    # 收到的 token 事件数
        self.error = error


def parse_args():
    parser = argparse.ArgumentParser(description="Railway-8620 API 压测（SSE 流式）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="后端地址")
    parser.add_argument("--concurrency", type=int, default=10, help="并发数（默认 10）")
    parser.add_argument("--requests", type=int, default=100, help="总请求数（默认 100）")
    parser.add_argument("--output", default="", help="结果 JSON 输出路径（可选）")
    parser.add_argument("--message", default="介绍一下前进型蒸汽机车", help="压测用提问内容")
    return parser.parse_args()


def get_token(base_url: str) -> str:
    """注册（或登录）测试用户，返回 JWT token"""
    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            # 尝试注册
            resp = client.post(
                "/auth/register",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            if resp.status_code == 200:
                return resp.json()["access_token"]
            # 已存在则登录
            resp = client.post(
                "/auth/login",
                data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            if resp.status_code == 200:
                return resp.json()["access_token"]
            raise RuntimeError(f"无法获取 token: {resp.status_code} {resp.text[:200]}")
    except httpx.ConnectError as e:
        raise SystemExit(
            f"❌ 无法连接后端 {base_url}，请确认服务已启动：\n"
            f"   uvicorn backend.api:app --host 0.0.0.0 --port 8000\n"
            f"   或 docker compose up -d backend\n"
            f"   原始错误: {e}"
        ) from e


def send_one(client: httpx.Client, token: str, message: str) -> Result:
    """发送单个 SSE 流式请求并完整消费，返回 TTFT / 总时长 / token 数

    关键点：必须用 client.stream() 惰性读取，才能在第一个 chunk 到达时
    记录 TTFT；若用 client.post() 会一次性读到流结束，TTFT 就退化成总时长。
    """
    payload = {"message": message, "session_id": "benchmark"}
    headers = {"Authorization": f"Bearer {token}"}
    start = time.perf_counter()
    ttft = 0.0
    tokens = 0

    try:
        with client.stream("POST", "/chat/stream", json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                resp.read()  # 消费掉响应体，保证连接可复用
                return Result(0.0, time.perf_counter() - start, resp.status_code,
                              error=f"HTTP {resp.status_code}")

            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                if not ttft:
                    # 第一个有效事件（含 content 或 error）到达 → 记录首字时间
                    ttft = time.perf_counter() - start
                if '"content"' in data:
                    tokens += 1

        total = time.perf_counter() - start
        return Result(ttft or total, total, 200, tokens=tokens)
    except Exception as e:  # noqa: BLE001
        return Result(0.0, time.perf_counter() - start, 0, error=str(e)[:120])


def percentile(sorted_values: list[float], p: float) -> float:
    """计算百分位（输入秒，输出毫秒）"""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[idx] * 1000  # 秒 → 毫秒


def main():
    args = parse_args()

    print(f"🔧 压测配置:")
    print(f"   base-url   : {args.base_url}")
    print(f"   concurrency: {args.concurrency}")
    print(f"   requests   : {args.requests}")
    print(f"   message    : {args.message}")
    print()

    # 1. 获取 token
    print("🔑 获取测试用户 token ...")
    token = get_token(args.base_url)
    print("   ✅ 已获取 token\n")

    # 2. 并发压测
    print(f"🚀 开始压测（并发 {args.concurrency}，共 {args.requests} 请求）...")
    results: list[Result] = []
    errors: list[str] = []

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        # 每个线程一个独立 client（httpx 连接池线程安全，但独立更干净）
        clients: list[httpx.Client] = []
        futures = []
        for i in range(args.requests):
            client = httpx.Client(base_url=args.base_url, timeout=120)
            clients.append(client)
            futures.append(pool.submit(send_one, client, token, args.message))

        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:120])

        # 压测结束统一关闭连接（此前遗漏，会留下 TIME_WAIT 连接）
        for client in clients:
            client.close()

    total_time = time.perf_counter() - start_time

    # 3. 统计
    ok_results = [r for r in results if r.status == 200]
    success = len(ok_results)
    qps = args.requests / total_time if total_time > 0 else 0

    sorted_total = sorted(r.total for r in ok_results)
    sorted_ttft = sorted(r.ttft for r in ok_results)
    total_tokens = sum(r.tokens for r in ok_results)

    print("\n📊 压测结果:")
    print(f"   总耗时     : {total_time:.2f}s")
    print(f"   QPS        : {qps:.1f} req/s")
    print(f"   成功率     : {success}/{args.requests} ({success / args.requests * 100:.1f}%)")
    if total_tokens:
        print(f"   token 总数 : {total_tokens}（平均 {total_tokens / success:.0f}/请求）")
    if sorted_ttft:
        print()
        print("   ── 首 token 时间 TTFT（用户感知延迟）──")
        print(f"   平均       : {statistics.mean(sorted_ttft) * 1000:.0f} ms")
        print(f"   P50        : {percentile(sorted_ttft, 0.50):.0f} ms")
        print(f"   P95        : {percentile(sorted_ttft, 0.95):.0f} ms")
        print(f"   P99        : {percentile(sorted_ttft, 0.99):.0f} ms")
    if sorted_total:
        print()
        print("   ── 完整响应时长（含全部 token 生成）──")
        print(f"   平均       : {statistics.mean(sorted_total) * 1000:.0f} ms")
        print(f"   P50        : {percentile(sorted_total, 0.50):.0f} ms")
        print(f"   P95        : {percentile(sorted_total, 0.95):.0f} ms")
        print(f"   P99        : {percentile(sorted_total, 0.99):.0f} ms")
    if sorted_ttft and sorted_total:
        print()
        print(f"   💡 流式收益 : 首字比完整响应快 "
              f"{statistics.mean(sorted_total) / statistics.mean(sorted_ttft):.1f} 倍")
    if errors:
        print(f"\n   异常数     : {len(errors)}")
        for e in errors[:3]:
            print(f"     - {e}")

    # 4. 可选输出 JSON
    if args.output:
        result = {
            "config": vars(args),
            "total_time_s": round(total_time, 3),
            "qps": round(qps, 2),
            "success": success,
            "total": args.requests,
            "success_rate": round(success / args.requests, 4),
            "tokens_total": total_tokens,
            "ttft_ms": {
                "avg": round(statistics.mean(sorted_ttft) * 1000, 1) if sorted_ttft else 0,
                "p50": round(percentile(sorted_ttft, 0.50), 1),
                "p95": round(percentile(sorted_ttft, 0.95), 1),
                "p99": round(percentile(sorted_ttft, 0.99), 1),
            },
            "total_latency_ms": {
                "avg": round(statistics.mean(sorted_total) * 1000, 1) if sorted_total else 0,
                "p50": round(percentile(sorted_total, 0.50), 1),
                "p95": round(percentile(sorted_total, 0.95), 1),
                "p99": round(percentile(sorted_total, 0.99), 1),
            },
            "errors": errors[:10],
        }
        out_path = Path(args.output)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 结果已保存至 {out_path}")


if __name__ == "__main__":
    main()
