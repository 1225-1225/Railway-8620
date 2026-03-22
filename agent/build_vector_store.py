import hashlib
import os.path
from pathlib import Path

from datetime import datetime
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config_data


def check_md5(md5_str):
    if not os.path.exists(config_data.md5_path):
        with open(config_data.md5_path, "w", encoding="utf-8") as f:
            pass  # 创建空文件，无需写入内容
        return False
    else:
        for line in open(config_data.md5_path, "r", encoding="utf-8").readlines():
            line = line.strip()
            if line == md5_str:
                return True
        return False


def get_str_md5(data_str, encoding="utf-8"):
    str_bytes = data_str.encode(encoding=encoding)
    md5_obj = hashlib.md5()
    md5_obj.update(str_bytes)
    md5_hex = md5_obj.hexdigest()
    return md5_hex

def save_md5(md5_hex):
    with open(config_data.md5_path, "a", encoding="utf-8") as f:
        f.write(md5_hex + "\n")



class BuildVectorStore(object):
    def __init__(self):

        self.chroma = Chroma(   #创建数据库
            collection_name=config_data.collection_name,        #数据库表名
            embedding_function=DashScopeEmbeddings(model="text-embedding-v4"),  #embedding模型名称
            persist_directory=config_data.persist_directory,    #数据库目录
        )

        self.spliter = RecursiveCharacterTextSplitter(  #按照语义分割长文本，这个类是通用场景首选
            chunk_size=config_data.chunk_size,      #段落字符数最大值
            chunk_overlap=config_data.chunk_overlap,#两个段落间允许的重叠字符最大值
            separators=config_data.separators,      #分隔符指定，例如，。等，按照优先级排列
            length_function=len                     #计算文本长度的函数
        )

    def upload_from_data(self):  #上传字符串到数据库
        folder_path = Path(config_data.data_path)  # 替换为你的文件夹路径
        txt_files = []

        for txt_file in folder_path.glob('*.txt'):
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            txt_files.append({
                'filename': txt_file.name,
                'filepath': str(txt_file),
                'content': content
            })

        for txt_file in txt_files:
            data = txt_file["content"]
            filename = txt_file["filename"]
            md5_hex = get_str_md5(data)
            if check_md5(md5_hex):
                print(f"[跳过] {filename} 已存在")
                continue

            if len(data) > config_data.split_starting_point:
                txt_file_chunks = self.spliter.split_text(data)
            else:
                txt_file_chunks = [data]

            metadata = {
                "source": filename,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "operator": "1225"
            }

            self.chroma.add_texts(
                txt_file_chunks,
                metadatas=[metadata for _ in txt_file_chunks]
            )
            save_md5(md5_hex)
            print(f"[成功] {filename} 已存入库，共 {len(txt_file_chunks)} 个块")

if __name__ == "__main__":
    builder = BuildVectorStore()
    builder.upload_from_data()