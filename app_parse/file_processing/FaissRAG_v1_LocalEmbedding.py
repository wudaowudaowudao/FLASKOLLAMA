'''
调取向量库
进行查询
llm本地化，
Embedding本地化
'''

import os
from langchain_community.embeddings import BaichuanTextEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatZhipuAI
from langchain_core.messages import HumanMessage
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.chat_models import ChatOllama


class PDFQuerySystem:
    def __init__(self, **kwargs):
        # os.environ["BAICHUAN_API_KEY"] = baichuan_api_key
        # os.environ["ZHIPUAI_API_KEY"] = zhipuai_api_key

        # self.embeddings = BaichuanTextEmbeddings(baichuan_api_key=os.getenv("BAICHUAN_API_KEY"))
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest", show_progress=True)
        # 修改为使用 Ollama 的 qwen2:1.5b 模型
        self.llm = ChatOllama(model="qwen3:8b")
        # self.llm = ChatOllama(model="glm4:latest")
        self.db = None

    def load_database(self, db_path):
        try:
            # 获取db_path文件夹中所有以 .faiss 结尾的文件名，并去掉扩展名
            index_files = [os.path.splitext(os.path.basename(f))[0]
                           for f in os.listdir(db_path)
                           if f.endswith('.faiss')]
            print('index_files: ', index_files)
            # 遍历每个文件，加载索引并合并到self.db
            for index_file in index_files:
                if self.db is None:
                    # 第一个文件直接加载
                    self.db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                else:
                    # 其他文件合并到已有索引
                    temp_db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                    self.db.merge_from(temp_db)

            print("Vector database loaded successfully.")
        except Exception as e:
            print(f"Error loading the database: {e}")

    def search_and_summarize(self, query, k=5):
        if not self.db:
            print("Database not loaded. Please load a database first.")
            return None

        try:
            docs_with_scores = self.db.similarity_search_with_score(query, k=k)
            # 按score排序
            sorted_docs_with_scores = sorted(
                [(doc, score) for doc, score in docs_with_scores if score < 100000.0],
                key=lambda x: x[1]
            )

            print(f"Number of relevant documents found: {len(sorted_docs_with_scores)}")

            if len(sorted_docs_with_scores) == 0:
                print("No documents found with the required score threshold.")
                return None

            # 列举所有相关条目
            for doc, score in sorted_docs_with_scores:
                print(f"Document score: {score:.4f}")
                print('*************content**************')
                print(doc.page_content if hasattr(doc, 'page_content') else '')
                print('*************content**************')

            # 将所有相关内容进行总结
            all_context = " ".join([doc.page_content for doc, score in sorted_docs_with_scores if hasattr(doc, 'page_content')])
            prompt = f"根据以下内容总结回答问题'{query}'：\n\n{all_context}"
            message = HumanMessage(content=prompt)
            summary_response = self.llm.invoke([message])

            return summary_response.content

        except Exception as e:
            print(f"Error during search or summarization: {e}")
            return None

    def run_interactive_mode(self):
        if not self.db:
            print("Database not loaded. Please load a database first.")
            return

        while True:
            query = input("请输入您的问题 (输入 'q' 退出): ")
            if query.lower() == 'q':
                break

            answer = self.search_and_summarize(query)
            if answer:
                print(f"总结: {answer}\n")


def main():
    # baichuan_api_key = "sk-9c8de2cf7d808d120bb88dea8ecdd3cc"
    # zhipuai_api_key = "57122259c07b1f120a083a82fed91a1d.cNPaEpVy3psGvZfI"
    # db_path = "vector_zhuzhou"  # 向量数据库的路径
    # db_path = "E:\\PycharmProjects\\FlaskOllama\\data\\vector_md_db"  # 向量数据库的路径
    db_path = "E:\\PycharmProjects\\FlaskOllama\\data\\vector_json_db"  # 向量数据库的路径

    # query_system = PDFQuerySystem(baichuan_api_key, zhipuai_api_key)
    query_system = PDFQuerySystem()
    query_system.load_database(db_path)
    query_system.run_interactive_mode()


if __name__ == "__main__":
    main()
