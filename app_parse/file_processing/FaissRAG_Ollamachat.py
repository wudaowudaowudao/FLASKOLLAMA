# 可以直接使用的RAG问答
import os
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage


class PDFQuerySystem:
    def __init__(self, baichuan_api_key=None, zhipuai_api_key=None):
        if baichuan_api_key:
            os.environ["BAICHUAN_API_KEY"] = baichuan_api_key
        if zhipuai_api_key:
            os.environ["ZHIPUAI_API_KEY"] = zhipuai_api_key

        self.embeddings = OllamaEmbeddings(model="bge-m3:latest", show_progress=True)
        self.llm = ChatOllama(model="qwen3:8b")
        self.db = None

    def load_database(self, db_path):
        try:
            index_files = [os.path.splitext(os.path.basename(f))[0]
                           for f in os.listdir(db_path) if f.endswith('.faiss')]

            print('index_files: ', index_files)

            for index_file in index_files:
                if self.db is None:
                    self.db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                else:
                    temp_db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                    self.db.merge_from(temp_db)

            print("✅ 向量数据库加载成功。")

        except Exception as e:
            print(f"❌ 向量库加载失败: {e}")

    def search_and_summarize(self, query, k=5, enable_chain_of_thought=False):
        if not self.db:
            print("⚠️ 向量库未加载。")
            return

        try:
            docs_with_scores = self.db.similarity_search_with_score(query, k=k)
            sorted_docs_with_scores = sorted(
                [(doc, score) for doc, score in docs_with_scores if score < 100000.0],
                key=lambda x: x[1]
            )

            if len(sorted_docs_with_scores) == 0:
                print("⚠️ 没有找到匹配的文档。")
                return

            all_context = " ".join([
                doc.page_content for doc, score in sorted_docs_with_scores
                if hasattr(doc, 'page_content')
            ])

            # 如果不开启深度思考，则在问题后加上 /no_think
            formatted_query = query if enable_chain_of_thought else f"{query} /no_think"

            prompt = f"""以下是参考内容：\n{all_context}\n\n请根据上面的内容回答问题：'{formatted_query}'"""

            message = HumanMessage(content=prompt)

            print("\n========= 模型回答开始 =========")
            for chunk in self.llm.stream([message]):
                print(chunk.content, end="", flush=True)
            print("\n========= 模型回答结束 =========\n")

        except Exception as e:
            print(f"❌ 处理过程中出错: {e}")

    def run_interactive_mode(self):
        if not self.db:
            print("⚠️ 请先加载向量数据库。")
            return

        while True:
            query = input("\n请输入您的问题（输入 'q' 退出）：")
            if query.lower() == 'q':
                break

            mode = input("是否开启深度思考模式？(y/n)：").strip().lower()
            enable_thinking = mode == 'y'

            self.search_and_summarize(query, enable_chain_of_thought=enable_thinking)


def main():
    baichuan_api_key = "sk-xxxx"  # 可选
    zhipuai_api_key = "sk-xxxx"   # 可选
    db_path = "E:\\PycharmProjects\\FlaskOllama\\data\\vector_crrc"

    query_system = PDFQuerySystem(baichuan_api_key, zhipuai_api_key)
    query_system.load_database(db_path)
    query_system.run_interactive_mode()


if __name__ == "__main__":
    main()
