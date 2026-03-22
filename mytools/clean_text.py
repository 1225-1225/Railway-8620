#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ND5型柴油机车TXT文件清理工具
支持自定义输入输出目录，批量处理文件
"""

import re
import os
from pathlib import Path
from datetime import datetime

# ==================== 配置区域 ====================
# 在此处修改输入输出目录路径

# 输入目录（存放原始txt文件）
INPUT_DIR = r"../data/txts"  # 可修改为绝对路径，如 r"D:\RailwayData\ND5\input"

# 输出目录（存放清理后的txt文件）
OUTPUT_DIR = r"../data/cleaned_txts"  # 可修改为绝对路径，如 r"D:\RailwayData\ND5\output"

# 文件匹配模式（支持通配符）
FILE_PATTERN = "*.txt"  # 可修改为 "ND5*.txt" 或 "*.md" 等

# 是否保留标题结构（True=保留，False=完全移除）
KEEP_STRUCTURE = True

# 是否生成处理报告
GENERATE_REPORT = True


# ==================== 清理函数 ====================

def clean_text_content(content, keep_structure=True):
    """
    清理文本内容中的格式标记

    Args:
        content: 原始文本内容
        keep_structure: 是否保留标题结构

    Returns:
        清理后的文本内容
    """
    original_size = len(content)

    # 1. 移除Markdown标题标记
    if keep_structure:
        content = re.sub(r'^##\s*(.+)$', r'\n=== \1 ===\n', content, flags=re.MULTILINE)
        content = re.sub(r'^###\s*(.+)$', r'\n--- \1 ---\n', content, flags=re.MULTILINE)
        content = re.sub(r'^####\s*(.+)$', r'\n*** \1 ***\n', content, flags=re.MULTILINE)
    else:
        content = re.sub(r'^#{1,6}\s*', '', content, flags=re.MULTILINE)

    # 2. 移除所有链接格式，保留文字 [文字](URL) -> 文字
    content = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', content)
    content = re.sub(r'\[([^\]]+)\]\(http://[^\)]+\)', r'\1', content)

    # 3. 移除所有图片标记
    content = re.sub(r'\[!\[[^\]]*\]\([^\)]+\)\]\([^\)]+\)', '', content)
    content = re.sub(r'\[!\[[^\]]*\]\([^\)]+\)', '', content)
    content = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', content)

    # 4. 移除引用标记 [[数字]](URL) 和 [[数字]]
    content = re.sub(r'\[\[\d+\]\]\(https?://[^\)]+\)', '', content)
    content = re.sub(r'\[\[\d+\]\]', '', content)

    # 5. 清理表格格式
    # content = re.sub(r'^\|[-:\s|]+\|\s*$', '', content, flags=re.MULTILINE)
    # content = re.sub(r'^\|\s*', '', content, flags=re.MULTILINE)
    # content = re.sub(r'\s*\|\s*$', '', content, flags=re.MULTILINE)
    # content = re.sub(r'\s*\|\s*', ' | ', content)

    # 6. 移除HTML标签
    content = re.sub(r'<[^>]+>', '', content)

    # 7. 清理特殊字符
    content = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', content)  # 零宽字符
    content = re.sub(r' {2,}', ' ', content)  # 多个空格变单个
    content = re.sub(r'\t', '    ', content)  # 制表符变空格

    # 8. 清理空行（保留最多2个连续空行）
    content = re.sub(r'\n{3,}', '\n\n', content)

    # 9. 移除目录行（- [1.1 标题](URL) 格式）
    content = re.sub(r'^-\s*\[\d+\.?\d*\s*[^\]]*\]\(https?://[^\)]+\)\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^-\s*\[\d+\.?\d*\s*[^\]]*\]\s*$', '', content, flags=re.MULTILINE)

    # 10. 移除纯符号行
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not re.match(r'^[\s\-\|\*\=\#]+$', stripped):
            cleaned_lines.append(line)
    content = '\n'.join(cleaned_lines)

    # 11. 移除纯URL行
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not re.match(r'^https?://\S+$', stripped):
            cleaned_lines.append(line)
    content = '\n'.join(cleaned_lines)

    # 12. 最终清理
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.strip()

    new_size = len(content)
    reduction = (1 - new_size / original_size) * 100 if original_size > 0 else 0

    return content, original_size, new_size, reduction


def process_single_file(input_path, output_path, keep_structure=True):
    """
    处理单个文件

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        keep_structure: 是否保留标题结构

    Returns:
        处理结果字典
    """
    result = {
        'input_file': str(input_path),
        'output_file': str(output_path),
        'success': False,
        'original_size': 0,
        'cleaned_size': 0,
        'reduction': 0,
        'error': None
    }

    try:
        # 读取文件
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 清理内容
        cleaned_content, orig_size, new_size, reduction = clean_text_content(
            content, keep_structure=keep_structure
        )

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)

        result['success'] = True
        result['original_size'] = orig_size
        result['cleaned_size'] = new_size
        result['reduction'] = reduction

    except Exception as e:
        result['error'] = str(e)

    return result


def batch_process_files(input_dir, output_dir, file_pattern="*.txt", keep_structure=True):
    """
    批量处理文件

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        file_pattern: 文件匹配模式
        keep_structure: 是否保留标题结构

    Returns:
        处理结果列表
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # 检查输入目录
    if not input_path.exists():
        print(f"❌ 错误: 输入目录 '{input_dir}' 不存在!")
        return []

    if not input_path.is_dir():
        print(f"❌ 错误: '{input_dir}' 不是目录!")
        return []

    # 创建输出目录（如果不存在）
    output_path.mkdir(parents=True, exist_ok=True)

    # 获取所有匹配的文件
    files = list(input_path.glob(file_pattern))

    if not files:
        print(f"⚠️  警告: 在 '{input_dir}' 中未找到匹配 '{file_pattern}' 的文件")
        return []

    print(f"📁 找到 {len(files)} 个文件待处理")
    print("-" * 60)

    results = []
    for i, input_file in enumerate(files, 1):
        # 生成输出文件名（添加_清理后后缀）
        output_file = output_path / f"{input_file.stem}_清理后{input_file.suffix}"

        print(f"[{i}/{len(files)}] 处理: {input_file.name}")

        # 处理文件
        result = process_single_file(input_file, output_file, keep_structure)
        results.append(result)

        # 显示结果
        if result['success']:
            print(f"    ✅ 成功 | 原始: {result['original_size']:,} 字符 | "
                  f"清理: {result['cleaned_size']:,} 字符 | "
                  f"压缩: {result['reduction']:.2f}%")
        else:
            print(f"    ❌ 失败 | 错误: {result['error']}")

    print("-" * 60)

    return results


def generate_report(results, output_dir, report_name="处理报告.txt"):
    """
    生成处理报告

    Args:
        results: 处理结果列表
        output_dir: 输出目录
        report_name: 报告文件名
    """
    if not results:
        return

    report_path = Path(output_dir) / report_name

    # 统计信息
    total_files = len(results)
    success_files = sum(1 for r in results if r['success'])
    failed_files = total_files - success_files
    total_original = sum(r['original_size'] for r in results if r['success'])
    total_cleaned = sum(r['cleaned_size'] for r in results if r['success'])
    avg_reduction = sum(r['reduction'] for r in results if r['success']) / success_files if success_files > 0 else 0

    # 生成报告内容
    report_content = f"""
================================================================================
                        ND5型柴油机车TXT文件清理处理报告
================================================================================

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

--------------------------------------------------------------------------------
                                   统计摘要
--------------------------------------------------------------------------------

总处理文件数:     {total_files} 个
成功处理:         {success_files} 个
处理失败:         {failed_files} 个
成功率:           {success_files / total_files * 100:.2f}% (如有成功文件)

原始总大小:       {total_original:,} 字符
清理后总大小:     {total_cleaned:,} 字符
总压缩率:         {(1 - total_cleaned / total_original) * 100:.2f}% (如有成功文件)
平均压缩率:       {avg_reduction:.2f}%

--------------------------------------------------------------------------------
                                   文件详情
--------------------------------------------------------------------------------

"""

    for i, result in enumerate(results, 1):
        status = "✅ 成功" if result['success'] else "❌ 失败"
        report_content += f"""
[{i}] {Path(result['input_file']).name}
    状态: {status}
    输入: {result['input_file']}
    输出: {result['output_file']}
"""
        if result['success']:
            report_content += f"""    原始大小: {result['original_size']:,} 字符
    清理大小: {result['cleaned_size']:,} 字符
    压缩率: {result['reduction']:.2f}%
"""
        else:
            report_content += f"""    错误: {result['error']}
"""

    report_content += """
================================================================================
                                   结束
================================================================================
"""

    # 写入报告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"📄 处理报告已生成: {report_path}")


# ==================== 主程序 ====================

def main():
    """主程序入口"""
    print("=" * 60)
    print("        ND5型柴油机车TXT文件清理工具")
    print("=" * 60)
    print()
    print(f"📂 输入目录: {os.path.abspath(INPUT_DIR)}")
    print(f"📂 输出目录: {os.path.abspath(OUTPUT_DIR)}")
    print(f"📄 文件模式: {FILE_PATTERN}")
    print(f"📋 保留结构: {'是' if KEEP_STRUCTURE else '否'}")
    print(f"📊 生成报告: {'是' if GENERATE_REPORT else '否'}")
    print()
    print("=" * 60)
    print()

    # 批量处理文件
    results = batch_process_files(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        file_pattern=FILE_PATTERN,
        keep_structure=KEEP_STRUCTURE
    )

    # 生成报告
    if GENERATE_REPORT and results:
        print()
        generate_report(results, OUTPUT_DIR)

    # 总结
    print()
    print("=" * 60)
    if results:
        success_count = sum(1 for r in results if r['success'])
        print(f"🎉 处理完成! 成功: {success_count}/{len(results)} 个文件")
        print(f"💾 输出目录: {os.path.abspath(OUTPUT_DIR)}")
    else:
        print("⚠️  没有文件被处理")
    print("=" * 60)


if __name__ == '__main__':
    main()