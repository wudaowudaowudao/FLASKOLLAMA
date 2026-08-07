from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
app = Flask(__name__)   

from app_parse import routes


def create_app():
     
    app.config.from_object(Config)

    # 配置JSON响应，确保中文不被转义
    #app.config['JSON_AS_ASCII'] = False
    #app.config['JSON_SORT_KEYS'] = False

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 3600,  # 每1小时回收空闲连接（小于MySQL的wait_timeout）
        'pool_pre_ping': True,  # 执行查询前检查连接有效性
        'pool_size': 5,        # 基础连接数
        'max_overflow': 10     # 最大额外连接数
    }
    
    db.init_app(app)
    #with app.app_context():
     #   db.create_all()

    from .routes import main
    app.register_blueprint(main)

    return app

