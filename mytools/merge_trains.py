#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
合并车次数据脚本
功能：将多个车次文件去重后合并到一个txt文件中，格式为：车次-类型
"""

import os

# 定义所有需要处理的文件
file_mapping = {
    "动车.txt": "动车",
    "高速.txt": "高速",
    "特快.txt": "特快",
    "快车.txt": "快车",
    "普快.txt": "普快",
    "直特.txt": "直特",
    "普客.txt": "普客",
    "快慢.txt": "快慢"
}

def parse_train_number(line):
    """解析行中的车次号，处理 '1. G65' 这种格式"""
    line = line.strip()
    if not line:
        return None

    # 尝试分割出车次号部分
    # 格式可能是 "1. G65" 或 "G65"
    parts = line.split('.')
    if len(parts) > 1:
        train_number = parts[1].strip()
    else:
        train_number = parts[0].strip()

    return train_number if train_number else None

def merge_train_files():
    """合并所有车次文件并去重"""
    all_trains = {}  # 使用字典去重，key为车次号

    # 遍历所有文件
    for filename, train_type in file_mapping.items():
        if not os.path.exists(filename):
            print(f"警告：文件 {filename} 不存在，跳过")
            continue

        print(f"正在处理 {filename} ({train_type})...")

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    train_number = parse_train_number(line)
                    if train_number:
                        # 如果车次号已存在，检查是否需要更新类型
                        if train_number in all_trains:
                            existing_type = all_trains[train_number]
                            if existing_type != train_type:
                                print(f"  注意：车次 {train_number} 在多个文件中出现（{existing_type} 和 {train_type}），保留 {existing_type}")
                        else:
                            all_trains[train_number] = train_type
        except Exception as e:
            print(f"  错误：处理 {filename} 时出错 - {e}")

    # 按车次号排序输出
    sorted_trains = sorted(all_trains.items(), key=lambda x: x[0])

    # 写入合并后的文件
    output_file = "../data/合并车次.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        for train_number, train_type in sorted_trains:
            f.write(f"{train_number}-{train_type}\n")

    print(f"\n合并完成！")
    print(f"共收集到 {len(sorted_trains)} 个不重复的车次")
    print(f"结果已保存至 {output_file}")

    # 统计每种类型的车次数量
    type_stats = {}
    for _, train_type in sorted_trains:
        type_stats[train_type] = type_stats.get(train_type, 0) + 1

    print("\n各类型车次统计：")
    for train_type, count in sorted(type_stats.items()):
        print(f"  {train_type}: {count} 次")

if __name__ == "__main__":
    merge_train_files()
