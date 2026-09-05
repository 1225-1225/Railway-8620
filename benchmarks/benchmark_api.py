#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway-8620 API 性能压测脚本（纯 Python，零额外依赖）

功能：
  1. 自动注册一个测试用户（或复用已有用户）
  2. 用线程池并发发送请求到 /chat 接口
  3. 统计 QPS、P50/P95/P99 延迟、成功率
  4. 可选输出 JSON 结果文件

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


def parse_args():
    parser = argparse.ArgumentParser(description="Railway-8620 API 压测")
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


def send_one(client: httpx.Client, token: str, message: str) -> tuple[float, int]:
    """发送单个请求，返回 (耗时秒, 状态码)"""
    start = time.perf_counter()
    resp = client.post(
        "/chat",
        json={"message": message, "session_id": "benchmark"},
        headers={"Authorization": f"Bearer {token}"},
    )
    elapsed = time.perf_counter() - start
    return elapsed, resp.status_code


def percentile(sorted_latencies: list[float], p: float) -> float:
    """计算百分位延迟（毫秒）"""
    if not sorted_latencies:
        return 0.0
    idx = min(len(sorted_latencies) - 1, int(len(sorted_latencies) * p))
    return sorted_latencies[idx] * 1000  # 秒 → 毫秒


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
    latencies: list[float] = []
    status_codes: list[int] = []
    errors: list[str] = []

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        # 每个线程一个独立 client（httpx 连接池线程安全，但独立更干净）
        futures = []
        for i in range(args.requests):
            client = httpx.Client(base_url=args.base_url, timeout=120)
            futures.append(pool.submit(send_one, client, token, args.message))

        for fut in as_completed(futures):
            try:
                elapsed, code = fut.result()
                latencies.append(elapsed)
                status_codes.append(code)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
            finally:
                pass

    total_time = time.perf_counter() - start_time

    # 3. 统计
    success = sum(1 for c in status_codes if c < 500)
    qps = args.requests / total_time if total_time > 0 else 0
    sorted_lat = sorted(latencies)

    print("\n📊 压测结果:")
    print(f"   总耗时     : {total_time:.2f}s")
    print(f"   QPS        : {qps:.1f} req/s")
    print(f"   成功率     : {success}/{args.requests} ({success / args.requests * 100:.1f}%)")
    if sorted_lat:
        print(f"   平均延迟   : {statistics.mean(sorted_lat) * 1000:.0f} ms")
        print(f"   P50 延迟   : {percentile(sorted_lat, 0.50):.0f} ms")
        print(f"   P95 延迟   : {percentile(sorted_lat, 0.95):.0f} ms")
        print(f"   P99 延迟   : {percentile(sorted_lat, 0.99):.0f} ms")
    if errors:
        print(f"   异常数     : {len(errors)}")
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
            "latency_ms": {
                "avg": round(statistics.mean(sorted_lat) * 1000, 1) if sorted_lat else 0,
                "p50": round(percentile(sorted_lat, 0.50), 1),
                "p95": round(percentile(sorted_lat, 0.95), 1),
                "p99": round(percentile(sorted_lat, 0.99), 1),
            },
            "errors": errors[:10],
        }
        out_path = Path(args.output)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 结果已保存至 {out_path}")


if __name__ == "__main__":
    main()
