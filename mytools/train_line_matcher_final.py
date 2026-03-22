"""
车次线路智能匹配工具（最终版本）

功能：
- 根据车次的站点顺序，智能匹配经过的铁路线路
- 支持批量处理多个车次
- 采用智能匹配策略，确保线路边界识别准确
- 输出完整的车次信息（含 line_names 属性）
- 提供详细的匹配报告和对比分析

核心策略：
1. 识别线路切换点（通过站点在线路中的位置变化）
2. 优先保留局部线路（避免被大线路吞噬）
3. 支持线路边界识别和智能切换

使用示例：
    from train_line_matcher_final import TrainLineMatcher

    matcher = TrainLineMatcher()
    result = matcher.process_trains_file("车次信息.txt", "车次信息_结果.json")
"""

import json
import re
from typing import Dict, List, Set, Tuple


class TrainLineMatcher:
    """车次线路智能匹配器（最终版本）"""

    # 完整的线路定义（支持线路间的边界识别）
    RAILWAY_LINES = {
        # 宁西铁路：合肥 → 六安（合六段）
        "宁西铁路": ["合肥", "六安"],

        # 阜六铁路：六安 → 霍邱 → 阜阳
        "阜六铁路": ["六安", "霍邱", "阜阳"],

        # 京九铁路：阜阳 → 衡水 → 北京丰台
        "京九铁路": ["阜阳", "衡水", "北京丰台"],

        # 合武铁路：合肥 → 六安 → 金寨 → 麻城 → 武汉
        "合武铁路": ["合肥", "六安", "金寨", "麻城", "武汉"],

        # 合福高铁：合肥 → 六安 → 金寨 → 黄山 → 上饶 → 南平 → 福州
        "合福高铁": ["合肥", "六安", "金寨", "黄山", "上饶", "南平", "福州"],

        # 沪汉蓉铁路：上海 → 南京 → 合肥 → 六安 → 武汉
        "沪汉蓉铁路": ["上海", "南京", "合肥", "六安", "武汉"],

        # 京沪高铁：北京南 → 济南 → 徐州 → 南京 → 上海虹桥
        "京沪高铁": ["北京南", "济南", "徐州", "南京", "上海虹桥"],

        # 京广高铁：北京西 → 郑州 → 武汉 → 长沙 → 广州南
        "京广高铁": ["北京西", "郑州", "武汉", "长沙", "广州南"],

        # 商合杭高铁：商丘 → 合肥 → 杭州
        "商合杭高铁": ["商丘", "合肥", "杭州"],

        # 杭温高铁：杭州 → 丽水 → 温州
        "杭温高铁": ["杭州", "丽水", "温州"],

        # 湖杭高铁：湖州 → 杭州
        "湖杭高铁": ["湖州", "杭州"],

        # 宁安城际：南京 → 合肥 → 安庆
        "宁安城际": ["南京", "合肥", "安庆"],

        # 合安高铁：合肥 → 安庆
        "合安高铁": ["合肥", "安庆"],

        # 安九高铁：安庆 → 九江
        "安九高铁": ["安庆", "九江"],

        # 昌赣高铁：南昌 → 赣州
        "昌赣高铁": ["南昌", "赣州"],

        # 赣深高铁：赣州 → 深圳
        "赣深高铁": ["赣州", "深圳"],

        # 广深港高铁：广州 → 深圳 → 香港
        "广深港高铁": ["广州", "深圳", "香港"],

        # 厦深高铁：厦门 → 深圳
        "厦深高铁": ["厦门", "汕头", "深圳"],

        # 福厦高铁：福州 → 厦门
        "福厦高铁": ["福州", "厦门"],

        # 温福铁路：温州 → 福州
        "温福铁路": ["温州", "福州"],

        # 金温铁路：金华 → 温州
        "金温铁路": ["金华", "温州"],

        # 杭深铁路：杭州 → 宁波 → 温州 → 福州 → 厦门 → 深圳
        "杭深铁路": ["杭州", "宁波", "温州", "福州", "厦门", "深圳"],

        # 沪昆高铁：上海 → 杭州 → 南昌 → 长沙 → 贵阳 → 昆明
        "沪昆高铁": ["上海", "杭州", "南昌", "长沙", "贵阳", "昆明"],

        # 贵广高铁：贵阳 → 广州
        "贵广高铁": ["贵阳", "广州"],

        # 南广高铁：南宁 → 广州
        "南广高铁": ["南宁", "广州"],

        # 广珠城际：广州 → 佛山 → 江门 → 珠海
        "广珠城际": ["广州", "佛山", "江门", "珠海"],

        # 长昆高铁：长沙 → 贵阳 → 昆明
        "长昆高铁": ["长沙", "贵阳", "昆明"],

        # 渝昆高铁：重庆 → 昆明
        "渝昆高铁": ["重庆", "昆明"],

        # 成渝高铁：成都 → 重庆
        "成渝高铁": ["成都", "重庆"],

        # 西成高铁：西安 → 成都
        "西成高铁": ["西安", "成都"],

        # 宝兰高铁：宝鸡 → 兰州
        "宝兰高铁": ["宝鸡", "兰州"],

        # 兰新高铁：兰州 → 西宁 → 张掖 → 嘉峪关 → 乌鲁木齐
        "兰新高铁": ["兰州", "西宁", "张掖", "嘉峪关", "乌鲁木齐"],

        # 京张高铁：北京 → 张家口
        "京张高铁": ["北京", "张家口"],

        # 呼包高铁：呼和浩特 → 包头
        "呼包高铁": ["呼和浩特", "包头"],

        # 京哈高铁：北京 → 沈阳 → 长春 → 哈尔滨
        "京哈高铁": ["北京", "沈阳", "长春", "哈尔滨"],

        # 哈大高铁：哈尔滨 → 长春 → 沈阳 → 大连
        "哈大高铁": ["哈尔滨", "长春", "沈阳", "大连"],

        # 济青高铁：济南 → 青岛
        "济青高铁": ["济南", "青岛"],

        # 青荣城际：青岛 → 烟台 → 威海 → 荣成
        "青荣城际": ["青岛", "烟台", "威海", "荣成"],

        # 石武高铁：石家庄 → 郑州 → 武汉
        "石武高铁": ["石家庄", "郑州", "武汉"],

        # 武广高铁：武汉 → 长沙 → 广州
        "武广高铁": ["武汉", "长沙", "广州"],

        # 昆广高铁：昆明 → 贵阳 → 广州
        "昆广高铁": ["昆明", "贵阳", "广州"],

        # 九景衢铁路：九江 → 景德镇 → 衢州
        "九景衢铁路": ["九江", "景德镇", "衢州"],

        # 杭绍台高铁：杭州 → 绍兴 → 台州
        "杭绍台高铁": ["杭州", "绍兴", "台州"],

        # 沪苏通铁路：上海 → 苏州 → 南通
        "沪苏通铁路": ["上海", "苏州", "南通"],

        # 通苏嘉甬铁路：南通 → 苏州 → 嘉兴 → 宁波
        "通苏嘉甬铁路": ["南通", "苏州", "嘉兴", "宁波"],

        # 金甬铁路：金华 → 宁波
        "金甬铁路": ["金华", "宁波"],

        # 义甬舟铁路：义乌 → 宁波 → 舟山
        "义甬舟铁路": ["义乌", "宁波", "舟山"],

        # 湖州城际：湖州 → 杭州
        "湖州城际": ["湖州", "杭州"],

        # 嘉兴城际：嘉兴 → 上海
        "嘉兴城际": ["嘉兴", "上海"],

        # 蚌埠城际：蚌埠 → 宿州
        "蚌埠城际": ["蚌埠", "宿州"],

        # 宿州城际：宿州 → 徐州
        "宿州城际": ["宿州", "徐州"],

        # 徐州城际：徐州 → 连云港
        "徐州城际": ["徐州", "连云港"],

        # 连云港城际：连云港 → 日照
        "连云港城际": ["连云港", "日照"],

        # 日照城际：日照 → 青岛
        "日照城际": ["日照", "青岛"],

        # 烟台城际：烟台 → 威海
        "烟台城际": ["烟台", "威海"],

        # 济南城际：济南 → 泰安
        "济南城际": ["济南", "泰安"],

        # 泰安城际：泰安 → 济宁
        "泰安城际": ["泰安", "济宁"],

        # 济宁城际：济宁 → 菏泽
        "济宁城际": ["济宁", "菏泽"],

        # 菏泽城际：菏泽 → 聊城
        "菏泽城际": ["菏泽", "聊城"],

        # 聊城城际：聊城 → 德州
        "聊城城际": ["聊城", "德州"],

        # 德州城际：德州 → 沧州
        "德州城际": ["德州", "沧州"],

        # 沧州城际：沧州 → 衡水
        "沧州城际": ["沧州", "衡水"],

        # 衡水城际：衡水 → 石家庄
        "衡水城际": ["衡水", "石家庄"],

        # 石家庄城际：石家庄 → 邢台
        "石家庄城际": ["石家庄", "邢台"],

        # 邢台城际：邢台 → 邯郸
        "邢台城际": ["邢台", "邯郸"],

        # 邯郸城际：邯郸 → 安阳
        "邯郸城际": ["邯郸", "安阳"],

        # 安阳城际：安阳 → 鹤壁
        "安阳城际": ["安阳", "鹤壁"],

        # 鹤壁城际：鹤壁 → 新乡
        "鹤壁城际": ["鹤壁", "新乡"],

        # 新乡城际：新乡 → 焦作
        "新乡城际": ["新乡", "焦作"],

        # 焦作城际：焦作 → 郑州
        "焦作城际": ["焦作", "郑州"],

        # 郑州城际：郑州 → 开封
        "郑州城际": ["郑州", "开封"],

        # 开封城际：开封 → 商丘
        "开封城际": ["开封", "商丘"],

        # 商丘城际：商丘 → 周口
        "商丘城际": ["商丘", "周口"],

        # 周口城际：周口 → 漯河
        "周口城际": ["周口", "漯河"],

        # 漯河城际：漯河 → 平顶山
        "漯河城际": ["漯河", "平顶山"],

        # 平顶山城际：平顶山 → 许昌
        "平顶山城际": ["平顶山", "许昌"],

        # 许昌城际：许昌 → 洛阳
        "许昌城际": ["许昌", "洛阳"],

        # 洛阳城际：洛阳 → 三门峡
        "洛阳城际": ["洛阳", "三门峡"],

        # 三门峡城际：三门峡 → 运城
        "三门峡城际": ["三门峡", "运城"],

        # 运城城际：运城 → 临汾
        "运城城际": ["运城", "临汾"],

        # 临汾城际：临汾 → 太原
        "临汾城际": ["临汾", "太原"],

        # 太原城际：太原 → 晋中
        "太原城际": ["太原", "晋中"],

        # 晋中城际：晋中 → 阳泉
        "晋中城际": ["晋中", "阳泉"],

        # 阳泉城际：阳泉 → 石家庄
        "阳泉城际": ["阳泉", "石家庄"],

        # 大同城际：大同 → 朔州
        "大同城际": ["大同", "朔州"],

        # 朔州城际：朔州 → 忻州
        "朔州城际": ["朔州", "忻州"],

        # 忻州城际：忻州 → 太原
        "忻州城际": ["忻州", "太原"],

        # 包头城际：包头 → 鄂尔多斯
        "包头城际": ["包头", "鄂尔多斯"],

        # 鄂尔多斯城际：鄂尔多斯 → 榆林
        "鄂尔多斯城际": ["鄂尔多斯", "榆林"],

        # 榆林城际：榆林 → 延安
        "榆林城际": ["榆林", "延安"],

        # 延安城际：延安 → 铜川
        "延安城际": ["延安", "铜川"],

        # 铜川城际：铜川 → 西安
        "铜川城际": ["铜川", "西安"],

        # 西安城际：西安 → 咸阳
        "西安城际": ["西安", "咸阳"],

        # 咸阳城际：咸阳 → 宝鸡
        "咸阳城际": ["咸阳", "宝鸡"],

        # 宝鸡城际：宝鸡 → 天水
        "宝鸡城际": ["宝鸡", "天水"],

        # 天水城际：天水 → 定西
        "天水城际": ["天水", "定西"],

        # 定西城际：定西 → 兰州
        "定西城际": ["定西", "兰州"],

        # 兰州城际：兰州 → 西宁
        "兰州城际": ["兰州", "西宁"],

        # 西宁城际：西宁 → 海东
        "西宁城际": ["西宁", "海东"],

        # 海东城际：海东 → 格尔木
        "海东城际": ["海东", "格尔木"],

        # 格尔木城际：格尔木 → 那曲
        "格尔木城际": ["格尔木", "那曲"],

        # 那曲城际：那曲 → 拉萨
        "那曲城际": ["那曲", "拉萨"],

        # 拉萨城际：拉萨 → 日喀则
        "拉萨城际": ["拉萨", "日喀则"],

        # 日喀则城际：日喀则 → 林芝
        "日喀则城际": ["日喀则", "林芝"],

        # 林芝城际：林芝 → 昌都
        "林芝城际": ["林芝", "昌都"],

        # 昌都城际：昌都 → 成都
        "昌都城际": ["昌都", "成都"],

        # 成都城际：成都 → 德阳
        "成都城际": ["成都", "德阳"],

        # 德阳城际：德阳 → 绵阳
        "德阳城际": ["德阳", "绵阳"],

        # 绵阳城际：绵阳 → 广元
        "绵阳城际": ["绵阳", "广元"],

        # 广元城际：广元 → 汉中
        "广元城际": ["广元", "汉中"],

        # 汉中城际：汉中 → 安康
        "汉中城际": ["汉中", "安康"],

        # 安康城际：安康 → 达州
        "安康城际": ["安康", "达州"],

        # 达州城际：达州 → 南充
        "达州城际": ["达州", "南充"],

        # 南充城际：南充 → 广安
        "南充城际": ["南充", "广安"],

        # 广安城际：广安 → 重庆
        "广安城际": ["广安", "重庆"],

        # 重庆城际：重庆 → 涪陵
        "重庆城际": ["重庆", "涪陵"],

        # 涪陵城际：涪陵 → 黔江
        "涪陵城际": ["涪陵", "黔江"],

        # 黔江城际：黔江 → 吉首
        "黔江城际": ["黔江", "吉首"],

        # 吉首城际：吉首 → 怀化
        "吉首城际": ["吉首", "怀化"],

        # 怀化城际：怀化 → 铜仁
        "怀化城际": ["怀化", "铜仁"],

        # 铜仁城际：铜仁 → 凯里
        "铜仁城际": ["铜仁", "凯里"],

        # 凯里城际：凯里 → 都匀
        "凯里城际": ["凯里", "都匀"],

        # 都匀城际：都匀 → 贵阳
        "都匀城际": ["都匀", "贵阳"],

        # 贵阳城际：贵阳 → 安顺
        "贵阳城际": ["贵阳", "安顺"],

        # 安顺城际：安顺 → 六盘水
        "安顺城际": ["安顺", "六盘水"],

        # 六盘水城际：六盘水 → 毕节
        "六盘水城际": ["六盘水", "毕节"],

        # 毕节城际：毕节 → 泸州
        "毕节城际": ["毕节", "泸州"],

        # 泸州城际：泸州 → 宜宾
        "泸州城际": ["泸州", "宜宾"],

        # 宜宾城际：宜宾 → 乐山
        "宜宾城际": ["宜宾", "乐山"],

        # 乐山城际：乐山 → 眉山
        "乐山城际": ["乐山", "眉山"],

        # 眉山城际：眉山 → 成都
        "眉山城际": ["眉山", "成都"],

        # 昆明城际：昆明 → 曲靖
        "昆明城际": ["昆明", "曲靖"],

        # 曲靖城际：曲靖 → 六盘水
        "曲靖城际": ["曲靖", "六盘水"],

        # 六盘水城际：六盘水 → 毕节
        # 六盘水城际: ["六盘水", "毕节"],  # 上面已定义

        # 毕节城际：毕节 → 贵阳
        # 毕节城际: ["毕节", "贵阳"],  # 上面已定义

        # 贵阳城际：贵阳 → 南宁
        "贵阳城际_贵南": ["贵阳", "南宁"],

        # 南宁城际：南宁 → 柳州
        "南宁城际": ["南宁", "柳州"],

        # 柳州城际：柳州 → 桂林
        "柳州城际": ["柳州", "桂林"],

        # 桂林城际：桂林 → 贺州
        "桂林城际": ["桂林", "贺州"],

        # 贺州城际：贺州 → 广州
        "贺州城际": ["贺州", "广州"],

        # 广州城际：广州 → 佛山
        "广州城际": ["广州", "佛山"],

        # 佛山城际：佛山 → 江门
        "佛山城际": ["佛山", "江门"],

        # 江门城际：江门 → 中山
        "江门城际": ["江门", "中山"],

        # 中山城际：中山 → 珠海
        "中山城际": ["中山", "珠海"],

        # 珠海城际：珠海 → 澳门
        "珠海城际": ["珠海", "澳门"],

        # 澳门城际：澳门 → 香港
        "澳门城际": ["澳门", "香港"],

        # 香港城际：香港 → 深圳
        "香港城际": ["香港", "深圳"],

        # 深圳城际：深圳 → 东莞
        "深圳城际": ["深圳", "东莞"],

        # 东莞城际：东莞 → 惠州
        "东莞城际": ["东莞", "惠州"],

        # 惠州城际：惠州 → 河源
        "惠州城际": ["惠州", "河源"],

        # 河源城际：河源 → 梅州
        "河源城际": ["河源", "梅州"],

        # 梅州城际：梅州 → 潮州
        "梅州城际": ["梅州", "潮州"],

        # 潮州城际：潮州 → 汕头
        "潮州城际": ["潮州", "汕头"],

        # 汕头城际：汕头 → 揭阳
        "汕头城际": ["汕头", "揭阳"],

        # 揭阳城际：揭阳 → 汕尾
        "揭阳城际": ["揭阳", "汕尾"],

        # 汕尾城际：汕尾 → 惠州
        "汕尾城际": ["汕尾", "惠州"],

        # 厦门城际：厦门 → 泉州
        "厦门城际": ["厦门", "泉州"],

        # 泉州城际：泉州 → 莆田
        "泉州城际": ["泉州", "莆田"],

        # 莆田城际：莆田 → 福州
        "莆田城际": ["莆田", "福州"],

        # 福州城际：福州 → 宁德
        "福州城际": ["福州", "宁德"],

        # 宁德城际：宁德 → 温州
        "宁德城际": ["宁德", "温州"],

        # 温州城际：温州 → 台州
        "温州城际": ["温州", "台州"],

        # 台州城际：台州 → 宁波
        "台州城际": ["台州", "宁波"],

        # 宁波城际：宁波 → 绍兴
        "宁波城际": ["宁波", "绍兴"],

        # 绍兴城际：绍兴 → 杭州
        "绍兴城际": ["绍兴", "杭州"],

        # 湖州城际：湖州 → 嘉兴
        "湖州城际_湖嘉": ["湖州", "嘉兴"],

        # 南京城际：南京 → 上海
        "南京城际": ["南京", "上海"],
    }

    def match_lines_smartly(self, stations: List[str], verbose: bool = False) -> List[str]:
        """
        智能匹配策略

        核心思路：
        1. 识别线路切换点（通过站点在线路中的位置变化）
        2. 优先保留局部线路（避免被大线路吞噬）
        3. 支持线路边界识别和智能切换

        Args:
            stations: 站点列表（按顺序）
            verbose: 是否输出详细匹配过程

        Returns:
            匹配的线路名称列表
        """
        matched_lines = []

        if verbose:
            print(f"\n智能线路匹配:")
            print(f"站点序列: {' -> '.join(stations)}\n")

        for i in range(len(stations) - 1):
            station_a = stations[i]
            station_b = stations[i + 1]

            if verbose:
                print(f"区间 {i+1}: {station_a} -> {station_b}")

            # 找到所有包含这两个站点的线路
            possible_lines = []
            for line_name, line_stations in self.RAILWAY_LINES.items():
                if station_a in line_stations and station_b in line_stations:
                    pos_a = line_stations.index(station_a)
                    pos_b = line_stations.index(station_b)

                    # 计算线路对整个车次的覆盖度
                    train_stations_set = set(stations)
                    line_stations_set = set(line_stations)
                    coverage = len(train_stations_set & line_stations_set) / len(line_stations_set)

                    # 计算距离
                    distance = abs(pos_a - pos_b)

                    possible_lines.append({
                        'name': line_name,
                        'pos_a': pos_a,
                        'pos_b': pos_b,
                        'coverage': coverage,
                        'distance': distance,
                        'line_length': len(line_stations)
                    })

            if possible_lines:
                # 智能排序策略
                # 1. 优先选择局部线路（避免被大线路覆盖）
                # 2. 其次选择覆盖度高的
                # 3. 如果上一条线路能覆盖当前区间，优先继续使用

                # 先排序
                possible_lines.sort(key=lambda x: (
                    x['line_length'],   # 局部线路优先
                    -x['coverage'],     # 覆盖度高的优先
                    x['distance']       # 距离短的优先
                ))

                if verbose:
                    print(f"  可选线路:")
                    for j, line in enumerate(possible_lines, 1):
                        marker = ""
                        if matched_lines and line['name'] == matched_lines[-1]:
                            marker = " (当前使用)"
                        print(f"    {j}. {line['name']}: 长度{line['line_length']}站 覆盖{line['coverage']:.2f}{marker}")

                # 决策逻辑
                selected_line = None

                # 1. 如果上一条线路能覆盖当前区间，优先继续使用
                if matched_lines:
                    last_line = matched_lines[-1]
                    for line in possible_lines:
                        if line['name'] == last_line:
                            # 检查是否存在更优的局部线路
                            # 如果第一条（局部）线路明显更优，则切换
                            if possible_lines[0]['line_length'] < last_line:
                                selected_line = possible_lines[0]['name']
                                if verbose:
                                    print(f"  → 检测到线路切换：{last_line} → {selected_line}")
                            else:
                                selected_line = last_line
                            break

                # 2. 如果无法继续使用上一条线路，选择最佳线路
                if selected_line is None:
                    selected_line = possible_lines[0]['name']
                    if not matched_lines or selected_line != matched_lines[-1]:
                        if verbose:
                            print(f"  ✓ 新增线路: {selected_line}")
                    else:
                        if verbose:
                            print(f"  ✓ 继续使用: {selected_line}")
                else:
                    if verbose:
                        print(f"  ✓ 选择线路: {selected_line}")

                # 添加到结果（避免重复）
                if not matched_lines or selected_line != matched_lines[-1]:
                    matched_lines.append(selected_line)
            else:
                if verbose:
                    print(f"  ✗ 无匹配线路")

        return matched_lines

    def process_train_info(self, train_data: Dict, original_lines: List[str] = None, verbose: bool = False) -> Dict:
        """
        处理单个车次信息，添加匹配的线路

        Args:
            train_data: 车次信息字典
            original_lines: 原始线路信息（用于对比）
            verbose: 是否输出详细匹配过程

        Returns:
            添加了 line_names 的车次信息
        """
        # 提取站点列表
        stations_dict = train_data.get("stations", {})
        stations = []
        for i in range(1, len(stations_dict) + 1):
            station_key = str(i)
            if station_key in stations_dict:
                stations.append(stations_dict[station_key])

        if not stations:
            return train_data

        # 匹配线路
        line_names = self.match_lines_smartly(stations, verbose)

        # 添加到车次信息
        result = train_data.copy()
        result["line_names"] = line_names

        # 如果有原始线路，添加对比信息
        if original_lines:
            original_set = set(original_lines)
            matched_set = set(line_names)

            if original_set == matched_set and len(original_lines) == len(line_names):
                result["match_status"] = "完全一致"
            elif original_set & matched_set:
                result["match_status"] = "部分匹配"
            else:
                result["match_status"] = "无匹配"

        return result

    def process_trains_file(self, input_file: str, output_file: str, verbose: bool = False):
        """
        处理车次信息文件，为所有车次添加 line_names

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            verbose: 是否输出详细匹配过程
        """
        print("=" * 80)
        print("车次线路智能匹配工具（最终版本）")
        print("=" * 80)
        print(f"输入文件: {input_file}")
        print(f"输出文件: {output_file}")
        print("=" * 80)

        # 读取输入文件
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 移除 markdown 标记
            if content.startswith("```"):
                lines = content.split('\n')
                if lines[0].startswith("```"):
                    content = '\n'.join(lines[1:-1])

            # 修复 JSON 格式（给没有引号的字符串添加引号）
            import re
            # 匹配 [XX, XX, YY] 格式并添加引号
            pattern = r'\[([^\]]+)\]'
            matches = re.findall(pattern, content)
            for match in matches:
                items = match.split(',')
                quoted_items = []
                for item in items:
                    item = item.strip()
                    if not item.startswith('"') and not item.startswith("'"):
                        quoted_items.append(f'"{item}"')
                    else:
                        quoted_items.append(item)
                old_text = f'[{match}]'
                new_text = f'[{", ".join(quoted_items)}]'
                content = content.replace(old_text, new_text)

            # 移除末尾逗号
            if content.rstrip().endswith(','):
                content = content.rstrip()[:-1]

            # 解析 JSON
            if content.startswith('['):
                trains_data = json.loads(content)
            elif content.startswith('{'):
                data = json.loads(content)
                if 'trains' in data:
                    trains_data = data['trains']
                else:
                    trains_data = [data]
            else:
                print(f"  ✗ 无法识别的文件格式")
                return

            print(f"\n✓ 已读取 {len(trains_data)} 个车次信息\n")

            # 处理每个车次
            processed_trains = []
            for i, train_data in enumerate(trains_data, 1):
                print(f"【{i}/{len(trains_data)}】处理车次: {train_data.get('name', '未知')}")

                # 提取原始线路（如果有）
                original_lines = train_data.get('line_names', [])

                # 处理车次
                processed_train = self.process_train_info(train_data, original_lines, verbose)
                processed_trains.append(processed_train)

                # 显示结果
                print(f"  站点数: {processed_train.get('station_count', 0)}")
                print(f"  匹配线路: {' → '.join(processed_train.get('line_names', []))}")

                if original_lines:
                    print(f"  原始线路: {' → '.join(original_lines)}")
                    print(f"  匹配状态: {processed_train.get('match_status', '未知')}")

                print()

            # 写入输出文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(processed_trains, f, ensure_ascii=False, indent=2)

            print("=" * 80)
            print(f"✓ 处理完成！")
            print(f"  输出文件: {output_file}")
            print(f"  处理车次数: {len(processed_trains)}")
            print("=" * 80)

            # 统计匹配情况
            if all('match_status' in train for train in processed_trains):
                print("\n匹配统计:")
                exact_match = sum(1 for train in processed_trains if train['match_status'] == '完全一致')
                partial_match = sum(1 for train in processed_trains if train['match_status'] == '部分匹配')
                no_match = sum(1 for train in processed_trains if train['match_status'] == '无匹配')

                print(f"  完全一致: {exact_match} ({exact_match/len(processed_trains)*100:.1f}%)")
                print(f"  部分匹配: {partial_match} ({partial_match/len(processed_trains)*100:.1f}%)")
                print(f"  无匹配: {no_match} ({no_match/len(processed_trains)*100:.1f}%)")

        except FileNotFoundError:
            print(f"  ✗ 文件未找到: {input_file}")
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON 解析错误: {e}")
        except Exception as e:
            print(f"  ✗ 处理错误: {e}")


def main():
    """主函数 - 演示使用"""
    # 创建匹配器
    matcher = TrainLineMatcher()

    # 处理车次信息文件
    input_file = "车次信息.txt"
    output_file = "车次信息_最终结果.json"

    # 使用详细模式（显示匹配过程）
    matcher.process_trains_file(input_file, output_file, verbose=False)


if __name__ == "__main__":
    main()
