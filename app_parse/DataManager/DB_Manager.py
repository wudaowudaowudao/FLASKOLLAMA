from datetime import datetime

import sys
import os 

# 将项目根目录添加到sys.path（关键修复）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from app_parse import db,app
from flask_sqlalchemy import SQLAlchemy

class ChatSession(db.Model):
    """聊天会话基本信息表（存储会话元数据）"""
    session_id = db.Column(db.String(50), primary_key=True)  # 会话唯一标识（主键）
    user_id = db.Column(db.String(50), nullable=False)  # 用户ID（外键，可关联用户表）
    session_name = db.Column(db.String(100), nullable=False)  # 会话名称（如"技术咨询2024"）
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # 会话创建时间

    @staticmethod
    def create_session(session_id: str, user_id: str, session_name: str = "New Session"):
        """创建新会话记录"""
        with app.app_context():
            # 检查session_id是否已存在
            existing_session = ChatSession.query.filter_by(session_id=session_id).first()
            if existing_session:
                return  # 如果存在则不创建新记录
            
            new_session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                session_name=session_name
            )
            db.session.add(new_session)
            db.session.commit()
        return

    def __repr__(self):
        return f'<ChatSession {self.session_id}>'

class ChatMessage(db.Model):
    """聊天记录详细信息表（存储单条消息内容）"""
    id = db.Column(db.Integer, primary_key=True)  # 自增主键
    session_id = db.Column(
        db.String(50), 
        db.ForeignKey('chat_session.session_id'),  # 外键关联会话表
        nullable=False
    )
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # 消息时间戳
    role = db.Column(db.String(10), nullable=False)  # 角色（'user'或'ai'）
    question = db.Column(db.Text)  # 用户提问内容（用户角色时必填）
    answer = db.Column(db.Text)  # AI回答内容（AI角色时必填）

    @staticmethod
    def create_Chat(session_id: str, question: str ,answer: str, role: str = "user"):
        """创建新会话记录"""
        from app_parse import app
        with app.app_context():
            new_session = ChatMessage(
                session_id=session_id,
                role=role,
                question=question,
                answer=answer 
            )
            db.session.add(new_session)
            db.session.commit()
        return 

    @staticmethod
    def get_chat_history_by_session(session_id: str) -> list:
        """
        根据session_id查询聊天记录（按时间升序排列）
        :param session_id: 会话唯一标识
        :return: 聊天记录列表（ChatMessage对象）
        """

        return ChatMessage.query \
            .filter_by(session_id=session_id) \
            .order_by(ChatMessage.timestamp.asc()) \
            .all()

    


    def __repr__(self):
        return f'<ChatMessage {self.session_id} {self.role}>'


class KnowledgeBase(db.Model):
    """知识库信息表（存储上传的知识库元数据）"""
    id = db.Column(db.String(36), primary_key=True)  # UUID作为主键
    name = db.Column(db.String(100), nullable=False)  # 知识库名称
    ext = db.Column(db.String(20), nullable=False)  # 文件后缀
    file_set_id = db.Column(db.String(36), nullable=False)  # 文件集ID
    user_id = db.Column(db.String(50), nullable=False)  # 用户ID
    file_size = db.Column(db.Integer)  # 文件大小（字节）
    file_type = db.Column(db.String(50))  # 文件类型
    status = db.Column(db.String(50), default="pending")  # 处理状态：pending/processing/completed/failed
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)  # 上传时间

    @staticmethod
    def get_all_file_set_ids(file_set_id):
        """根据file_set_id查询对应的id列表"""
        with app.app_context():
            # 查询指定file_set_id的所有记录的id
            records = KnowledgeBase.query.filter_by(file_set_id=file_set_id).all()
            # 提取id字段并返回列表
            return [record.id for record in records]

    @staticmethod
    def get_db_paths_by_ids(id_list):
        """根据ID列表查询对应的db_path列表"""
        with app.app_context():
            # 查询指定ID的知识库记录
            knowledge_bases = KnowledgeBase.query.filter(KnowledgeBase.id.in_(id_list)).all()
            # 提取db_path字段并返回列表
            return [kb.name for kb in knowledge_bases]

    @staticmethod
    def create_file_record(file_id, filename, ext, file_set_id, user_id, file_size, file_type,status="unparsed"):
        """创建文件记录并保存到数据库"""
        try:
            with app.app_context():
                new_kb = KnowledgeBase(
                    id=file_id,
                    name=filename,
                    ext=ext,
                    file_set_id=file_set_id,
                    user_id=user_id,
                    file_size=file_size,
                    file_type=file_type,
                    status=status
                )
                db.session.add(new_kb)
                db.session.commit()
                return new_kb
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"创建文件记录失败: {str(e)}")
            return None

    @staticmethod      
    def update_knowledge_base_status(file_id,status):
        # 更新KnowledgeBase状态为completed
        kb_record = KnowledgeBase.query.filter_by(file_id=file_id).first()
        if kb_record:
            kb_record.status = status
            db.session.commit()
            return True
        else:
            logger.error(f"警告：未找到file_id为{file_id}的KnowledgeBase记录，无法更新状态")
            return False

    def __repr__(self):
        return f'<KnowledgeBase {self.id} {self.name}>'


class FileSet(db.Model):
    """知识库数据集表（存储数据集元数据）"""
    id = db.Column(db.String(36), primary_key=True)  # 数据集唯一标识（UUID）
    name = db.Column(db.String(100), nullable=False)  # 数据集名称
    parent_id = db.Column(db.String(36), nullable=True)  # 父文件夹ID（可为空）
    user_id = db.Column(db.String(50), nullable=False)  # 用户ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 创建时间

    def __repr__(self):
        return f'<FileSet {self.id} {self.name}>'
    



