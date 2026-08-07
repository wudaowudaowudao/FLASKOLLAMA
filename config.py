import os

# 项目根目录
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # 限制上传文件大小为 200MB
    MAX_CONTENT_LENGTH = 600 * 1024 * 1024
    # 指定保存文件的目录
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    # 确保上传目录存在
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:crrc123@localhost:3306/chat_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CHAT_CONVERSION_RESULT_API = "http://47.92.249.78:20812"

    # 模型列表配置：键为模型名称，值为模型标识
    MODEL_LIST = {
        "斫轮-智能审查大模型:32B": "qwen3:32b",
        "斫轮-规则生成大模型:235B": "qwen3:32b",
        "斫轮-智能问答大模型:27B": "qwen3:32b",
        "斫轮-仿真知识大模型:32B": "qwen3:32b",
        "QWEN3.6":"Qwen/Qwen3.6-35B-A3B",
    }


    OLLAMA_BASE_URL = "http://127.0.0.1:11434"
    vllm_BASE_URL = "http://192.168.65.26:8000/v1"



    # 解析文件配置
    PARSE_FILE_SETTINGS = {
        'FILE_PATH': os.path.join(BASE_DIR, 'data/parse_files'),
        'DB_PATH': os.path.join(BASE_DIR, 'data/parse_files_db'),
        'BASE_FAISS_SAVE_FOLDER': os.path.join(BASE_DIR, 'data/parse_files_db'),
        'SIM_FAISS_SAVE_FOLDER': os.path.join(BASE_DIR, 'data/sim_files_db'),
        'PARSE_DATA_PATH': os.path.join(BASE_DIR, 'data/parse_files_data'),
        'PARSE_DATA_PATH_SIM': os.path.join(BASE_DIR, 'data/parse_sim_files_data')
    }
    # 确保解析文件目录存在
    if not os.path.exists(PARSE_FILE_SETTINGS['FILE_PATH']):
        os.makedirs(PARSE_FILE_SETTINGS['FILE_PATH'], exist_ok=True)

    CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
    CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'


    