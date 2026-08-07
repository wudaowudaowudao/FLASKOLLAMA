'''
将 JSON 文件转换为向量文件，
对于仿真知识库的专有embeddings过程
'''

import os
import time
import random
import json
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings


class JsonFaissCreator:
    def __init__(self, model="bge-m3:latest", show_progress=True):
        """
        初始化 JsonFaissCreator 类
        
        Args:
            model (str): 使用的嵌入模型名称
            show_progress (bool): 是否显示进度
        """
        # 初始化 Ollama Embedding
        self.embeddings = OllamaEmbeddings(model=model, show_progress=show_progress)
    
    def load_json_data(self, file_path):
        """
        读取 JSON 文件内容
        
        Args:
            file_path (str): JSON 文件路径
            
        Returns:
            str: 文件内容文本
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                # 将 JSON 数据转换为字符串
                json_str = str(data)
                return json_str
        except Exception as e:
            print(f"读取 JSON 文件时出错: {e}")
            return ""
    
    def split_json_text(self, text, split_semicolon_count=10, overlap=1):
        """
        按指定分号数量分割文本为多个 chunk，并设置重叠部分
        
        Args:
            text (str): 要分割的文本
            split_semicolon_count (int): 每个 chunk 包含的分号数量
            overlap (int): 重叠的分号数量
            
        Returns:
            list: 分割后的文本块列表
        """
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
    
    def process_and_embed_chunks(self, chunks, batch_size=1, initial_delay=0.0, max_retries=5):
        """
        分批次处理并嵌入每个 chunk
        
        Args:
            chunks (list): 文本块列表
            batch_size (int): 每批处理的文本块数量
            initial_delay (float): 每批请求之间的基本等待时间
            max_retries (int): 最大重试次数
            
        Returns:
            list: 处理后的文本块列表
        """
        all_texts = []
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            all_texts.extend(batch_chunks)

            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    self.embeddings.embed_documents(batch_chunks)  # 嵌入文本块
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
    
    def create_faiss_index(self, json_file_path, save_path):
        """
        创建并保存 FAISS 索引
        
        Args:
            json_file_path (str): JSON 文件路径
            save_path (str): FAISS 索引保存路径
        """
        # 加载 JSON 数据
        json_text = self.load_json_data(json_file_path)
        print('len of json_text: ', len(json_text))

        # 分割文本为 chunk
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

# 主程序
def main():
    json_file_path = 'E:\\PycharmProjects\\FlaskOllama\\data\\SimuJson.json'
    save_path = "E:\\PycharmProjects\\FlaskOllama\\data\\vector_json_db"

    # 创建实例并运行
    creator = JsonFaissCreator()
    creator.create_faiss_index(json_file_path, save_path)


if __name__ == "__main__":
    main()