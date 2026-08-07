from flask import Flask
from config import Config
from app_parse import create_app,db
from app_parse.DataManager.DB_Manager import ChatSession, ChatMessage

if __name__ == '__main__':
    main_app = create_app()
    with main_app.app_context():
        db.create_all()  # 执行表结构创建
    main_app.run(host="0.0.0.0", debug=True, port=8550)
