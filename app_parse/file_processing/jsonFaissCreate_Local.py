'''
仿真知识库的专有处理文档
将 JSON 文件转换为向量文件
'''

import os
import time
import random
import json
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings
from config import Config

class JsonFaissCreator:
    def __init__(self, split_semicolon_count=10, overlap=1, **kwargs):
        # 初始化 Ollama Embedding
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest", show_progress=True, base_url=Config.OLLAMA_BASE_URL)
        self.split_semicolon_count = split_semicolon_count
        self.overlap = overlap

    # 读取 JSON 文件
    def load_json_data(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                # 将 JSON 数据转换为字符串
                json_str = str(data)
                return json_str
        except Exception as e:
            print(f"读取 JSON 文件时出错: {e}")
            return ""

    # 按指定分号数量分割文本为多个 chunk，并设置重叠部分
    def split_json_text(self, text):
        # 利用类属性中的分割参数
        return self.split_json_text_with_params(text, self.split_semicolon_count, self.overlap)

    def split_json_text_with_params(self, text, split_semicolon_count, overlap):
        # 按分号分割文本
        parts = text.split(';')
        chunks = []
        i = 0
        while i < len(parts):
            end_index = i + split_semicolon_count
            # 提取当前块
            chunk = ';'.join(parts[i:end_index])
            chunks.append(chunk)
            # 处理重叠部分
            i += split_semicolon_count - overlap
        return chunks

    # 分批次处理并嵌入每个 chunk
    def process_and_embed_chunks(self, chunks, batch_size=1, initial_delay=0.0, max_retries=5):
        all_texts = []
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            all_texts.extend(batch_chunks)

            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    self.embeddings.embed_documents(batch_chunks)  # 只是为了测试 API 调用
                    break
                except Exception as e:
                    retries += 1
                    print(f"Error occurred: {e}")
                    if retries < max_retries:
                        delay *= 2  # 指数退避
                        jitter = random.uniform(0, 0.1 * delay)  # 添加一些随机性
                        wait_time = delay + jitter
                        print(f"Retrying in {wait_time:.2f} seconds... ({retries}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print("Max retries reached, moving on to the next batch.")

            time.sleep(initial_delay)  # 每批请求之间的基本等待时间

        return all_texts

    # 主处理方法
    def process_json_to_faiss(self, json_file_path, save_path):
        # 加载 JSON 数据
        json_text = self.load_json_data(json_file_path)
        print('len of json_text: ', len(json_text))

        # 分割文本为 chunk，使用类属性中的参数
        chunks = self.split_json_text(json_text)
        print('len of chunks: ', len(chunks))

        # 处理每个 chunk
        all_texts = self.process_and_embed_chunks(chunks)
        print('len of all_texts: ', len(all_texts))

        # 创建 FAISS 索引
        db = FAISS.from_texts(all_texts, self.embeddings)
        file_name = os.path.splitext(os.path.basename(json_file_path))[0]
        # 保存 FAISS 索引
        db.save_local(save_path, index_name=file_name)
        print('FAISS vector store successfully saved at', save_path)
        return save_path

if __name__ == "__main__":
    creator = JsonFaissCreator(split_semicolon_count= 15, overlap=5)
    json_file_path = 'E:\\PycharmProjects\\FlaskOllama\\data\\SimuJson.json'
    save_path = "E:\\PycharmProjects\\FlaskOllama\\data\\vector_db"
    creator.process_json_to_faiss(json_file_path, save_path)