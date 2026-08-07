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
from app_parse.DataManager.DB_Manager import ChatMessage
from config import Config
from langchain_openai import ChatOpenAI

class PDFQuerySystem:
    def __init__(self, model_name,messages,session_id,user_id="default_user",is_pdf=True):
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest",base_url=Config.OLLAMA_BASE_URL)
        # self.llm = ChatOllama( # 调用使用的Ollama的接口
        #     model=f"{model_name}",
        #     temperature=0.5,
        #     streaming=True,
        #     base_url=Config.OLLAMA_BASE_URL
        # )1
        self.llm = ChatOpenAI(  #调用使用的vllm的接口
            model="Qwen/Qwen3.6-35B-A3B",
            base_url="http://192.168.65.26:8000/v1",
            api_key="EMPTY",
            temperature=0.5,
            streaming=True,
        )

        self.messages = messages
        self.db = None
        self.user_id = user_id
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.final_input = ""
        self.ai_answer = []
        self.question = ""
        self.session_id = session_id
        self.is_pdf = is_pdf
        if is_pdf:
            prompt_template = "你是一个严谨的PDF问答助手。"
        else:
            prompt_template = "你是一个严谨的问答助手。"
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_template),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def load_database(self, db_path):
        try:
            print("======================"+str(db_path))
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

    def generate(self):
        print("final_input:"+ self.final_input)
        print("history:"+ str(self.messages))
       # nonlocal ai_answer  # 声明使用外部变量        
        for chunk in self.chain.stream( {"input": self.final_input,"history":self.messages}):
            chunk_content = chunk.content
            self.ai_answer.append(chunk_content)
            print(chunk_content, end="", flush=True)
            yield f'{chunk_content}'
        
        ChatMessage.create_Chat(self.session_id, self.question, ''.join(self.ai_answer))

    def set_final_input(self, query,use_vector_db=False,enable_thinking=True):
        self.question = query
        final_query = query if enable_thinking else f"{query} /no_think"
        if use_vector_db:
            if not self.db:
                print("⚠️ 向量库未加载，无法进行检索问答。")
                return
            docs = self.db.similarity_search(query, k=10)
            context = "\n".join([doc.page_content for doc in docs])
            self.final_input = f"请根据以下内容回答问题：'{final_query}'。\n\n参考内容：\n{context}"
        else:
            self.final_input = final_query


    def ask(self, query, enable_thinking=True, use_vector_db=False):
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
                #config={"configurable": {"session_id": session_id}}
            ):
                print(chunk.content, end="", flush=True)
                response += chunk.content
        except Exception as e:
            print(f"\n❌ 模型推理出错: {e}")
            return
        print("\n\n========= 模型回答结束 =========\n")
        #self._save_history(session_id)
        return response

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

