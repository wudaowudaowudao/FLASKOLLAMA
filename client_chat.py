import requests

# 服务端接口地址
url = 'http://127.0.0.1:5001/ollama-qa'

# 要发送的问题
question = "请给我一个简单的 Python 示例。"

# 构造请求数据
data = {
    "question": question
}

try:
    # 发送 POST 请求
    response = requests.post(url, json=data)
    # 检查响应状态码
    if response.status_code == 200:
        result = response.json()
        print(f"问题: {question}")
        print(f"答案: {result['answer']}")
    else:
        print(f"请求失败，状态码: {response.status_code}，错误信息: {response.text}")
except requests.RequestException as e:
    print(f"请求发生错误: {e}")