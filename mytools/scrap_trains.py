import requests
from lxml import etree
import urllib3

# 禁用 SSL 警告（因目标网站证书配置问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. 目标网址 (URL)
url = "https://train.hao86.com/%E9%AB%98%E9%80%9F/"

# 2. 发送请求，获取网页内容
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
try:
    # verify=False 禁用 SSL 证书验证
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()  # 检查请求是否成功
    html_content = response.content
except requests.RequestException as e:
    print(f"请求网页失败: {e}")
    exit()

# 3. 解析HTML
parser = etree.HTMLParser()
tree = etree.fromstring(html_content, parser)

# **关键步骤：定位并提取数据**
# 定位到 class 为 "train_index_cz" 的 div 下的 ul class="clearfix" 中的 li
ul_xpath = '//div[contains(@class, "train_index_cz")]//ul[contains(@class, "clearfix")]/li'
lis = tree.xpath(ul_xpath)

if not lis:
    print("未找到目标列表，请检查XPath或网站结构。")
    exit()

# 统计数据总数
total_count = len(lis)
print(f"共收集到 {total_count} 个数据\n")

# 4. 遍历提取每个 li 的内容
all_data = []
for i, li in enumerate(lis, 1):
    # 提取 li 标签内的文本内容
    text = li.xpath('string(.)').strip()
    all_data.append(text)
    print(f"{i}. {text}")

# 6. (可选) 保存数据到文件
if all_data:
    with open('高速.txt', 'w', encoding='utf-8') as f:
        for i, item in enumerate(all_data, 1):
            f.write(f"{i}. {item}\n")
    print(f"\n数据已保存至 '高速.txt'，共 {total_count} 条记录")
