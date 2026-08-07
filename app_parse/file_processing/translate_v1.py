#使用OLLMA模型翻译Markdown文件，服务器上测试通过
import os
import re
# 导入 ChatOllama 类
from langchain_community.chat_models import ChatOllama
from langchain.schema import HumanMessage


class MarkdownTranslator:
    def __init__(self, api_key=None):
        """
        初始化 MarkdownTranslator 类。

        :param api_key: 这里不需要智谱 AI 的 API 密钥，保留参数是为了兼容原代码结构
        """
        if api_key:
            print("使用 Ollama 模型，API 密钥参数将被忽略。")

    def translate_text(self, text, context=""):
        """
        使用 Ollama 的 qwq:latest 模型将输入的文本翻译成中文。

        :param text: 需要翻译的文本
        :param context: 翻译时参考的上下文信息，默认为空
        :return: 翻译后的文本
        """
        # 使用 ChatOllama 调用 qwq:latest 模型
        llm = ChatOllama(
            model="qwq:latest",
            temperature=0.5
        )
        if context:
            prompt = (f"参考上下文：{context}\n请阅读以下 Markdown 格式的文本，将其内容翻译成中文，请不要添加任何解释或说明：\n\n{text}")
        else:
            prompt = (f"请阅读以下 Markdown 格式的文本，将其内容翻译成中文，请不要添加任何解释或说明：\n\n{text}")
        response = llm([HumanMessage(content=prompt)])
        translated_data = response.content.strip()
        return translated_data

    def split_markdown(self, md_content):
        """
        按 Markdown 标题对内容进行分段。

        :param md_content: Markdown 文件的内容
        :return: 分段后的列表
        """
        pattern = r'(#{1,6}.*?)(?=#{1,6}|$)'
        sections = re.findall(pattern, md_content, re.DOTALL)
        return [section.strip() for section in sections]

    def translate_markdown_file(self, input_file_path, output_file_path):
        """
        翻译 Markdown 文件并保存翻译结果。

        :param input_file_path: 输入的 Markdown 文件路径
        :param output_file_path: 输出的翻译后文件路径
        """
        try:
            # 读取 Markdown 文件内容
            with open(input_file_path, 'r', encoding='utf-8') as file:
                md_content = file.read()

            # 分段
            sections = self.split_markdown(md_content)

            translated_sections = []
            prev_translated = ""
            for section in sections:
                # 翻译当前分段，带上前一个分段的翻译结果作为上下文
                translated = self.translate_text(section, prev_translated)
                translated_sections.append(translated)
                prev_translated = translated

            # 合并翻译后的分段
            translated_content = '\n\n'.join(translated_sections)

            # 保存翻译后的内容
            with open(output_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(translated_content)

            print(f"翻译完成，结果已保存到 {output_file_path}")

        except Exception as e:
            print(f"处理过程中出现错误: {e}")


if __name__ == "__main__":
    # 实例化时可以传入 None，因为不需要 API 密钥
    translator = MarkdownTranslator(api_key=None)
    input_file = "e:\\PycharmProjects\\flaskFileFragment\\data\\foreign\\trans2.md"
    output_file = "e:\\PycharmProjects\\flaskFileFragment\\data\\foreign\\trans4_zh.md"
    translator.translate_markdown_file(input_file, output_file)