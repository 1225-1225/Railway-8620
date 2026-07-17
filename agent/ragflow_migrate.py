"""
将现有 cleaned_txts 中的纯文本数据迁移到 RAGFlow 知识库。

用法：
    python agent/ragflow_migrate.py

前提：
    - RAGFlow 服务已启动
    - .env 中配置了 ragflow_host, ragflow_api_key, ragflow_dataset_id
    - 在 RAGFlow Web UI 中已创建知识库
"""

import os
import sys
from pathlib import Path

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from settings import settings as config_data
from agent.ragflow_client import RAGFlowClient


def main():
    print("=" * 60)
    print("RAGFlow 数据迁移工具")
    print("将 data/cleaned_txts/ 中的文本上传到 RAGFlow 知识库")
    print("=" * 60)

    # 检查配置
    if not config_data.ragflow_api_key:
        print("❌ 错误: 未配置 ragflow_api_key，请在 .env 中设置")
        return
    if not config_data.ragflow_dataset_id:
        print("❌ 错误: 未配置 ragflow_dataset_id，请在 .env 中设置")
        return

    client = RAGFlowClient(
        host=config_data.ragflow_host,
        api_key=config_data.ragflow_api_key,
        dataset_id=config_data.ragflow_dataset_id,
    )

    # 先测试连接
    print(f"\n📡 测试连接到 RAGFlow: {config_data.ragflow_host}")
    datasets = client.list_datasets()
    if not datasets:
        print("⚠️  无法获取知识库列表，请确认：")
        print("   1. RAGFlow 服务是否运行")
        print(f"   2. API Key 是否正确")
        print(f"   3. 知识库 ID ({config_data.ragflow_dataset_id}) 是否存在")
        print("\n   继续尝试上传...")
    else:
        print(f"✅ 连接成功，找到 {len(datasets)} 个知识库")

    # 扫描 txt 文件
    txt_dir = Path(config_data.data_path)
    if not txt_dir.exists():
        print(f"❌ 目录不存在: {txt_dir}")
        return

    txt_files = sorted(txt_dir.glob("*.txt"))
    if not txt_files:
        print(f"⚠️  在 {txt_dir} 中未找到 .txt 文件")
        return

    print(f"\n📂 找到 {len(txt_files)} 个文本文件，开始上传...")
    success = 0
    failed = 0

    for txt_file in txt_files:
        print(f"  → 上传: {txt_file.name} ... ", end="", flush=True)
        try:
            ok = client.upload_document(str(txt_file))
            if ok:
                print("✅")
                success += 1
            else:
                print("❌")
                failed += 1
        except Exception as e:
            print(f"❌ ({e})")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"迁移完成: 成功 {success} 个, 失败 {failed} 个")
    print(f"\n💡 后续操作：")
    print(f"   1. 访问 RAGFlow Web UI 查看/管理文档")
    print(f"   2. 如有解析配置需要调整，可在 UI 中删除文档后重新上传")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()