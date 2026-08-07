import os
import json
from datetime import datetime
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage


class PDFQuerySystem:
    def __init__(self, user_id="default_user"):
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest")
        self.llm = ChatOllama(model="qwen3:32b")
        self.db = None
        self.user_id = user_id
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.theme = "未命名主题"
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
                temp_db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                           allow_dangerous_deserialization=True)
                if self.db is None:
                    self.db = temp_db
                else:
                    self.db.merge_from(temp_db)
            print("✅ 向量数据库加载完成。")
        except Exception as e:
            print(f"❌ 加载数据库时出错: {e}")

    def ask(self, query, session_id="default", enable_thinking=True, use_vector_db=False):
        # 如果主题还没生成，用第一次问题总结
        if self.theme == "未命名主题":
            self.theme = self._summarize_theme(query)

        final_query = query if enable_thinking else f"{query} /no_think"

        if use_vector_db:
            if not self.db:
                print("⚠️ 向量库未加载，无法进行检索问答。")
                return
            docs = self.db.similarity_search(query, k=10)
            context = "\n".join([doc.page_content for doc in docs])
            final_input = f"请根据以下内容回答问题：'{final_query}'。\n\n参考内容：\n{context}"
        else:
            final_input = final_query

        print("\n========= 模型回答开始 =========\n")
        try:
            response = ""
            for chunk in self.chain.stream(
                {"input": final_input},
                config={"configurable": {"session_id": session_id}}
            ):
                print(chunk.content, end="", flush=True)
                response += chunk.content
        except Exception as e:
            print(f"\n❌ 模型推理出错: {e}")
            return
        print("\n\n========= 模型回答结束 =========\n")
        self._save_history(session_id)
        return response

    def _save_history(self, session_id):
        path = self._get_history_file_path()
        history = self.history_store.get(session_id)
        if not history:
            return
        data = []
        for m in history.messages:
            role = "user" if isinstance(m, HumanMessage) else "ai"
            data.append({"role": role, "content": m.content})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_history_file_path(self):
        # 获取主题，如果是默认，就自动总结
        if self.theme == "未命名主题":
            self.theme = self._summarize_theme()
        folder = os.path.join("output", "chat_history", self.user_id, self.date_str, self.theme)
        return os.path.join(folder, "history.json")

    def _summarize_theme(self, first_question):
        try:
            result = self.llm.invoke([
                HumanMessage(content=f"请用不超过8个字总结这个问题的主题：\n\n{first_question}")
            ])
            summary = result.content.strip()
            return summary[:10].replace("。", "").replace("，", "") or "未命名主题"
        except Exception as e:
            print(f"⚠️ 主题总结失败: {e}")
            return "未命名主题"


    def list_themes(self):
        user_path = os.path.join("output", "chat_history", self.user_id)
        themes = []
        if os.path.exists(user_path):
            for date in os.listdir(user_path):
                date_path = os.path.join(user_path, date)
                for theme in os.listdir(date_path):
                    themes.append({"date": date, "theme": theme})
        return themes

    def load_history(self, date, theme, session_id="default"):
        path = os.path.join("output", "chat_history", self.user_id, date, theme, "history.json")
        if os.path.exists(path):
            history = InMemoryChatMessageHistory()
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for item in saved:
                    if item["role"] == "user":
                        history.add_user_message(item["content"])
                    else:
                        history.add_ai_message(item["content"])
            self.history_store[session_id] = history
            self.theme = theme
            self.date_str = date
            print(f"✅ 已加载历史主题：{theme}（{date}）")
        else:
            print("❌ 未找到历史文件")

if __name__ == "__main__":
    db_path = "/home/ubuntu/PycharmProjects/FlaskOllama/data/crrc400"  # 可修改为你的向量库路径
    user_id = input("请输入用户 ID：").strip()

    system = PDFQuerySystem(user_id=user_id)

    load_db = input("是否加载向量库？(y/n)：").strip().lower()
    if load_db == 'y':
        system.load_database(db_path)

    session_id = "default"

    print("\n📢 开始对话，输入 'q' 退出。\n")
    while True:
        query = input("\n请输入问题，输入 'q' 退出。：").strip()
        if query.lower() == "q":
            break

        think_mode = input("是否开启深度思考？(y/n)：").strip().lower()
        enable_thinking = think_mode == 'y'

        rag_mode = input("是否使用向量库？(y/n)：").strip().lower()
        use_vector_db = rag_mode == 'y'

        response = system.ask(query, session_id=session_id, enable_thinking=enable_thinking, use_vector_db=use_vector_db)
        if response:
            print(f"\n🧠 模型回答：\n{response}")

