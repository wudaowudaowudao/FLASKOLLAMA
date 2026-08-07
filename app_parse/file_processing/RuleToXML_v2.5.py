import json
import os
import logging
import re
from typing import Dict, Any

from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOllama

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


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


def load_json(json_path: str) -> Dict[str, Any]:
    """加载JSON文件"""
    try:
        return json.loads(load_file(json_path))
    except json.JSONDecodeError as e:
        logging.error(f"解析JSON文件时发生错误: {e}")
        raise


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


def create_llm() -> ChatOllama:
    """创建Ollama LLM实例，使用Qwen模型"""
    return ChatOllama(model="qwen3:32b", temperature=0.1)


def create_prompt() -> PromptTemplate:
    """创建提示模板"""
    template = """
你将扮演一个标准生成器，依据以下的标准格式（以XML格式给出）：

规则: {rule_base}

请根据以下JSON数据，生成对应的标准规则XML内容：

JSON数据: {json_data}

注意：
- 只返回和上面一样的标准的XML格式规则数据。
- 不要输出 <think>、<reflection>、Markdown 代码块、```xml 或其他额外内容。
- 不要包含任何解释、注释或冗余内容。

直接输出纯净的 XML。
"""
    return PromptTemplate(input_variables=["rule_base", "json_data"], template=template)


def run_standard_check(json_data: Dict[str, Any], rule_base: str, llm: ChatOllama, prompt: PromptTemplate) -> str:
    """运行标准检查"""
    chain = LLMChain(llm=llm, prompt=prompt)
    result = chain.run({"rule_base": rule_base, "json_data": json_data})
    logging.debug(f"模型原始输出:\n{result}")
    return result.strip()


def parse_result(result: str) -> str:
    """解析结果，清除不需要的标签及内容，返回纯净的XML部分"""
    # 去除 markdown 格式代码块标记 ```xml 或 ```
    result = re.sub(r'```(?:xml)?\s*', '', result)
    result = result.strip('`')

    # 清除 <think>...</think> 标签和其中所有内容（包括换行）
    result = re.sub(r'<think[\s\S]*?</think>', '', result, flags=re.IGNORECASE)

    # 去除空行
    result = re.sub(r'\n\s*\n', '\n', result)

    # 去除开头和结尾的多余空白
    return result.strip()



def main(JSON_INPUT_PATH, RULE_BASE_PATH, RULE_RESULT_OUTPUT_PATH):
    try:
        # 加载数据和规则
        json_data = load_json(JSON_INPUT_PATH)
        rule_base = load_file(RULE_BASE_PATH)

        # 创建LLM和提示模板
        llm = create_llm()
        prompt = create_prompt()

        # 运行标准检查
        check_result = run_standard_check(json_data, rule_base, llm, prompt)
        logging.info("标准检查完成")

        # 清洗并保存XML结果
        parsed_result = parse_result(check_result)
        save_xml(parsed_result, RULE_RESULT_OUTPUT_PATH)

    except Exception as e:
        logging.error(f"处理过程中发生错误: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    JSON_INPUT_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/data/xml_generator/file/GB-T14691-1993技术制图-字体_content_list.json"
    RULE_BASE_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/data/xml_generator/rule/rule_base.xml"
    RULE_RESULT_OUTPUT_PATH = "/home/ubuntu/PycharmProjects/FlaskOllama/data/xml_generator/output/GB-T14691-1993.xml"
    main(JSON_INPUT_PATH, RULE_BASE_PATH, RULE_RESULT_OUTPUT_PATH)
