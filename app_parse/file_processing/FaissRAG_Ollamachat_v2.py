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
    def __init__(self, model_name, messages, session_id, user_id="default_user", is_pdf=True):
        self.embeddings = OllamaEmbeddings(model="bge-m3:latest", base_url=Config.OLLAMA_BASE_URL)

        if model_name not in Config.MODEL_LIST:

            raise ValueError(f"未配置的模型：{model_name}")
        actual_model_name = Config.MODEL_LIST[model_name]
        if "vllm" in model_name.lower():
            # 使用 vLLM 的 OpenAI 兼容接口
            self.llm = ChatOpenAI(
                model=actual_model_name,
                base_url=Config.vllm_BASE_URL,
                api_key="EMPTY",
                temperature=0.5,
                streaming = True,
            )
        else:
                self.llm = ChatOllama(# 使用 Ollama 的  兼容接口
                    model=actual_model_name,
                    temperature=0.5,
                    streaming=True,
                    base_url=Config.OLLAMA_BASE_URL,
            )

        self.messages = messages
        self.db = None
        self.user_id = user_id
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.final_input = ""
        self.ai_answer = []
        self.source_attributions = []
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

    def load_database(self, db_path, source_name=None, index_name=None):
        try:
            print("======================" + str(db_path))
            if index_name:
                index_files = [os.path.splitext(os.path.basename(index_name))[0]]
            else:
                index_files = [os.path.splitext(f)[0] for f in os.listdir(db_path) if f.endswith(".faiss")]
            for index_file in index_files:
                temp_db = FAISS.load_local(db_path, self.embeddings, index_name=index_file,
                                           allow_dangerous_deserialization=True)
                # Older indexes do not carry LangChain metadata. Attach the
                # source while the index identity is still known, before
                # merging it into the shared vector store.
                source = source_name or index_file
                for document in temp_db.docstore._dict.values():
                    document.metadata = dict(document.metadata or {})
                    document.metadata.setdefault("source", source)
                if self.db is None:
                    self.db = temp_db
                else:
                    self.db.merge_from(temp_db)
            print("✅ 向量数据库加载完成。")
        except Exception as e:
            print(f"❌ 加载数据库时出错: {e}")

    def generate(self):
        print("final_input:" + self.final_input)
        print("history:" + str(self.messages))
        # nonlocal ai_answer  # 声明使用外部变量
        for chunk in self.chain.stream({"input": self.final_input, "history": self.messages}):
            chunk_content = chunk.content
            self.ai_answer.append(chunk_content)
            print(chunk_content, end="", flush=True)
            yield f'{chunk_content}'

        footer = ""
        if self.source_attributions:
            lines = ["知识来源："]
            lines.extend(
                f"{index}. {item['source']}（命中 {item['hits']} 个片段，最佳排名 #{item['best_rank']}）"
                for index, item in enumerate(self.source_attributions, start=1)
            )
            footer = "\n\n" + "\n".join(lines)
            yield footer

        ChatMessage.create_Chat(
            self.session_id, self.question, ''.join(self.ai_answer) + footer
        )

    def set_final_input(self, query, use_vector_db=False, enable_thinking=True):
        self.question = query
        final_query = query if enable_thinking else f"{query} /no_think"
        if use_vector_db:
            if not self.db:
                print("⚠️ 向量库未加载，无法进行检索问答。")
                return
            docs_with_scores = self.db.similarity_search_with_score(query, k=10)
            source_groups = {}
            for rank, (doc, _score) in enumerate(docs_with_scores, start=1):
                source = (doc.metadata or {}).get("source") or "未标注来源"
                group = source_groups.setdefault(
                    source, {"source": source, "hits": 0, "best_rank": rank}
                )
                group["hits"] += 1
                group["best_rank"] = min(group["best_rank"], rank)
            self.source_attributions = sorted(
                source_groups.values(),
                key=lambda item: (-item["hits"], item["best_rank"], item["source"]),
            )[:5]
            docs = [doc for doc, _score in docs_with_scores]
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
                    # config={"configurable": {"session_id": session_id}}
            ):
                print(chunk.content, end="", flush=True)
                response += chunk.content
        except Exception as e:
            print(f"\n❌ 模型推理出错: {e}")
            return
        print("\n\n========= 模型回答结束 =========\n")
        # self._save_history(session_id)
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

        response = system.ask(query, session_id=session_id, enable_thinking=enable_thinking,
                              use_vector_db=use_vector_db)
        if response:
            print(f"\n🧠 模型回答：\n{response}")
