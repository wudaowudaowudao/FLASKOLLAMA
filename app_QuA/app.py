# app.py
from flask import Flask, request, jsonify
from core import PDFQuerySystem
import os

app = Flask(__name__)

# 全局维护所有用户的系统实例
systems = {}

# 向量库路径（如不需要可留空）
VECTOR_DB_PATH = "data/crrc400"


def get_system(user_id):
    if user_id not in systems:
        systems[user_id] = PDFQuerySystem(user_id=user_id)
    return systems[user_id]


@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    query = data.get("query")
    user_id = data.get("user_id")
    enable_thinking = data.get("enable_thinking", True)
    use_vector_db = data.get("use_vector_db", False)
    load_db = data.get("load_db", False)

    if not query or not user_id:
        return jsonify({"error": "缺少 query 或 user_id 参数"}), 400

    system = get_system(user_id)

    if load_db:
        system.load_database(VECTOR_DB_PATH)

    response = system.ask(
        query=query,
        session_id="default",
        enable_thinking=enable_thinking,
        use_vector_db=use_vector_db
    )

    if response:
        return jsonify({"response": response, "theme": system.theme})
    else:
        return jsonify({"error": "模型回答失败"}), 500


@app.route("/list_themes", methods=["GET"])
def list_themes():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "缺少 user_id 参数"}), 400

    system = get_system(user_id)
    themes = system.list_themes()
    return jsonify({"themes": themes})


@app.route("/load_history", methods=["POST"])
def load_history():
    data = request.json
    user_id = data.get("user_id")
    date = data.get("date")
    theme = data.get("theme")

    if not all([user_id, date, theme]):
        return jsonify({"error": "缺少 user_id / date / theme 参数"}), 400

    system = get_system(user_id)
    system.load_history(date, theme, session_id="default")

    return jsonify({"message": f"历史主题 {theme} 已加载"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8008, debug=True)
