'''
比较稳定的一个版本
拥有功能:
1.深度思考的开关
2.多向量库的合并
3.使用OLLAMA的QWEN3模型
'''


import os
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage
from config import OLLAMA_BASE_URL


class PDFQuerySystem:
    def __init__(self,model="qwen3:32b"):
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest")
        self.llm = ChatOllama(model=model,
            temperature=0.5,
            streaming=True,
            base_url=OLLAMA_BASE_URL)
        self.db = None
        self.history_store = {}

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个严谨的PDF问答助手。"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        self.chain = RunnableWithMessageHistory(
            self.prompt | self.llm,
            self._get_history,
            input_messages_key="input",
            history_messages_key="history"
        )

    def _get_history(self, session_id):
        if session_id not in self.history_store:
            self.history_store[session_id] = InMemoryChatMessageHistory()
        return self.history_store[session_id]

    def load_database(self, db_path):
        try:
            index_files = [os.path.splitext(f)[0] for f in os.listdir(db_path) if f.endswith(".faiss")]
            for index_file in index_files:
                if self.db is None:
                    self.db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                else:
                    temp_db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                               allow_dangerous_deserialization=True)
                    self.db.merge_from(temp_db)
            print("✅ 向量数据库加载完成。")
        except Exception as e:
            print(f"❌ 加载数据库时出错: {e}")

    def ask(self, query, session_id="default", enable_thinking=True):
        if not self.db:
            print("⚠️ 请先加载数据库。")
            return

        # 向量检索
        docs = self.db.similarity_search(query, k=10)
        context = "\n".join([doc.page_content for doc in docs])

        # 控制是否 /no_think
        final_query = query if enable_thinking else f"{query} /no_think"

        final_input = f"请根据以下内容回答问题：'{final_query}'。\n\n参考内容：\n{context}"
        print("\n========= 模型回答开始 =========\n")

        try:
            for chunk in self.chain.stream(
                {"input": final_input},
                config={"configurable": {"session_id": session_id}}
            ):
                print(chunk.content, end="", flush=True)
        except Exception as e:
            print(f"\n❌ 模型推理出错: {e}")
        print("\n\n========= 模型回答结束 =========\n")

    def run(self, session_id="default"):
        while True:
            query = input("\n请输入问题（输入 q 退出）：").strip()
            if query.lower() == "q":
                break
            mode = input("是否开启深度思考？(y/n)：").strip().lower()
            enable_thinking = mode == 'y'
            self.ask(query, session_id=session_id, enable_thinking=enable_thinking)


if __name__ == "__main__":
    db_path = "/home/ubuntu/PycharmProjects/FlaskOllama/data/crrc400"  # 你自己的路径
    session_id = "user_001"

    system = PDFQuerySystem()
    system.load_database(db_path)
    system.run(session_id=session_id)
