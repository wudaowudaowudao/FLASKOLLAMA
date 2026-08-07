'''
测试有问题，待调整
将JSON文件转换为向量文件,这个是对于复杂的json文件的处理
1. 读取JSON文件
2. 递归处理JSON数据，按页面分割成多个chunk
3. 将每个chunk嵌入到向量数据库中
'''

import json
import os
import time
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import BaichuanTextEmbeddings
import random
from langchain_community.embeddings import OllamaEmbeddings

# 设置 Baichuan API 密钥
# os.environ["BAICHUAN_API_KEY"] = "sk-9c8de2cf7d808d120bb88dea8ecdd3cc"

# 初始化 Baichuan Embedding
# embeddings = BaichuanTextEmbeddings(baichuan_api_key=os.getenv("BAICHUAN_API_KEY"))
embeddings = OllamaEmbeddings(model="bge-m3:latest", show_progress=True)
# 读取 JSON 文件
def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 递归处理 JSON 数据，按页面分割成多个 chunk
def process_json(data, prefix=''):
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
                                    processed_list_items.append(f"{i}. {process_json(item, '')[0]}")  # 递归处理并获取字符串
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
                    chunks.extend(process_json(value, new_prefix))
            else:
                # 直接添加键值对
                chunks.append(f"{new_prefix}: {value}")
    return chunks

# 将 JSON 数据按 page 键分块
def split_by_page(data):
    if not isinstance(data, dict):
        return []

    page_chunks = []
    for key, value in data.items():
        if 'page' in key.lower():
            page_chunks.append({key: value})
        else:
            if isinstance(value, dict):
                nested_pages = split_by_page(value)
                if nested_pages:
                    page_chunks.extend(nested_pages)

    print('len of pages: ', len(page_chunks))
    return page_chunks

# 分批次处理并嵌入每个 chunk
def process_and_embed_chunks(page_chunks, batch_size=1, initial_delay=0.0, max_retries=5):
    all_texts = []
    for i in range(0, len(page_chunks), batch_size):
        batch_chunks = page_chunks[i:i + batch_size]
        batch_texts = []
        for page_chunk in batch_chunks:
            batch_texts.extend(process_json(page_chunk))

        all_texts.extend(batch_texts)

        retries = 0
        delay = initial_delay
        while retries < max_retries:
            try:
                embeddings.embed_documents(batch_texts)  # 只是为了测试 API 调用
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

# 主程序
def main():
    # json_file_path = 'E:\\PycharmProjects\\FlaskOllama\\data\\vector_crrc\\file1.json'
    json_file_path = 'output/case2/file1.json'
    save_path = "data/vector_crrc"

    # 加载 JSON 数据
    json_data = load_json_data(json_file_path)

    # 按页面分块
    page_chunks = split_by_page(json_data)

    # 处理每个 chunk
    all_texts = process_and_embed_chunks(page_chunks)
    #
    # 创建 FAISS 索引
    db = FAISS.from_texts(all_texts, embeddings)
    file_name = os.path.splitext(os.path.basename(json_file_path))[0]
    # 保存 FAISS 索引
    db.save_local(save_path, index_name=file_name)
    print('FAISS vector store successfully saved at', save_path)


if __name__ == "__main__":
    main()