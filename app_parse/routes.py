import os
from datetime import datetime
import json
from flask import Blueprint, request, send_file, jsonify, url_for, send_from_directory  # 导入 jsonify
import time
from io import BytesIO
from app_parse.modelChecker.checker import XMLRuleChecker
from app_parse.file_processing.pdf_processor import get_file_size, get_pdf_pages
from langchain_community.chat_models import ChatOllama
from langchain.schema import HumanMessage, SystemMessage
from app_parse.file_processing.jsonFaissCreate_Local import JsonFaissCreator  # 导入 JsonFaissCreator 类
from app_parse.file_processing.FaissRAG_Ollamachat_v2 import PDFQuerySystem  # 导入修改后的 PDFQuerySystem 类
from flask import Response, session
import uuid
from app_parse.DataManager.DB_Manager import ChatMessage,ChatSession,KnowledgeBase,FileSet
from app_parse import db
from flask import Blueprint, request, jsonify, current_app

#from client_script import answer
from config import Config
from app_parse.file_processing.RuleToXML_v3_API import RuleToXMLConverter
main = Blueprint('main', __name__)


def _parse_request_id_list(raw_value):
    """Accept comma-separated or JSON-array request fields.

    The historical frontend has sent both ``id1,id2`` and
    ``["id1", "id2"]`` representations for vector-database selections.
    Keeping this normalization at the knowledge-base boundary lets the
    VLLM proxy forward multipart bodies without buffering or rewriting them.
    """
    if raw_value is None:
        return []

    if isinstance(raw_value, (list, tuple)):
        values = raw_value
    else:
        value = str(raw_value).strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        values = parsed if isinstance(parsed, list) else value.split(',')

    return [str(item).strip() for item in values if str(item).strip()]

# 基础上传文件夹
BASE_UPLOAD_FOLDER = 'uploads'
SIM_UPLOAD_FOLDER = 'Simuploads'
# 保存 FAISS 索引的基础文件夹
BASE_FAISS_SAVE_FOLDER = Config.PARSE_FILE_SETTINGS['BASE_FAISS_SAVE_FOLDER']
SIM_FAISS_SAVE_FOLDER = Config.PARSE_FILE_SETTINGS['SIM_FAISS_SAVE_FOLDER']
FILE_PATH = Config.PARSE_FILE_SETTINGS['FILE_PATH']
os.makedirs(FILE_PATH, exist_ok=True)

def handle_file_upload(processor_func):
    try:
        if 'file1' not in request.files:
            return jsonify({"code": 400, "message": "No file part", "data": None}), 400
        file = request.files['file1']
        if file.filename == '':
            return jsonify({"code": 400, "message": "No selected file", "data": None}), 400
        if file:
            # 获取当前日期并创建对应的文件夹名称
            today = datetime.today().strftime('%Y-%m-%d')
            daily_upload_folder = os.path.join(BASE_UPLOAD_FOLDER, today)
            if not os.path.exists(daily_upload_folder):
                os.makedirs(daily_upload_folder)
            
            file_path = os.path.join(daily_upload_folder, file.filename)
            file.save(file_path)
            result = processor_func(file_path)
            return jsonify({"code": 200, "message": "success", "data": result}), 200
    except FileNotFoundError:
        return jsonify({"code": 500, "message": "File not found during processing", "data": None}), 500
    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

@main.route('/upload/size', methods=['POST'])
def upload_file_size():
    return handle_file_upload(get_file_size)

@main.route('/upload/pages', methods=['POST'])
def upload_file_pages():
    return handle_file_upload(get_pdf_pages)

@main.route('/chat/history', methods=['GET'])
def get_chat_history():
    try:
        # 获取客户端传入的查询参数（包含user_id）
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({"code": 400, "message": "userId is required", "data": None}), 400

        # 查询ChatSession表（假设表有create_time字段用于排序）
        from app_parse.DataManager.DB_Manager import ChatSession  # 导入模型
        sessions = ChatSession.query.filter_by(user_id=user_id)\
                                   .order_by(ChatSession.timestamp.desc())\
                                   .all()

        # 转换为客户端需要的格式（仅返回session_id和session_name）
        result = [{'sessionId': session.session_id, 'sessionName': session.session_name} 
                  for session in sessions]
        return jsonify({"code": 200, "message": "success", "data": result}), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

@main.route('/download/<filename>')
@main.route('/api/download/<filename>')
def download_file(filename):
    directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
    return send_from_directory(directory, filename, as_attachment=True)

@main.route('/chat/message', methods=['GET'])
def get_chat_message():
    try:
        # 获取客户端传入的查询参数（包含session_id和page）
        session_id = request.args.get('sessionId')
        page = request.args.get('page', 1, type=int)  # 默认第1页

        # 参数校验
        if not session_id:
            return jsonify({"code": 400, "message": "sessionId is required", "data": None}), 400
        if page < 1:
            return jsonify({"code": 400, "message": "page must be a positive integer", "data": None}), 400

        # 计算分页偏移量（每页5条）
        per_page = 5
        offset = (page - 1) * per_page

        # 查询ChatMessage表（按时间升序，分页查询）
        messages = ChatMessage.query.filter_by(session_id=session_id)\
                                   .order_by(ChatMessage.timestamp.asc())\
                                   .offset(offset)\
                                   .limit(per_page)\
                                   .all()

        # 转换为客户端需要的格式（仅返回question和answer）
        result = [{'question': message.question, 'answer': message.answer}\
                  for message in messages]
        return jsonify({"code": 200, "message": "success", "data": {"data": result, "page": page, "per_page": per_page}}), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500
        
@main.route('/get/new/sessionId', methods=['GET'])
def generate_new_session_id():
    """生成新的会话ID（UUID格式）"""
    # 生成UUID4格式的唯一会话ID
    session_id = str(uuid.uuid4())
    # 返回JSON格式响应
    return jsonify({"code": 200, "message": "success", "data": {"sessionId": session_id}}), 200

@main.route('/get/repository/list', methods=['GET'])
def get_repository_list():
    try:
        # 获取query参数
        userId = request.args.get('userId')
        if not userId:
            return jsonify({"code": 400, "message": "userId is required", "data": None}), 400

        # 查询用户的文件集列表，按创建时间降序排列
        filesets = FileSet.query.filter_by(user_id=userId).order_by(FileSet.created_at.desc()).all()
        # 提取id、name和created_at字段
        result = [{'id': fs.id, 'name': fs.name, 'created_at': fs.created_at} for fs in filesets]
        return jsonify({"code": 200, "message": "success", "data": result}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/get/file/list', methods=['GET'])
def get_file_list():
    try:
        # 获取query参数
        setId = request.args.get('setId')
        if not setId:
            return jsonify({"code": 400, "message": "setId is required", "data": None}), 400

        # 查询指定文件集下的文件列表
        files = KnowledgeBase.query.filter_by(file_set_id=setId).all()
        # 提取所需字段
        result = [{
            'file_id': file.id,
            'filename': file.name,
            'status': file.status
        } for file in files]
        return jsonify({"code": 200, "message": "success", "data": result}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/get/moudle/list', methods=['GET'])
def get_moudle_list():
    try:
        # 从配置中获取模型列表
        model_list = current_app.config.get('MODEL_LIST', {})
        # 转换为列表格式返回
        result = list(model_list.keys())
        return jsonify({"code": 200, "message": "success", "data": result}), 200
    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

import json
@main.route('/chat', methods=['POST'],defaults={'timeout': 3600})
def ollama_qa(timeout):
    try:
        # 获取客户端传入的数据
        print("chat accept")
        question = request.form.get('question')   
        user_id = request.form.get('userId',"admin")       
        if not question:
            return jsonify({"code": 400, "message": "No question provided", "data": None}), 400 

        session_id = request.form.get('sessionId',"")
        if not session_id or session_id == "":
            return jsonify({"code": 400, "message": "No sessionId provided", "data": None}), 400 

        # ``moudleId`` is the historical spelling; newer clients use
        # ``moduleId``. Accept both at the service boundary.
        moudleId = request.form.get('moudleId') or request.form.get('moduleId', "")
        if not moudleId or moudleId == "":
            return jsonify({"code": 400, "message": "No moudleId provided", "data": None}), 400 
        model_config = current_app.config.get('MODEL_LIST', {})
        model_value = model_config.get(moudleId)
        if not model_value:
            return jsonify({"code": 404, "message": f'Model with moudleId {moudleId} not found', "data": None}), 404

        category =  request.form.get('category',"")
        if not category or category == "":
            return jsonify({"code": 400, "message": "No category provided", "data": None}), 400   
        
        print(f"category:{category}")

        print(f"moudleId:{moudleId}")
        generationDb_str = request.form.get('generationDb', '')
        generationDb = _parse_request_id_list(generationDb_str)
        # The intelligent-review model is also used for knowledge-base Q&A.
        # Enter the drawing-audit branch only when the frontend actually
        # supplied generation rules; otherwise continue to loadVectorDb below.
        if "智能审查" in moudleId and generationDb:

            print(f"generationDb:{generationDb_str}")

            xml_paths=[]
            for loadVectorRule in generationDb:
                xml_path = os.path.join(BASE_UPLOAD_FOLDER, f"{loadVectorRule}.xml")

                #暂时写死规则来源
                #xml_path = os.path.join(BASE_UPLOAD_FOLDER, "/home/crrc/PycharmProjects/FlaskOllama/templates/simulated_rule_CAH234_03_00_001_A_dwg1.xml")
                xml_paths.append(xml_path)

            print(f"generationDb:{len(generationDb)}")

            files = request.form.get('file',"")
            print(f"files:{files}")

            files = request.files.getlist('file')
            #print(f"files:{len(files)}")
            # 验证form-data文件上传
            if not files :
                return jsonify({'error': '未上传有效文件'}), 400

            file_id_att = str(uuid.uuid4())
            # 获取当前日期并创建对应的文件夹名称
            if not os.path.exists(BASE_UPLOAD_FOLDER):
                os.makedirs(BASE_UPLOAD_FOLDER)

            file = files[0]
            ext = os.path.splitext(file.filename)[1]  # 提取文件后缀
            file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id_att}{ext}")
            file.save(file_path)

            output_dir = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id_att}")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)


            checker = XMLRuleChecker(rule_file=xml_paths, target_file=file_path, output_folder=output_dir)
            result = checker.run()

            # if result:
                # 流式生成JSON结果
                # def generate_json_result():
                #     json_result = json.dumps(result["result"], indent=2, ensure_ascii=False)
                #
                #     # 分块发送JSON结果
                #     chunk_size = 1024
                #     for i in range(0, len(json_result), chunk_size):
                #         yield json_result[i:i + chunk_size]
                #         time.sleep(0.05)  # 控制流传输速度
                # response = Response(generate_json_result(), mimetype='application/json', headers={
                #     'Cache-Control': 'no-cache',
                #     'X-Accel-Buffering': 'no'
                # })
            if result:
                # 这是 Markdown 格式的字符串，不需要 json.dumps()
                markdown_result = result["result"]

                # 替换换行，确保前端能正确渲染为换行
                result_with_linebreaks = markdown_result.replace('\n\n', '\n<br>\n')  # 段落换行
                result_with_linebreaks = result_with_linebreaks.replace('\n', '<br>\n')  # 单行换行

                def generate_markdown_result():
                    chunks = result_with_linebreaks.split('<br>\n')
                    for chunk in chunks:
                        yield chunk + '<br>\n'
                        time.sleep(0.05)

                response = Response(generate_markdown_result(), mimetype='text/markdown', headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                })
                return response

        loadVectorDb_str = request.form.get('loadVectorDb', '')
        loadVectorDb = _parse_request_id_list(loadVectorDb_str)



        # 调用独立查询函数获取聊天记录（按时间排序）
        chat_records = ChatMessage.get_chat_history_by_session(session_id)

        file_list = []
        if category == "4":

            files = request.files.getlist('file')
            # 验证form-data文件上传
            if not files or all(f.filename == '' for f in files):
                return jsonify({'error': '未上传有效文件'}), 400
            for file in files:
                if file.filename.strip() == '':
                    continue  # 跳过空文件
                file_id_att = str(uuid.uuid4())
                # 获取当前日期并创建对应的文件夹名称
                if not os.path.exists(BASE_UPLOAD_FOLDER):
                    os.makedirs(BASE_UPLOAD_FOLDER)
                
                xml_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id_att}.xml")
                ext = os.path.splitext(file.filename)[1]  # 提取文件后缀
                file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id_att}{ext}")
                file.save(file_path)

                #临时用API
                # converter = RuleToXMLConverter(model_value)
                converter = RuleToXMLConverter()

                converter.process(file_path, "xmlGenerator/rule_base.xml", xml_path,ext,file.filename)

                # 生成下载链接
                filename = os.path.basename(xml_path)
                download_url = url_for('main.download_file', filename=filename)
                file_list.append("/api" + download_url)

            # 生成完成后保存聊天记录（需在响应返回前提交事务）
            session_name = question if question else "New Session"
            if chat_records == []:
                ChatSession.create_session(session_id, user_id, session_name)
            # 流式生成Markdown链接
            def generate_links():
                for i, url in enumerate(file_list):
                    yield f'{i+1}. [下载文件 {i+1}]({url})\n'
                    time.sleep(0.1)  # 控制流传输速度
            response = Response(generate_links(), mimetype='text/event-stream', headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            })

            answer_1 = ""
            for i, url in enumerate(file_list):
                answer_1 = answer_1 + f'{i+1}. [下载文件 {i+1}]({url})\n'
            ChatMessage.create_Chat(session_id, question, answer_1)
            return response

    

        # 构造包含question和answer的历史对话列表
        history = []
        # 按顺序遍历聊天记录（假设用户消息和AI消息交替存储）
        for record in chat_records:
            if record.question:
                history.append({
                    "question": record.question,
                    "answer": record.answer
                })

        
        # 构造完整的对话历史作为上下文
        messages = []
        for item in history:
            answer = item["answer"] or ""
            # 来源段落是展示信息，不应再次作为模型上下文，否则模型可能
            # 在新回答中复述上一轮的来源列表。
            answer = answer.split("\n\n知识来源：", 1)[0]
            messages.append(HumanMessage(content=item["question"]))
            messages.append(SystemMessage(content=answer))
        #messages.append(HumanMessage(content=question))

        Query_system = PDFQuerySystem(
            model_name=moudleId,
            messages=messages,
            session_id=session_id,
            user_id=user_id,
            is_pdf=len(loadVectorDb) > 0
        )

        print("===================="+str(loadVectorDb))
        def source_name_for(identifier):
            knowledge_file = KnowledgeBase.query.filter_by(id=identifier).first()
            if knowledge_file and knowledge_file.name:
                return knowledge_file.name
            file_set = FileSet.query.filter_by(id=identifier).first()
            if file_set and file_set.name:
                return file_set.name
            return str(identifier)

        # 查询指定ID对应的db_path列表
        for set_id in loadVectorDb:
            if os.path.exists(os.path.join(BASE_FAISS_SAVE_FOLDER, f"{set_id}")):
                faiss_id_path = os.path.join(BASE_FAISS_SAVE_FOLDER, f"{set_id}")
            elif os.path.exists(os.path.join(SIM_FAISS_SAVE_FOLDER, f"{set_id}")):
                faiss_id_path = os.path.join(SIM_FAISS_SAVE_FOLDER, f"{set_id}")
            else:
                faiss_id_path = None
            know_ids = KnowledgeBase.get_all_file_set_ids(set_id)
            # 仿真知识库把多个文件索引放在同一个 set 目录中。存在子文件
            # 时按文件索引加载，避免先加载整个目录再重复合并。
            is_sim_set = faiss_id_path and os.path.normpath(faiss_id_path).startswith(
                os.path.normpath(SIM_FAISS_SAVE_FOLDER)
            )
            if faiss_id_path and not (is_sim_set and know_ids):
                Query_system.load_database(
                    faiss_id_path, source_name_for(set_id)
                )

            for know_id in know_ids:
                if is_sim_set:
                    # All simulated-file indexes live under the parent set
                    # directory; the index name is the child file ID.
                    Query_system.load_database(
                        faiss_id_path,
                        source_name_for(know_id),
                        index_name=know_id,
                    )
                    continue
                if os.path.exists(os.path.join(BASE_FAISS_SAVE_FOLDER, f"{know_id}")):
                    know_id_path = os.path.join(BASE_FAISS_SAVE_FOLDER, f"{know_id}")
                elif os.path.exists(os.path.join(SIM_FAISS_SAVE_FOLDER, f"{know_id}")):
                    know_id_path = os.path.join(SIM_FAISS_SAVE_FOLDER, f"{know_id}")
                else:
                    know_id_path = None
                if know_id_path:
                    if os.path.normpath(know_id_path).startswith(
                        os.path.normpath(SIM_FAISS_SAVE_FOLDER)
                    ):
                        Query_system.load_database(
                            know_id_path,
                            source_name_for(know_id),
                            index_name=know_id,
                        )
                    else:
                        Query_system.load_database(
                            know_id_path, source_name_for(know_id)
                        )
        

            
        Query_system.set_final_input(question, len(loadVectorDb) > 0, category=="1")

        # 执行流式生成并获取完整回答
        response = Response(Query_system.generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        })

        # 生成完成后保存聊天记录（需在响应返回前提交事务）
        session_name = question if question else "New Session"
        if chat_records == []:
            ChatSession.create_session(session_id, user_id,session_name)
        return response
    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

# 这是旧版本程序，本地生成ID
@main.route('/standard/toFaissWithFiles', methods=['POST'])
def upload_json_to_faiss():
    try:
        if 'file' not in request.files:
            return jsonify({"code": 400, "message": "No file part", "data": None}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"code": 400, "message": "No selected file", "data": None}), 400
        if file:
            folder_id = str(uuid.uuid4())
            # 获取当前日期并创建对应的文件夹名称
            if not os.path.exists(BASE_UPLOAD_FOLDER):
                os.makedirs(BASE_UPLOAD_FOLDER)

            ext = os.path.splitext(file.filename)[1]  # 提取文件后缀
            file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{folder_id}{ext}")
            file.save(file_path)

            # 生成文件夹编号，这里简单使用时间戳作为编号
            faiss_save_folder = os.path.join(BASE_FAISS_SAVE_FOLDER, folder_id)
            if not os.path.exists(faiss_save_folder):
                os.makedirs(faiss_save_folder)

            # 实例化 JsonFaissCreator 并处理文件
            creator = JsonFaissCreator(split_semicolon_count=10, overlap=1)
            creator.process_json_to_faiss(file_path, faiss_save_folder)

            # 将知识库信息存入数据库
            new_kb = KnowledgeBase(
                id=folder_id,  # 使用folder_id作为知识库ID
                name=os.path.splitext(file.filename)[0],  # 保存完整文件名（含扩展名）
                ext=ext  # 提取并保存文件后缀
            )
            db.session.add(new_kb)
            db.session.commit()

            return jsonify({
                "code": 200,
                "message": "JSON file processed and FAISS index saved successfully",
                "data": {"folderId": folder_id}
            }), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500



@main.route('/vector_qa', methods=['POST'])
def vector_qa():
    try:
        print("vector_qa accept")
        data = request.get_json()
        # 获取文件夹编号和问题
        folder_id = data.get('folder_id')
        question = data.get('question')

        if not folder_id or not question:
            return jsonify({"code": 400, "message": "文件夹编号和问题均为必填项", "data": None}), 400

        # 根据文件夹编号获取数据库路径
        db_path = PDFQuerySystem.get_db_path_from_folder_id(folder_id)

        query_system = PDFQuerySystem()
        query_system.load_database(db_path)
        answer = query_system.search_and_summarize(question)

        if answer:
            return jsonify({"code": 200, "message": "success", "data": {"answer": answer}}), 200
        else:
            return jsonify({"code": 404, "message": "未找到有效答案", "data": None}), 404

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/chat/message/delete/<session_id>', methods=['DELETE'])
def delete_chat_message(session_id):
    try:
        # 从路径参数获取sessionId
        if not session_id:
            return jsonify({"code": 400, "message": "sessionId is required", "data": None}), 400

        # 先删除关联的聊天消息
        ChatMessage.query.filter_by(session_id=session_id).delete()
        # 再删除会话记录
        ChatSession.query.filter_by(session_id=session_id).delete()
        # 提交事务
        db.session.commit()

        return jsonify({"code": 200, "message": "Records deleted successfully", "data": None}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/standard/toFaiss', methods=['POST'])
def standard_to_faiss():
    '''
     接收前端传入的 fileId 列表和 userId，根据 fileId 加载文件并生成 FAISS 向量
     '''
    from tasks import create_faiss
    try:
        files = request.files.getlist('file')
        # 验证form-data文件上传
        if not files or all(f.filename == '' for f in files):
            return jsonify({"code": 400, "message": "未上传有效文件", "data": None}), 400

        # 只处理第一个文件
        file = files[0]

        # 验证file_id参数
        file_id = request.form.get('id')
        if not file_id or file_id == "":
            return jsonify({"code": 400, "message": "fileId is required and must be a string", "data": None}), 400

        # 获取文件后缀
        file_name, file_ext = os.path.splitext(file.filename)
        ext = file_ext.lower()[1:]  # 去除点号并转为小写

        # 定义支持的文件后缀
        supported_exts = {'md','pdf', 'docx', 'json'}
        if ext not in supported_exts:
            return jsonify({"code": 400, "message": f"Unsupported file extension: {ext}", "data": None}), 400

        # 保存文件到BASE_UPLOAD_FOLDER文件夹
        file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id}.{ext}")
        file.save(file_path)

        # 创建保存向量的目录
        faiss_save_folder = os.path.join(BASE_FAISS_SAVE_FOLDER, file_id)
        if not os.path.exists(faiss_save_folder):
            os.makedirs(faiss_save_folder)

        # 异步执行创建FAISS向量的任务
        task = create_faiss.delay(file_path, ext, faiss_save_folder, file_id,file_name)

        return jsonify({
            "code": 200,
            "message": "解析中...",
            "data": {"fileId": file_id, "status": "pending", "task_id": str(task.id)}
        }), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

@main.route('/sim/toFaiss', methods=['POST'])
def sim_to_faiss():
    '''
     接收前端传入的 fileId 列表和 userId，根据 fileId 加载文件并生成 FAISS 向量
     '''
    from tasks import create_faiss
    try:
        setId = request.form.get('setId')
        # 验证setId参数
        if not setId or setId == "":
            return jsonify({"code": 400, "message": "setId is required and must be a string", "data": None}), 400

        jsonContent = request.form.get('jsonContent')

        files = request.files.getlist('file')
        files_valid = files and any(f.filename != '' for f in files)
        jsonContent_valid = jsonContent and jsonContent.strip() != ''

        # 验证file_id参数
        file_id = request.form.get('id')
        if not file_id or file_id == "":
            return jsonify({"code": 400, "message": "fileId is required and must be a string", "data": None}), 400


        # 创建包含setId的目录
        setId_folder = os.path.join(SIM_UPLOAD_FOLDER, setId)
        os.makedirs(setId_folder, exist_ok=True)

        # 验证jsonContent和files至少有一个有效
        if not jsonContent_valid and not files_valid:
            return jsonify({"code": 400, "message": "jsonContent和文件至少需要提供一个", "data": None}), 400, {'Content-Type': 'application/json; charset=utf-8'}

        file_path = ""
        if files_valid:
            # 只处理第一个文件
            file = files[0]
            # 获取文件后缀
            file_name, file_ext = os.path.splitext(file.filename)
            ext = file_ext.lower()[1:]  # 去除点号并转为小写

            # 定义支持的文件后缀
            supported_exts = {'md','pdf', 'docx', 'json'}
            if ext not in supported_exts:
                return jsonify({"code": 400, "message": f"Unsupported file extension: {ext}", "data": None}), 400

            # 保存文件到setId目录下
            file_path = os.path.join(setId_folder, f"{file_id}.{ext}")
            file.save(file_path)
        elif jsonContent_valid:
            file_name = file_id
            file_path = os.path.join(setId_folder, f"{file_id}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(jsonContent)
            ext = "json"

        # 创建包含setId的向量保存目录
        faiss_setId_folder = os.path.join(SIM_FAISS_SAVE_FOLDER, setId)
        os.makedirs(faiss_setId_folder, exist_ok=True)
        faiss_save_folder = faiss_setId_folder #os.path.join(faiss_setId_folder, file_id)

        os.makedirs(faiss_save_folder, exist_ok=True)

        # 异步执行创建FAISS向量的任务
        task = create_faiss.delay(file_path, ext, faiss_save_folder, file_id,file_name)

        return jsonify({
            "code": 200,
            "message": "解析中...",
            "data": {"fileId": file_id, "status": "pending", "task_id": str(task.id)}
        }), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500

@main.route('/open/generation/add', methods=['POST'])
def standard_to_rule():
    '''
     接收前端传入的 fileId 列表和 userId，根据 fileId 加载文件并生成 FAISS 向量
     '''
    from tasks import create_rule
    try:
        # 验证file_id参数
        file_id = request.form.get('id')
        if not file_id or file_id == "":
            return jsonify({"code": 400, "message": "fileId is required and must be a string", "data": None}), 400

        moduleId = request.form.get('moduleId')
        if not moduleId or moduleId == "":
            return jsonify({"code": 400, "message": "moduleId is required and must be a string", "data": None}), 400

        type = request.form.get('type')
        if not type or type == "":
            return jsonify({"code": 400, "message": "type is required and must be a string", "data": None}), 400

        file_path=""
        ext=""
        file_name=""
        if type=='1':
            files = request.files.getlist('file')
            # 验证form-data文件上传
            if not files or all(f.filename == '' for f in files):
                return jsonify({"code": 400, "message": "未上传有效文件", "data": None}), 400

            # 只处理第一个文件
            file = files[0]

            # 获取文件后缀
            file_name, file_ext = os.path.splitext(file.filename)
            ext = file_ext.lower()[1:]  # 去除点号并转为小写

            # 定义支持的文件后缀
            supported_exts = {'xls','xlsx', 'pdf', 'docx', 'doc'}
            if ext not in supported_exts:
                return jsonify({"code": 400, "message": f"Unsupported file extension: {ext}", "data": None}), 400

            # 保存文件到BASE_UPLOAD_FOLDER文件夹
            file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id}.{ext}")
            file.save(file_path)
        else:
            ext = request.form.get('ext')
            if not ext or ext == "":
                return jsonify({"code": 400, "message": "ext is required and must be a string", "data": None}), 400

            file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id}.{ext}")
            if not os.path.exists(file_path):
                return jsonify({"code": 400, "message": f"{file_id}.{ext} not found", "data": None}), 400

            file_name=file_id

        # 创建保存向量的目录
        faiss_save_folder = os.path.join(BASE_FAISS_SAVE_FOLDER, file_id)
        if not os.path.exists(faiss_save_folder):
            os.makedirs(faiss_save_folder)


        xml_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id}.xml")
        print(ext)
        # 异步执行创建FAISS向量的任务
        task = create_rule.delay(file_path,xml_path, ext,file_name,moduleId,file_id)

        print("2")



        return jsonify({
            "code": 200,
            "message": "解析中...",
            "data": {"fileId": file_id, "status": "pending", "task_id": str(task.id)}
        }), 200

    except Exception as e:
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/repository/create/fileset', methods=['POST'])
def create_fileset():
    try:
        # 获取查询参数
        # 从JSON请求体获取参数
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "Invalid JSON format", "data": None}), 400

        filesetName = data.get('filesetName')
        parentFolder = data.get('parentFolder')  # 可为空，表示顶级文件夹
        userId = data.get('userId')

        # 验证必填参数
        if not filesetName or not userId:
            return jsonify({"code": 400, "message": "filesetName and userId are required", "data": None}), 400

        # 参数验证
        if not filesetName:
            return jsonify({"code": 400, "message": "filesetName is required", "data": None}), 400
        if not userId:
            return jsonify({"code": 400, "message": "userId is required", "data": None}), 400

        # 生成唯一UID
        import uuid
        filesetId = str(uuid.uuid4())

        # 创建时间
        from datetime import datetime
        createTime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 存入数据库（假设存在FileSet模型）
        # 注意：需要根据实际模型结构调整字段名
        new_fileset = FileSet(
            id=filesetId,
            name=filesetName,
            parent_id=parentFolder,
            user_id=userId,
            created_at=createTime
        )
        db.session.add(new_fileset)
        db.session.commit()

        # 构造响应数据
        result = {
            "filesetId": filesetId,
            "filesetName": filesetName,
            "parentFolder": parentFolder,
            "userId": userId,
            "createTime": createTime
        }

        return jsonify({"code": 200, "message": "File set created successfully", "data": result}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/repository/create/faiss', methods=['POST'])
def create_faiss_repository():
    try:
        # 获取form-data参数
        userId = request.form.get('userId')
        filesetId = request.form.get('filesetId')
        file = request.files.get('file')

        # 参数验证
        if not userId:
            return jsonify({"code": 400, "message": "userId is required", "data": None}), 400
        if not filesetId:
            return jsonify({"code": 400, "message": "filesetId is required", "data": None}), 400
        if not file or file.filename == '':
            return jsonify({"code": 400, "message": "file is required", "data": None}), 400

        # 生成唯一文件ID
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1]

        # 保存文件到本地
        file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{file_id}{ext}")
        file.save(file_path)

        # 存入KnowledgeBase表
        KnowledgeBase.create_file_record(
            file_id=file_id,
            filename=file.filename,
            ext=ext,
            file_set_id=filesetId,
            user_id=userId,
            file_size=file.content_length,
            file_type=file.content_type
        )

        return jsonify({
            "code": 200,
            "message": "FAISS repository created successfully",
            "data": {
                "fileId": file_id,
                "filesetId": filesetId,
                "userId": userId
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/repository/del/faiss', methods=['DELETE'])
def delete_faiss_repository():
    import shutil
    try:
        # 获取query参数
        fileId = request.args.get('fileId')
        if not fileId:
            return jsonify({"code": 400, "message": "fileId is required", "data": None}), 400

        # 查询文件记录
        kb = KnowledgeBase.query.filter_by(id=fileId).first()
        if not kb:
            return jsonify({"code": 404, "message": "File not found", "data": None}), 404

        # 删除FAISS索引文件夹
        faiss_path = os.path.join(BASE_FAISS_SAVE_FOLDER, fileId)
        if os.path.exists(faiss_path):
            shutil.rmtree(faiss_path)
        
        file_path = os.path.join(BASE_UPLOAD_FOLDER, f"{fileId}{kb.ext}")
        if os.path.exists(file_path):
            if os.path.isfile(file_path):
                os.remove(file_path)
            else:
                shutil.rmtree(file_path)

        # 从数据库删除记录
        db.session.delete(kb)
        db.session.commit()

        return jsonify({
            "code": 200,
            "message": "FAISS repository deleted successfully",
            "data": {"fileId": fileId}
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@main.route('/repository/delete/fileset', methods=['DELETE'])
def delete_fileset():
    try:
        # 获取查询参数
        userId = request.args.get('userId')
        filesetId = request.args.get('filesetId')

        # 参数验证
        if not userId:
            return jsonify({"code": 400, "message": "userId is required", "data": None}), 400
        if not filesetId:
            return jsonify({"code": 400, "message": "filesetId is required", "data": None}), 400

        # 查询文件集
        fileset = FileSet.query.filter_by(id=filesetId, user_id=userId).first()
        if not fileset:
            return jsonify({"code": 404, "message": "File set not found or no permission", "data": None}), 404

        # 删除文件集
        db.session.delete(fileset)
        db.session.commit()

        return jsonify({"code": 200, "message": "File set deleted successfully", "data": {"filesetId": filesetId}}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


