import json
import os
import time
import random
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings


# 读取 JSON 文件
def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 递归处理 JSON 数据，生成 text chunk
def process_json(data, prefix=''):
    chunks = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_prefix = f"{prefix} -> {key}" if prefix else key
            if isinstance(value, dict):
                if all(isinstance(v, (str, int, float, bool, list)) for v in value.values()):
                    chunk = f"{new_prefix}:\n"
                    for k, v in value.items():
                        if isinstance(v, list):
                            processed_list_items = []
                            for i, item in enumerate(v, start=1):
                                res = process_json(item, '')
                                if res:
                                    processed_list_items.append(f"{i}. {res[0]}")
                                else:
                                    processed_list_items.append(f"{i}. {str(item)}")
                            chunk += f"{k}: " + "\n".join(processed_list_items) + "\n"
                        else:
                            chunk += f"{k}: {v}\n"
                    chunks.append(chunk.strip())
                else:
                    chunks.extend(process_json(value, new_prefix))
            else:
                chunks.append(f"{new_prefix}: {value}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            chunks.extend(process_json(item, f"{prefix}[{i}]"))

    return chunks

# 分割 JSON 数据为多个 "页面块"
def split_by_page(data):
    if isinstance(data, dict):
        if 'page_idx' in data:
            return [data]
        else:
            chunks = []
            for value in data.values():
                chunks.extend(split_by_page(value))
            return chunks
    elif isinstance(data, list):
        chunks = []
        for item in data:
            chunks.extend(split_by_page(item))
        return chunks
    else:
        return []

# 嵌入每个 chunk（批处理 + 重试机制）
def process_and_embed_chunks(page_chunks, embeddings, batch_size=1, initial_delay=0.0, max_retries=5):
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
                embeddings.embed_documents(batch_texts)  # 调用一次测试 API
                break
            except Exception as e:
                retries += 1
                print(f"Error occurred: {e}")
                if retries < max_retries:
                    delay *= 2
                    jitter = random.uniform(0, 0.1 * delay)
                    wait_time = delay + jitter
                    print(f"Retrying in {wait_time:.2f} seconds... ({retries}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached, skipping this batch.")
        time.sleep(initial_delay)

    return all_texts

# 主流程（参数可外部传入）
def run_vectorization_pipeline(json_file_path, save_path, model_name="bge-m3:latest"):
    embeddings = OllamaEmbeddings(model=model_name, show_progress=True)

    json_data = load_json_data(json_file_path)
    page_chunks = split_by_page(json_data)
    print(f"📄 Total page chunks found: {len(page_chunks)}")

    all_texts = process_and_embed_chunks(page_chunks, embeddings)

    db = FAISS.from_texts(all_texts, embeddings)

    file_name = os.path.splitext(os.path.basename(json_file_path))[0]
    db.save_local(save_path, index_name=file_name)
    print(f"✅ FAISS vector store saved at: {os.path.join(save_path, file_name)}")


# 只在这里修改路径！
if __name__ == "__main__":
    json_file_path = "/home/ubuntu/PycharmProjects/FlaskOllama/data/crrc400/crrc_scan_content_list.json"
    save_path = "/home/ubuntu/PycharmProjects/FlaskOllama/data/crrc400"
    run_vectorization_pipeline(json_file_path, save_path)
