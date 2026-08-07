import requests
import time

BASE_URL = "http://localhost:8008"
USER_ID = "zhangsan"

def ask_question(query, use_vector_db=False, enable_thinking=True, load_db=True):
    payload = {
        "query": query,
        "user_id": USER_ID,
        "enable_thinking": enable_thinking,
        "use_vector_db": use_vector_db,
        "load_db": load_db
    }
    response = requests.post(f"{BASE_URL}/ask", json=payload)
    print("\n[ASK] Status:", response.status_code)
    print("Response:", response.json())
    return response.json()


def list_themes():
    response = requests.get(f"{BASE_URL}/list_themes", params={"user_id": USER_ID})
    print("\n[LIST THEMES] Status:", response.status_code)
    print("Themes:", response.json())
    return response.json()


def load_history(date, theme):
    payload = {
        "user_id": USER_ID,
        "date": date,
        "theme": theme
    }
    response = requests.post(f"{BASE_URL}/load_history", json=payload)
    print("\n[LOAD HISTORY] Status:", response.status_code)
    print("Message:", response.json())
    return response.json()


if __name__ == "__main__":
    print("🔥 测试开始...\n")

    # 第一次问，自动生成主题
    first = ask_question("齿轮箱在高速列车中起什么作用？", use_vector_db=True)
    theme = first.get("theme", "")
    time.sleep(2)

    # 查询主题
    themes_info = list_themes()
    date = themes_info["themes"][-1]["date"]
    theme = themes_info["themes"][-1]["theme"]
    time.sleep(2)

    # 加载历史
    load_history(date, theme)
    time.sleep(1)

    # 再次问，继续对话
    ask_question("它的维护周期是多久？", use_vector_db=False, enable_thinking=False, load_db=False)

    print("\n✅ 所有接口测试完成。")
