# -*- coding: utf-8 -*-
# @Time : 2024/8/21 上午10:57
# @Author : Administrator
# @File : FaissCreate.py
# @Project : RAG normal

import json
import os
import threading
import queue
import time
from langchain_community.vectorstores import FAISS
#from langchain_community.embeddings import BaichuanTextEmbeddings
from langchain_community.embeddings import OllamaEmbeddings
import random
import configparser
from config import Config


class FaissCreate:
    def __init__(self):
        # 设置 Baichuan API 密钥
        self.thread_num = 5
        self.task_queue = queue.Queue()
        os.environ["BAICHUAN_API_KEY"] = "sk-9c8de2cf7d808d120bb88dea8ecdd3cc"

        self.lock = threading.Lock()
        self.all_texts = []

        # 初始化 Baichuan Embedding
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest", show_progress=True)

        #config = configparser.ConfigParser()
        #config.read('chat/parse/config.ini')
        
        base_url = Config.OLLAMA_BASE_URL   #config.get('Ollama', 'base_url')

        #settings = QSettings('config.ini', QSettings.Format.IniFormat)
        #base_url = settings.value('Ollama/base_url', 'http://localhost:11434')
        self.embeddings.base_url = base_url
        #self.embeddings = BaichuanTextEmbeddings(baichuan_api_key=os.getenv("BAICHUAN_API_KEY"))

    # 读取 JSON 文件
    def load_json_data(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)

    # 递归处理 JSON 数据，按页面分割成多个 chunk
    def process_json(self, data, prefix=''):
        chunks = []


        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix} -> {key}" if prefix else key
                if isinstance(value, dict):
                    if all(isinstance(v, (str, int, float, bool, list)) for v in value.values()):
                        # 这是一个最终的数据项，将其合并为一个chunk
                        chunk = f"{new_prefix}:\n"
                        for k, v in value.items():
                            if isinstance(v, list):
                                # 处理list中的每个元素，递归处理可能的dict，并加上编号
                                processed_list_items = []
                                for i, item in enumerate(v, start=1):
                                    if isinstance(item, dict):
                                        processed_list_items.append(f"{i}. {self.process_json(item, '')[0]}")  # 递归处理并获取字符串
                                    else:
                                        processed_list_items.append(f"{i}. {str(item)}")
                                chunk += f"{k}: " + "\n".join(processed_list_items) + "\n"
                            else:
                                chunk += f"{k}: {v}\n"
                        chunk = chunk.strip()  # 去除最后一个换行符
                        print('chunk is: ', chunk)
                        print('*' * 50)
                        chunks.append(chunk)
                    else:
                        # 这是一个中间节点，继续递归
                        chunks.extend(self.process_json(value, new_prefix))
                else:
                    # 直接添加键值对
                    chunks.append(f"{new_prefix}: {value}")
        return chunks

    # 将 JSON 数据按 page 键分块
    def split_by_page(self, sets, file_name):

        page_chunks = []

        for item in sets:
            text = item.get("text")
            if text is None:
                continue

            page = str(item["page_idx"]+1)
            item_title = f"{file_name} 第{page}页"

            page_chunks.append(f'{item_title}: {text}')

        print('len of pages: ', len(page_chunks))
        return page_chunks

    def process_and_embed(self):
        while True:
            page_chunk, page_num = self.task_queue.get()
            if page_chunk is None:
                self.task_queue.task_done()
                break

            try:
                batch_texts = [page_chunk] #self.process_json(page_chunk)
                retries = 0
                delay = 0.0
                while retries < 5:
                    try:
                        self.embeddings.embed_documents(batch_texts)  # 这里假设embed_documents返回嵌入向量
                        with self.lock:
                            self.all_texts.extend(batch_texts)
                        break
                    except Exception as e:
                        retries += 1
                        print(f"Error occurred: {e}")
                        delay *= 2
                        jitter = random.uniform(0, 0.1 * delay)
                        time.sleep(delay + jitter)
                time.sleep(0.1)  # 休息一下，防止API过载
            finally:
                self.task_queue.task_done()
    
    def process_and_embed_Threads(self, page_chunks):
        # 填充任务队列
        page_num = 1
        for img in page_chunks:
            self.task_queue.put((img, page_num))
            page_num += 1

        # 创建并启动线程
        threads = []
        for _ in range(self.thread_num):
            thread = threading.Thread(target=self.process_page)
            thread.start()
            threads.append(thread)

        # 等待所有任务完成
        self.task_queue.join()

        # 停止线程
        for _ in threads:
            self.task_queue.put((None, None))

        # 等待所有线程完成
        for thread in threads:
            thread.join()

    # 分批次处理并嵌入每个 chunk
    def process_and_embed_chunks(self, page_chunks, batch_size=1, initial_delay=0.0, max_retries=5):
        all_texts = []
        for i in range(0, len(page_chunks), batch_size):
            batch_chunks = page_chunks[i:i + batch_size]
            batch_texts = []
            for page_chunk in batch_chunks:
                batch_texts.extend(self.process_json(page_chunk))

            all_texts.extend(batch_texts)

            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    self.embeddings.embed_documents(batch_texts)  # 只是为了测试 API 调用
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

    def set_json_faiss(self, faiss_index, json_path, save_path, file_name):
        import json
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"JSON file not found at {json_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in {json_path}: {str(e)}")

        page_chunks = self.split_by_page(json_data, file_name)

        # 填充任务队列
        for page_chunk in page_chunks:
            self.task_queue.put((page_chunk, None))

        # 创建并启动线程
        threads = []
        for _ in range(self.thread_num):
            thread = threading.Thread(target=self.process_and_embed)
            thread.start()
            threads.append(thread)

        # 等待所有任务完成
        self.task_queue.join()

        # 停止线程
        for _ in range(self.thread_num):
            self.task_queue.put((None, None))

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 创建 FAISS 索引
        db = FAISS.from_texts(self.all_texts, self.embeddings)
        db.save_local(save_path, index_name=faiss_index)
        print('FAISS vector store successfully saved at', save_path)

    def set_json_faiss1(self, faiss_index, json_data, save_path):

        try:
            # 加载 JSON 数据
            # json_data = self.load_json_data(json_file_path)
            #json_data = commonUtil.CommonUtil.read_json_from_file(json_path)

            # 按页面分块
            page_chunks = self.split_by_page(json_data)

            # 处理每个 chunk
            all_texts = self.process_and_embed_chunks(page_chunks)
            #
            # 创建 FAISS 索引
            db = FAISS.from_texts(all_texts, self.embeddings)
            # print('db is: ', db)

            # 保存 FAISS 索引
            # abspath = os.path.abspath(save_path)
            # abspath = abspath.replace("\\", "/")
            # db.save_local(abspath,index_name=faiss_index )
            db.save_local(save_path,
                          index_name=faiss_index
                          )
            print('FAISS vector store successfully saved at', save_path)
            return 'FAISS vector store successfully saved at', save_path
        except Exception as e:
            return str(e)
