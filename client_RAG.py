import requests

url = 'http://127.0.0.1:5001/vector_qa'
data = {
    "db_path": "E:\\PycharmProjects\\FlaskOllama\\data\\vector_json_db\\2025-04-16",
    "question": "Unit Conversion模块有什么功能？"
}

response = requests.post(url, json=data)
result = response.json()
print(result)
