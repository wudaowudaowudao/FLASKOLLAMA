'''
将 Word 文件转换为向量文件
this is only for Simulation platform
'''

import os
import time
import random
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings
import docx


class WordFaissCreator:
    def __init__(self, model="bge-m3:latest", show_progress=True):
        """
        初始化 WordFaissCreator 类
        
        Args:
            model (str): 使用的嵌入模型名称
            show_progress (bool): 是否显示进度
        """
        # 初始化 Ollama Embedding
        self.embeddings = OllamaEmbeddings(model=model, show_progress=show_progress)
    
    def load_word_data(self, file_path):
        """
        读取 Word 文件内容
        
        Args:
            file_path (str): Word 文件路径
            
        Returns:
            str: 文件内容文本
        """
        doc = docx.Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    
    def split_text(self, text, split_enter_count=10, overlap=1):
        """
        按指定数量分割文本为多个 chunk，并设置重叠部分
        
        Args:
            text (str): 要分割的文本
            split_enter_count (int): 每个 chunk 包含的段落数
            overlap (int): 重叠的段落数
            
        Returns:
            list: 分割后的文本块列表
        """
        # 按分号分割文本
        paragraphs = text.split(';')
        chunks = []
        i = 0
        while i < len(paragraphs):
            end_index = i + split_enter_count
            # 提取当前块
            chunk = '\n'.join(paragraphs[i:end_index])
            chunks.append(chunk)
            # 处理重叠部分
            i += split_enter_count - overlap
        return chunks
    
    def process_and_embed_chunks(self, chunks, batch_size=1, initial_delay=0.0, max_retries=5):
        """
        分批次处理并嵌入每个 chunk
        
        Args:
            chunks (list): 文本块列表
            batch_size (int): 每批处理的文本块数量
            initial_delay (float): 初始延迟时间(秒)
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
    
    def create_faiss(self, word_file_path, save_path):
        """
        主方法：从 Word 文件创建 FAISS 向量存储
        
        Args:
            word_file_path (str): Word 文件路径
            save_path (str): FAISS 向量存储保存路径
            
        Returns:
            str: 保存路径
        """
        # 加载 Word 数据
        word_text = self.load_word_data(word_file_path)
        print('len of word_text: ', len(word_text))

        # 分割文本为 chunk
        chunks = self.split_text(word_text)
        print('len of chunks: ', len(chunks))

        # 处理每个 chunk
        all_texts = self.process_and_embed_chunks(chunks)
        print('len of all_texts: ', len(all_texts))

        # 创建 FAISS 索引
        db = FAISS.from_texts(all_texts, self.embeddings)
        file_name = os.path.splitext(os.path.basename(word_file_path))[0]
        # 保存 FAISS 索引
        db.save_local(save_path, index_name=file_name)
        print('FAISS vector store successfully saved at', save_path)
        
        return save_path


# 主程序
def main():
    word_file_path = 'E:\PycharmProjects\FlaskOllama\data\SimuWord.docx'
    save_path = "E:\PycharmProjects\FlaskOllama\data\vector_word_db"
    
    # 创建实例并运行
    creator = WordFaissCreator()
    creator.create_faiss(word_file_path, save_path)


if __name__ == "__main__":
    main()