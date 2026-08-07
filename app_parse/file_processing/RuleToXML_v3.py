import json
import os
import logging
import re
from typing import Dict, Any

from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOllama
from app_parse.file_processing.parsefile import ParseFile
from config import Config
from app_parse.file_processing.docx_to_json import DocxToJsonConverter
from app_parse.file_processing.excel_to_json import ExcelToJsonConverter


# 配置日志
class RuleToXMLConverter:
    def __init__(self, model_name: str = "qwen3:32b", temperature: float = 0.1):
        """初始化规则转XML转换器"""
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        self.model_name = model_name
        self.temperature = temperature
        self.llm = self.create_llm()
        self.prompt = self.create_prompt()

    @staticmethod
    def load_file(file_path: str, encoding: str = 'utf-8') -> str:
        """从文件中加载内容"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except FileNotFoundError:
            logging.error(f"文件未找到: {file_path}")
            raise
        except IOError as e:
            logging.error(f"读取文件时发生错误: {e}")
            raise

    @staticmethod
    def load_json(json_path: str) -> Dict[str, Any]:
        """加载JSON文件"""
        try:
            return json.loads(RuleToXMLConverter.load_file(json_path))
        except json.JSONDecodeError as e:
            logging.error(f"解析JSON文件时发生错误: {e}")
            raise

    @staticmethod
    def save_xml(data: str, xml_path: str) -> None:
        """保存结果到XML文件"""
        try:
            os.makedirs(os.path.dirname(xml_path), exist_ok=True)
            with open(xml_path, 'w', encoding='utf-8') as f:
                f.write(data)
            logging.info(f"结果已保存到: {xml_path}")
        except IOError as e:
            logging.error(f"保存XML文件时发生错误: {e}")
            raise

    def create_llm(self) -> ChatOllama:
        """创建Ollama LLM实例"""
        return ChatOllama(model=self.model_name, temperature=self.temperature, num_ctx=48*1000, num_predict=64*1000)

    def create_prompt(self) -> PromptTemplate:
        """创建提示模板"""
        template = """
    你是一个结构化提取专家。现在我给你两个输入：

    1. 一个 JSON，字段 "text" 包含 OCR 提取的机械制图标准文档内容（可能非常长）。json文件在下文中我会提供给你。
    2. 一个样例 XML，展示了理想输出结构（但你不必限制输出长度，完整结构化内容最重要）。下文提供给你。

    你的任务是：
    - 理解文档中各项标准（如零件图线型、字体、注释格式等）。
    - 将这些标准转换成符合样例模板的完整 XML 结构。
    - 输出完整 XML，不要截断，也不要只输出样例长度。
    - 如果文档中没有某项标准，可省略对应 XML 节点。

    请注意：
    - 按样例xml中的方式字段列出属性；
    - 对标准文档的理解要准确，输出结构要清晰完整。

    以下为json文件：
    {json_data}
    这个是样例xml：{rule_base}

    请执行任务。
"""
        return PromptTemplate(input_variables=["rule_base", "json_data"], template=template)

    def run_standard_check(self, json_data: Dict[str, Any], rule_base: str) -> str:
        """运行标准检查"""
        chain = LLMChain(llm=self.llm, prompt=self.prompt)
        result = chain.run({"rule_base": rule_base, "json_data": json_data})
        logging.debug(f"模型原始输出:\n{result}")
        return result.strip()

    import re

    def parse_result(self, result: str) -> str:
        """解析结果，清除不需要的标签及内容，返回纯净的XML部分"""
        # 去除 markdown 格式代码块标记 ```xml 或 ```
        result = re.sub(r'```(?:xml)?\s*', '', result)
        result = result.strip('`')

        # 清除 <think>...</think> 标签和其中内容（跨多行）
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.IGNORECASE | re.DOTALL)

        # 去除空行
        result = re.sub(r'\n\s*\n', '\n', result)

        # 去除开头和结尾的多余空白
        return result.strip()

    def get_json_file(self, file_path: str,filename:str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self.get_pdf_json(file_path,filename)
        if ext == ".doc" or ext == ".docx":
            return self.get_docx_json(file_path)
        if ext == ".xls" or ext == ".xlsx":
            return self.get_Excel_json(file_path)

    def get_docx_json(self, file_path: str) :
        print(f'正在解析文件: {file_path}')
        converter = DocxToJsonConverter(file_path)
        json_file = converter.read_docx().save_json()

        return json_file

    def get_Excel_json(self, file_path: str) :
        print(f'正在解析文件: {file_path}')
        converter = ExcelToJsonConverter(file_path)
        json_file = converter.read_excel().save_json()

        return json_file


    def get_pdf_json(self,file_path,filename):
        print(f'正在解析文件: {file_path}')

        file_name = os.path.basename(file_path)
        file_name_without_ext, file_ext = os.path.splitext(file_name)

        parse_file = ParseFile()

        # 创建解析实例并处理
        parse_file.set_parse_param("ch", "0", "",
                                   file_name_without_ext)
        print(f'accept:: {file_path}')
        res = parse_file.Parse_work(file_path, file_name_without_ext, filename,False)

        if res != "":
            return f"{'status': 'error', 'message': f'文件解析错误:{res}'}"
        else:
            return f"{Config.PARSE_FILE_SETTINGS['PARSE_DATA_PATH']}/{file_name_without_ext}/{file_name_without_ext}_content_list.json"

    def process(self, json_input_path: str, rule_base_path: str, rule_result_output_path: str,ext:str,filename:str) -> None:
        """处理主流程：加载数据、运行检查、保存结果"""
        try:

            json_input_path1 = self.get_json_file(json_input_path,filename)

            # 加载数据和规则
            json_data = self.load_json(json_input_path1)
            rule_base = self.load_file(rule_base_path)

            # 运行标准检查
            check_result = self.run_standard_check(json_data, rule_base)
            logging.info("标准检查完成")

            # 清洗并保存XML结果
            parsed_result = self.parse_result(check_result)
            self.save_xml(parsed_result, rule_result_output_path)

        except Exception as e:
            logging.error(f"处理过程中发生错误: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        logging.error("Usage: python RuleToXML_v3.py <JSON_INPUT_PATH> <RULE_BASE_PATH> <RULE_RESULT_OUTPUT_PATH>")
        sys.exit(1)
    converter = RuleToXMLConverter()
    converter.process(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    JSON_INPUT_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/xmlGenerator/file1.json"
    RULE_BASE_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/xmlGenerator/rule_base.xml"
    RULE_RESULT_OUTPUT_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/xmlGenerator/file1.xml"
    #main(JSON_INPUT_PATH, RULE_BASE_PATH, RULE_RESULT_OUTPUT_PATH,"pdf")
