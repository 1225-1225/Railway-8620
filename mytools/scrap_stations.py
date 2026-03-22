#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量爬取车次经停站信息脚本（支持暂停/继续）
功能：根据合并车次文件，批量爬取每个车次的经停站信息，合并生成JSON文件
"""

import requests
from lxml import etree
import urllib3
import json
import time
import os
import sys

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 请求头配置
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
}


def get_train_stations(train_number):
    """
    获取指定车次的经停站信息
    返回格式：{'1': '合肥', '2': '六安', ...} 或 None（失败时）
    """
    url = f"https://www.liecheba.com/{train_number.lower()}.html"

    try:
        # 添加随机延迟，避免请求过快被封
        time.sleep(0.5)

        response = requests.get(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        html_content = response.content

        # 解析HTML
        parser = etree.HTMLParser()
        tree = etree.fromstring(html_content, parser)

        # 定位到经停站表格（div class="table-inner" 下的 tbody）
        table_xpath = '//div[contains(@class, "table-inner")]//tbody'
        tbody = tree.xpath(table_xpath)

        if not tbody:
            print(f"    未找到 {train_number} 的经停站表格")
            return None

        # 提取经停站数据
        stations = {}
        for row in tbody[0].xpath('./tr'):
            tds = row.xpath('./td')
            if len(tds) >= 2:  # 确保至少有2列数据（序号、站点名称）
                # 第一列是序号，第二列是站点名称
                seq_num = tds[0].xpath('string(.)').strip()
                station_name = tds[1].xpath('string(.)').strip()

                if seq_num and station_name and seq_num.isdigit():
                    stations[seq_num] = station_name

        if stations:
            print(f"    成功获取 {train_number} 的 {len(stations)} 个站点")
            return stations
        else:
            print(f"    {train_number} 未获取到站点数据")
            return None

    except requests.RequestException as e:
        print(f"    请求 {train_number} 失败: {e}")
        return None
    except Exception as e:
        print(f"    解析 {train_number} 数据时出错: {e}")
        return None


def save_checkpoint(results, current_index, total_count):
    """
    保存检查点，支持断点续传
    """
    checkpoint = {
        'results': results,
        'current_index': current_index,
        'total_count': total_count,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    try:
        with open('scrape_checkpoint.json', 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存检查点失败: {e}")


def load_checkpoint():
    """
    加载检查点，返回之前的进度
    """
    if os.path.exists('scrape_checkpoint.json'):
        try:
            with open('scrape_checkpoint.json', 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
                return checkpoint
        except Exception as e:
            print(f"加载检查点失败: {e}")
    return None


def check_pause():
    """
    检查是否需要暂停
    """
    try:
        # 检查是否存在暂停标志文件
        if os.path.exists('pause_scrape.flag'):
            return True
    except:
        pass
    return False


def read_train_numbers():
    """
    读取合并车次文件，返回车次列表
    格式：[{'name': 'Z227', 'class': '直特'}, ...]
    """
    if not os.path.exists('../data/合并车次.txt'):
        print("错误：找不到 '合并车次.txt' 文件")
        return []

    trains = []
    try:
        with open('../data/合并车次.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '-' in line:
                    parts = line.split('-')
                    if len(parts) == 2:
                        train_name, train_class = parts
                        trains.append({
                            'name': train_name.strip(),
                            'class': train_class.strip()
                        })

    except Exception as e:
        print(f"读取合并车次文件时出错: {e}")
        return []

    return trains


def create_pause_flag():
    """创建暂停标志文件"""
    try:
        with open('pause_scrape.flag', 'w') as f:
            f.write('pause')
        print("暂停信号已发送")
    except Exception as e:
        print(f"创建暂停标志文件失败: {e}")


def remove_pause_flag():
    """移除暂停标志文件"""
    try:
        if os.path.exists('pause_scrape.flag'):
            os.remove('pause_scrape.flag')
            print("暂停标志已移除，可以继续运行")
    except Exception as e:
        print(f"移除暂停标志文件失败: {e}")


def show_help():
    """显示帮助信息"""
    print("""
    使用方法：
    python scrape_all_trains.py [命令]

    命令选项：
    - 无参数：开始爬取（如果存在检查点，则从上次停止处继续）
    - pause: 暂停正在运行的爬取任务
    - resume: 继续暂停的任务
    - reset: 重置所有进度，重新开始
    - help: 显示帮助信息

    暂停功能使用说明：
    1. 在另一个终端窗口运行：python scrape_all_trains.py pause
    2. 等待当前车次处理完成后，程序会自动暂停并保存进度
    3. 要继续运行，执行：python scrape_all_trains.py resume
    """)


def main():
    """
    主函数：批量爬取车次经停站信息并生成JSON文件
    """
    # 检查命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == 'pause':
            create_pause_flag()
            return
        elif command == 'resume':
            remove_pause_flag()
        elif command == 'reset':
            # 重置：删除检查点文件
            try:
                if os.path.exists('scrape_checkpoint.json'):
                    os.remove('scrape_checkpoint.json')
                    print("检查点已清除，下次运行将重新开始")
                else:
                    print("没有找到检查点文件")
            except Exception as e:
                print(f"清除检查点失败: {e}")
            return
        elif command == 'help':
            show_help()
            return
        else:
            print(f"未知命令: {command}")
            show_help()
            return

    print("=" * 60)
    print("开始批量爬取车次经停站信息")
    print("=" * 60)

    # 读取车次列表
    trains = read_train_numbers()
    if not trains:
        print("未找到车次数据，程序退出")
        return

    print(f"共 {len(trains)} 个车次需要处理")

    # 尝试加载检查点
    checkpoint = load_checkpoint()
    if checkpoint:
        results = checkpoint['results']
        start_index = checkpoint['current_index']
        print(f"检测到检查点，从第 {start_index + 1} 个车次继续")
        print(f"已成功爬取 {len(results)} 个车次")
    else:
        results = []
        start_index = 0
        print("开始新的爬取任务")

    print()

    # 结果统计
    success_count = len(results)
    fail_count = start_index - len(results)

    # 逐个处理车次
    for i in range(start_index, len(trains)):
        train = trains[i]
        train_name = train['name']
        train_class = train['class']

        print(f"[{i + 1}/{len(trains)}] 正在处理 {train_name} ({train_class})...")

        # 检查是否需要暂停
        if check_pause():
            print("\n检测到暂停信号，保存进度后退出...")
            save_checkpoint(results, i, len(trains))
            print(f"进度已保存，下次运行将从第 {i + 1} 个车次继续")
            return

        # 获取经停站信息
        stations = get_train_stations(train_name)

        if stations:
            success_count += 1
            results.append({
                'name': train_name,
                'class': train_class,
                'stations': stations
            })
        else:
            fail_count += 1
            print(f"    {train_name} 获取失败，跳过")

        # 每处理10个车次保存一次检查点
        if (i + 1) % 10 == 0:
            save_checkpoint(results, i + 1, len(trains))

        # 每50个车次显示一次进度
        if (i + 1) % 50 == 0:
            print(f"\n进度: {i + 1}/{len(trains)} 成功: {success_count} 失败: {fail_count}\n")

    # 保存最终结果
    output_file = '../data/train_data.json'
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # 清除检查点文件
        if os.path.exists('scrape_checkpoint.json'):
            os.remove('scrape_checkpoint.json')

        print("\n" + "=" * 60)
        print("爬取完成！")
        print(f"总处理车次: {len(trains)}")
        print(f"成功获取: {success_count}")
        print(f"获取失败: {fail_count}")
        print(f"结果已保存至: {output_file}")
        print("=" * 60)

    except Exception as e:
        print(f"保存JSON文件时出错: {e}")


if __name__ == "__main__":
    main()
