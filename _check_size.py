"""查看各目录大小，分析 Docker 镜像体积来源"""
import os

root = os.path.dirname(os.path.abspath(__file__))

dirs = [
    "data",
    "data/txts",
    "data/cleaned_txts",
    "data/vector_database",
    "frontend",
    "frontend/node_modules",
    "mytools",
    "tests",
    ".git",
    "agent",
    "backend",
]

for d in dirs:
    path = os.path.join(root, d)
    if os.path.isdir(path):
        total = 0
        fcount = 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    total += os.path.getsize(fp)
                    fcount += 1
                except:
                    pass
        print(f"{d:30s} {total/1024/1024:>8.2f} MB  ({fcount} files)")
    else:
        print(f"{d:30s}   (不存在)")

# 大文件单独看
big_files = [
    "data/china_railway.pkl",
    "data/city_to_node.pkl",
    "data/train_data.json",
    "data/stations.json",
    "data/stations.pkl",
]
print()
for f in big_files:
    path = os.path.join(root, f)
    if os.path.isfile(path):
        print(f"{f:40s} {os.path.getsize(path)/1024/1024:.2f} MB")
