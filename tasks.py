import os

from app_parse.file_processing.parsefile import ParseFile
from celery.result import AsyncResult
from config import Config
from celery import Celery
import json
import zipfile
from io import BytesIO
import requests
import time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app_parse.file_processing.jsonFaissCreate_Local_v02 import JsonFaissCreator
from app_parse.file_processing.markdownFaissCreate_Local import MarkdownFaissCreator
from app_parse.file_processing.wordFaissCreate_Local_v1 import WordFaissCreator
from app_parse.file_processing.RuleToXML_v3_API import RuleToXMLConverter

# 创建数据库引擎和会话
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def update_knowledge_status(file_id, status):
    """更新知识库状态

    Args:
        file_id: 文件ID
        status: 状态值 (processing/failed/completed)
    """
    db = SessionLocal()
    try:
        db.execute(text("UPDATE knowledge_base SET status = :status WHERE id = :file_id"),
                  {'status': status, 'file_id': file_id})
        db.commit()
    finally:
        db.close()

PARSE_DATA_PATH = Config.PARSE_FILE_SETTINGS['PARSE_DATA_PATH']
# 创建 Celery 实例
celery = Celery('tasks', broker=Config.CELERY_BROKER_URL)
celery.conf.update({'result_backend': Config.CELERY_RESULT_BACKEND}, worker_concurrency=1)

@celery.task
def create_rule(file_path,xml_path, ext,file_name,moudule,file_id):
    url = f"{Config.CHAT_CONVERSION_RESULT_API}/open/chat/conversionResult"
    # 获取xml文件的文件名
    xml_filename = os.path.basename(xml_path)
    # 构建下载URL (假设文件可以通过项目的/uploads路径访问)
    download_url = f"/api/download/{xml_filename}"
    payload = {
        "analysisFilePath": download_url,
        "id": file_id,
        "status": 2,
        "type": 2
    }
    headers = {'Content-Type': 'application/json'}

    print("=====================")
    print(file_path)
    print(xml_path)

    try:
        converter = RuleToXMLConverter()
        converter.process(file_path, "xmlGenerator/rule_base.xml", xml_path, ext, file_name)
        payload["status"] = 3

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
        except Exception as req_e:
            print(f"Failed to send result: {req_e}")

    except Exception as e:
        # 发送失败状态请求
        payload['status']=4
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
        except Exception as req_e:
            print(f"Failed to send error result: {req_e}")

        return {'status': 'error', 'message': str(e)}




@celery.task
def create_faiss(file_path,ext,faiss_save_folder, file_id,file_name):
    try:
        update_knowledge_status(file_id, 'processing')
        callback_timeout = (10, float(os.getenv('FLASKOLLAMA_CALLBACK_TIMEOUT', '30')))
        url = f"{Config.CHAT_CONVERSION_RESULT_API}/open/chat/conversionResult"
        payload = {
            "analysisFilePath": file_id,
            "id": file_id,
            "status": 2,
            "type": 1
        }
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=callback_timeout)
            response.raise_for_status()
        except Exception as req_e:
            print(f"Failed to send result: {req_e}")

        # 处理成功，发送请求
        payload["status"]=3

        # 根据不同后缀调用不同的处理函数
        if ext == 'md':
            # 处理md文件
            creator = MarkdownFaissCreator()
            creator.create_faiss(file_path, faiss_save_folder)

        elif ext == 'doc' or ext == 'docx':
            # 处理word文件
            creator = WordFaissCreator()
            creator.create_faiss(file_path, faiss_save_folder)

        elif ext == 'json':
            # 处理json文件
            creator = JsonFaissCreator()
            creator.create_faiss_index(file_path, faiss_save_folder)

        elif ext == 'pdf':
            # PDF 交给独立的 9540 解析服务，8550 只负责把解析 JSON 建成向量。
            fragment_url = os.getenv('FLASKOLLAMA_FRAGMENT_URL', 'http://127.0.0.1:9540').rstrip('/')
            parse_payload = {
                'fileData': {'fileId': str(file_id), 'fileName': file_name + '.pdf'},
                'parseOptions': {'fileLanguage': 'ch', 'wordsRecInterface': '0'},
            }
            with open(file_path, 'rb') as source:
                response = requests.post(
                    fragment_url + '/parsefile',
                    files={'file': (os.path.basename(file_path), source, 'application/pdf')},
                    data={'json_data': json.dumps(parse_payload, ensure_ascii=False)},
                    timeout=(10, 60),
                )
            response.raise_for_status()
            fragment_task_id = response.json().get('task_id')
            if not fragment_task_id:
                raise RuntimeError('fragment parser returned no task_id')

            deadline = time.monotonic() + float(os.getenv('FLASKOLLAMA_FRAGMENT_TIMEOUT', '1800'))
            parsed = None
            while time.monotonic() < deadline:
                poll = requests.get(fragment_url + '/get_result/' + str(fragment_task_id), timeout=(10, 60))
                if poll.status_code == 202:
                    time.sleep(2)
                    continue
                poll.raise_for_status()
                parsed = poll.json()
                break
            if not parsed or parsed.get('status') != 'success':
                raise RuntimeError('fragment parser did not complete successfully')

            parsed_json = parsed.get('json_content')
            if not parsed_json:
                raise RuntimeError('fragment parser returned empty json_content')
            parsed_path = Path(file_path).with_name(str(file_id) + '_content_list.json')
            parsed_path.write_text(parsed_json, encoding='utf-8')
            creator = JsonFaissCreator()
            creator.create_faiss_index(str(parsed_path), faiss_save_folder)

        else:
            payload["status"]=1

            #raise ValueError(f"Unsupported file extension: {ext}")


        update_knowledge_status(file_id, 'completed' if payload.get('status') == 3 else 'failed')
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=callback_timeout)
            response.raise_for_status()
        except Exception as req_e:
            print(f"Failed to send result: {req_e}")

    except Exception as e:
        update_knowledge_status(file_id, 'failed')
        # 发送失败状态请求
        payload = {
            "analysisFilePath": file_id,
            "id": file_id,
            "status": 4,
            "type": 1
        }
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=callback_timeout)
            response.raise_for_status()
        except Exception as req_e:
            print(f"Failed to send error result: {req_e}")

        return {'status': 'error', 'message': str(e)}



@celery.task
def parse_file(file_path, file_id,file_name):
    try:
        # 导入Flask应用并创建上下文
        # 直接连接数据库更新状态
        update_knowledge_status(file_id, 'processing')
        parse_file = ParseFile()

        # 创建解析实例并处理
        parse_file.set_parse_param("ch", "0", file_id,file_name)
        #print(f'accept:: {file_data}')
        res = parse_file.Parse_work(file_path, file_id,file_name)

        if res != "":
            update_knowledge_status(file_id, 'failed')
            return {'status': 'error', 'message': f'文件解析错误:{res}'}
        else:            
            # 更新KnowledgeBase状态为completed
            update_knowledge_status(file_id, 'completed')
            json_info = {'status': 'success', 'fileId': file_id, 'message': '文件解析完成'}
            return json_info

    except Exception as e:
        strRes = str(e).lower().replace('magic', 'Parser').replace('mineru', 'ParserPDF')
        return {'status': 'error', 'message': strRes}
