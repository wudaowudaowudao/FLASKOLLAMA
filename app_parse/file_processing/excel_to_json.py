import pandas as pd
import json
import os
from typing import Optional, Dict, List, Union

class ExcelToJsonConverter:
    def __init__(self, excel_file: str):
        """初始化转换器

        Args:
            excel_file (str): Excel文件的路径
        """
        self.excel_file = excel_file
        self.data: Optional[List[Dict]] = None

    def read_excel(self, sheet_name: Optional[Union[str, int]] = 0) -> 'ExcelToJsonConverter':
        """读取Excel文件

        Args:
            sheet_name: 工作表名称或索引，默认为第一个工作表

        Returns:
            self: 支持链式调用
        """
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        self.data = df.to_dict(orient='records')
        return self

    def save_json(self, output_file: Optional[str] = None, indent: int = 4) -> str:
        """将数据保存为JSON文件

        Args:
            output_file: 输出JSON文件的路径，如果为None则使用Excel文件同名的JSON文件
            indent: JSON文件的缩进空格数

        Returns:
            str: 保存的JSON文件路径
        """
        if self.data is None:
            raise ValueError('请先调用read_excel()方法读取Excel文件')

        if output_file is None:
            output_file = os.path.splitext(self.excel_file)[0] + '.json'

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=indent)

        return output_file

    def get_data(self) -> Optional[List[Dict]]:
        """获取转换后的数据

        Returns:
            Optional[List[Dict]]: 转换后的数据，如果未读取Excel则返回None
        """
        return self.data

if __name__ == '__main__':
    # 测试代码
    excel_file = 'e:\\PycharmProjects\\TestEnv\\XMLGenerator\\data\\需求评估_0310.xlsx'
    
    # 基本使用示例
    converter = ExcelToJsonConverter(excel_file)
    json_file = converter.read_excel().save_json()
    print(f'已将Excel文件转换为JSON并保存至: {json_file}')

    # # 获取数据示例
    # data = converter.get_data()
    # if data:
    #     print(f'\n转换后的数据预览（前2条）:')
    #     for item in data[:2]:
    #         print(item)

    # # 自定义输出文件示例
    # custom_output = 'e:\\PycharmProjects\\TestEnv\\XMLGenerator\\output\\custom_output.json'
    # json_file = converter.save_json(custom_output)
    # print(f'\n已将数据保存至自定义路径: {json_file}')