import os
import re
import json
import time
from langchain_community.chat_models import ChatOllama
from langchain.schema import HumanMessage

class MarkdownTranslator:
    def __init__(self, api_key=None, model_name="gemma3:27b", temperature=0.2):
        """
        初始化 MarkdownTranslator
        """
        if api_key:
            print("使用 Ollama 本地模型，API Key 将被忽略。")
        self.llm = ChatOllama(model=model_name, temperature=temperature)

    def remove_think_content(self, text):
        """
        删除<think>标签内容
        """
        pattern = r'(<think>.*?</think>)'
        return re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    def translate(self, text, context="", skip_non_text=False, retry_times=3):
        """
        通用翻译接口，支持自动重试
        """
        if not text:
            return ""

        prompt = ""
        if skip_non_text:
            prompt = (
                f"{'参考上下文：' + context if context else ''}\n"
                "请将下列文本翻译成中文，不要添加任何解释，如果是链接/代码片段/无需翻译内容，请保持原样：\n\n"
                f"{text}"
            )
        else:
            prompt = (
                f"{'参考上下文：' + context if context else ''}\n"
                "请将以下 Markdown 内容翻译成中文，不要添加任何解释：\n\n"
                f"{text}"
            )

        attempt = 0
        while attempt < retry_times:
            try:
                response = self.llm([HumanMessage(content=prompt)])
                print("============"+response.content)
                return response.content.strip()
            except Exception as e:
                print(f"翻译出错，正在重试({attempt+1}/{retry_times})：{e}")
                attempt += 1
                time.sleep(2)

        print(f"翻译失败：{text[:50]}...")
        return text  # 翻译失败就返回原文

    def split_markdown(self, md_content):
        """
        更智能地分段：按标题、段落、列表项目等
        """
        pattern = r'(#{1,6}\s.*?$|^[-*+]\s.*?$|\n\n|\n(?=\s*-|\s*\*))'
        sections = re.split(pattern, md_content, flags=re.MULTILINE)
        return [s.strip() for s in sections if s.strip()]

    def translate_markdown_file(self, input_file_path, output_file_path):
        """
        翻译 Markdown 文件
        """
        try:
            with open(input_file_path, 'r', encoding='utf-8') as file:
                md_content = file.read()

            sections = self.split_markdown(md_content)
            print(f"共分割出 {len(sections)} 个段落。")

            translated_sections = []
            prev_context = ""

            for idx, section in enumerate(sections):
                translated = self.translate(section, context=prev_context)
                translated_sections.append(translated)
                prev_context = translated

                if idx % 5 == 0 or idx == len(sections) - 1:
                    progress = (idx + 1) / len(sections) * 100
                    print(f"翻译进度：{progress:.2f}%")

            translated_content = '\n\n'.join(translated_sections)

            with open(output_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(translated_content)

            print(f"✅ 翻译完成，保存到 {output_file_path}")

        except Exception as e:
            print(f"处理 Markdown 文件时出错: {e}")


    def translate_json(self, data):
        """
        翻译 JSON 文件，text字段翻译
        """
        try:
            prev_context =""
            for idx, item in enumerate(data):
                if item.get('type') == 'text':
                    original_text = item.get('text', '')
                    translated_text = self.translate(original_text,  context=prev_context,skip_non_text=True)
                    item['translate_text'] = translated_text
                    prev_context = translated_text
                    #print(item['translate_text'])


                    if idx % 5 == 0 or idx == len(data) - 1:
                        progress = (idx + 1) / len(data) * 100
                        print(f"JSON翻译进度：{progress:.2f}%")

            print(f"✅ JSON翻译完成")
            return data

        except Exception as e:
            print(f"处理 JSON 文件时出错: {e}")

    def translate_json_file(self, input_file_path, output_file_path):
        """
        翻译 JSON 文件，text字段翻译
        """
        try:
            with open(input_file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                data = json.loads(content)


            for idx, item in enumerate(data):
                if item.get('type') == 'text':
                    original_text = item.get('text', '')
                    translated_text = self.translate(original_text, skip_non_text=True)
                    item['translate_text'] = translated_text

                    if idx % 5 == 0 or idx == len(data) - 1:
                        progress = (idx + 1) / len(data) * 100
                        print(f"JSON翻译进度：{progress:.2f}%")

            with open(output_file_path, 'w', encoding='utf-8') as new_file:
                json.dump(data, new_file, ensure_ascii=False, indent=4)

            print(f"✅ JSON翻译完成，保存到 {output_file_path}")

        except Exception as e:
            print(f"处理 JSON 文件时出错: {e}")

if __name__ == "__main__":
    translator = MarkdownTranslator()

    start_time = time.time()

    input_file = "/home/crrc/Projects/flaskFileFragment/data/trans2.md"
    # output_file = "/home/crrc/Projects/PdfParser/MinerU/MinerU-master/output_0506_o/data/foreign/序14 EN 50128-2011 英文/data/foreign/序14 EN 50128-2011 英文_zh.md"

    # 获取文件的目录和文件名
    file_dir, file_name = os.path.split(input_file)

    # 分离文件名和扩展名
    file_name_without_ext, file_ext = os.path.splitext(file_name)

    # 添加后缀并重新组合文件名
    output_file_name = f"{file_name_without_ext}_zh{file_ext}"

    # 组合输出文件的完整路径
    output_file = os.path.join(file_dir, output_file_name)
    print("output_file:", output_file)

    translator.translate_markdown_file(input_file, output_file)

    end_time = time.time()
    elapsed = end_time - start_time
    print(f"⏰ 总耗时：{elapsed // 60:.0f}分钟 {elapsed % 60:.0f}秒")
