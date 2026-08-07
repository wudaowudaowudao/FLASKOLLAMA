import requests

# 服务器的地址和端口，根据实际情况修改
url = 'http://127.0.0.1:5001/upload/json_to_faiss'
# 要上传的 JSON 文件路径，根据实际情况修改
file_path = 'E:\PycharmProjects\FlaskOllama\data\SimuJson.json'

try:
    # 打开文件
    with open(file_path, 'rb') as file:
        # 准备文件数据
        files = {'file': file}
        # 发送 POST 请求
        response = requests.post(url, files=files)

    # 检查响应状态码
    if response.status_code == 200:
        result = response.json()
        print("文件处理成功！")
        print("文件夹编号:", result.get('folder_id'))
    else:
        result = response.json()
        print("文件处理失败，错误信息:", result.get('error'))

except Exception as e:
    print("请求发生错误:", e)
