#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高铁网站数据爬虫
爬取全国各城市火车站信息并生成JSON文件
"""

import requests
from bs4 import BeautifulSoup
import json
import re

# 网站基础URL
BASE_URL = "https://shike.gaotie.cn/chengshichezhan/"


def get_city_list():
    """
    获取所有城市列表
    从主页解析出所有城市链接
    """
    # 先访问主页获取所有城市列表
    # 从你提供的图片看，城市列表在特定的table中
    # 我们需要先获取主页，然后解析所有城市链接

    # 根据HTML结构，城市链接格式为：
    # https://shike.gaotie.cn/chengshi/?chengshi=<URL编码的城市名>

    # 从图片中看到的城市列表（主要城市）
    main_cities = [
        "北京", "上海", "广州", "深圳", "天津", "重庆", "杭州", "西安", "成都", "郑州",
        "南京", "武汉", "长沙", "青岛", "大连", "厦门", "福州", "昆明", "贵阳", "南宁",
        "哈尔滨", "沈阳", "济南", "太原", "石家庄", "兰州", "西宁", "银川", "乌鲁木齐", "拉萨",
        "呼和浩特", "长春", "南昌", "苏州", "宁波", "合肥", "海口", "三亚", "桂林", "丽江",
        "三亚", "张家界", "黄山", "九寨沟", "敦煌", "喀什", "拉萨", "桂林", "北海", "威海",
        "烟台", "淄博", "潍坊", "日照", "临沂", "泰安", "济宁", "德州", "聊城", "滨州",
        "菏泽", "东营", "枣庄", "莱芜", "威海", "烟台", "青岛", "淄博", "潍坊", "日照"
    ]

    # 从A开头的城市开始爬取（按字母顺序）
    # 根据你的截图，从"阿坝"开始
    cities = []

    # 尝试获取完整的城市列表
    try:
        url = "https://shike.gaotie.cn/chengshichezhan/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'  # 使用gbk编码

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找所有符合要求的table
        tables = soup.find_all('table', {'width': '100%', 'border': '0', 'cellpadding': '4', 'cellspacing': '1'})

        city_links = []
        for table in tables:
            try:
                tbody = table.find('tbody')
                if tbody:
                    trs = tbody.find_all('tr', recursive=False)
                    if len(trs) >= 1:
                        first_tr = trs[0]
                        td = first_tr.find('td')
                        if td:
                            a = td.find('a')
                            if a:
                                b = a.find('b')
                                if b:
                                    city_name = b.get_text(strip=True)
                                    href = a.get('href', '')
                                    if href:
                                        city_links.append({
                                            'name': city_name,
                                            'url': href
                                        })
                                        print(f"找到城市: {city_name}")
            except Exception as e:
                continue

        print(f"共找到 {len(city_links)} 个城市")
        return city_links

    except Exception as e:
        print(f"获取城市列表失败: {e}")
        # 返回空列表，使用手动爬取方式
        return []


def parse_city_page(city_url, city_name):
    """
    解析单个城市的车站信息
    """
    try:
        # 如果是相对路径，添加基础URL
        if not city_url.startswith('http'):
            city_url = BASE_URL + city_url.split('chengshi/')[-1]

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        print(f"正在爬取: {city_name} - {city_url}")
        response = requests.get(city_url, headers=headers, timeout=10)
        response.encoding = 'gbk'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找所有符合条件的table
        tables = soup.find_all('table', {'width': '100%', 'border': '0', 'cellpadding': '4', 'cellspacing': '1'})

        city_data = {
            'city_name': city_name,
            'stations': [],
            'city_station_count': 0
        }

        for table in tables:
            try:
                tbody = table.find('tbody')
                if tbody:
                    trs = tbody.find_all('tr', recursive=False)

                    # 第一个tr包含城市名（已经知道，跳过）
                    # 第二个tr包含车站信息
                    if len(trs) >= 2:
                        second_tr = trs[1]
                        tds = second_tr.find_all('td')

                        for td in tds:
                            # 查找td下的a标签下的font标签
                            a_tag = td.find('a')
                            if a_tag:
                                font_tag = a_tag.find('font')
                                if font_tag:
                                    station_name = font_tag.get_text(strip=True)
                                    if station_name and '站' in station_name:
                                        city_data['stations'].append(station_name)
            except Exception as e:
                continue

        city_data['city_station_count'] = len(city_data['stations'])

        if city_data['stations']:
            print(f"  {city_name}: {len(city_data['stations'])} 个车站 - {city_data['stations']}")

        return city_data

    except Exception as e:
        print(f"  解析 {city_name} 失败: {e}")
        return {
            'city_name': city_name,
            'stations': [],
            'city_station_count': 0
        }


def main():
    """
    主函数
    """
    print("开始爬取高铁网站数据...")
    print("=" * 60)

    # 获取所有城市列表
    city_links = get_city_list()

    all_cities_data = []

    if city_links:
        # 使用获取到的城市列表
        for city in city_links:
            city_data = parse_city_page(city['url'], city['name'])
            if city_data['stations']:
                all_cities_data.append(city_data)
    else:
        # 手动指定一些城市进行测试
        # 从你提供的截图看，从"阿坝"开始
        test_cities = [
            ('%B0%A2%B0%D3%B2%D8%D7%E5%C7%BC%D7%E5%D4%D6%CE%D6%DD', '阿坝藏族羌族自治州'),
            ('%B0%A2%BF%CB%CB%D5', '阿克苏'),
            ('%B0%A2%C0%AD%C9%B3', '阿拉善'),
        ]

        for city_code, city_name in test_cities:
            city_url = f"{BASE_URL}?chengshi={city_code}"
            city_data = parse_city_page(city_url, city_name)
            if city_data['stations']:
                all_cities_data.append(city_data)

    # 统计总数
    total_cities = len(all_cities_data)
    total_stations = sum(city['city_station_count'] for city in all_cities_data)

    # 添加统计信息
    result = {
        'cities': all_cities_data,
        'city_count': total_cities,
        'station_count': total_stations
    }

    # 保存到JSON文件
    output_file = 'gaotie_stations.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"爬取完成！")
    print(f"城市总数: {total_cities}")
    print(f"车站总数: {total_stations}")
    print(f"数据已保存到: {output_file}")

    # 显示部分数据预览
    if all_cities_data:
        print("\n数据预览:")
        for city in all_cities_data[:5]:
            print(f"  {city['city_name']}: {city['city_station_count']} 个车站")


if __name__ == '__main__':
    main()
