# 0807 mengyang update
import json
import os
import re

class TitleAnalyzer:
    def __init__(self, dir_path):
        """初始化标题分析器，指定处理的目录路径"""
        self.dir_path = dir_path

    def normalize(self, parts):
        """去掉编号中的0层级"""
        #return [p for p in parts if p != 0]
        return parts

    def extract_number(self, text):
        """提取开头的数字编号，返回list[int]，没有则返回None"""
        text_clean = text.strip().replace(" ", "")
        match = re.match(r'^(\d+(?:\.\d+)*)', text_clean)
        if match:
            return [int(x) for x in match.group(1).split('.')]
        return None

    def find_invalid_and_clean(self, data):
        start_check = False
        sub_titles = []  # 记录所有子标题（带点编号）的位置
        max_chapter = 0

        # 第一遍：找出所有子标题的位置和最大章节号
        for i, item in enumerate(data):
            if item.get("text") == "目次" and item.get("text_level") == 1:
                start_check = True
                continue
            if not start_check:
                continue
            text = item.get("text")
            if not text:
                continue
            num_parts = self.extract_number(text)
            if not num_parts:
                continue
            norm_parts = self.normalize(num_parts)
            if len(norm_parts) > 1:  # 子标题（带点编号）
                sub_titles.append(i)
                max_chapter = max(max_chapter, norm_parts[0])

        # 第二遍：删除非法标题
        for idx, start_idx in enumerate(sub_titles):
            end_idx = sub_titles[idx + 1] if idx + 1 < len(sub_titles) else None

            # 范围：当前子标题和下一子标题之间（开区间）
            if end_idx:
                for i in range(start_idx + 1, end_idx):
                    if data[i].get("text_level") == 1:
                        num_parts = self.extract_number(data[i].get("text", ""))
                        if num_parts and len(self.normalize(num_parts)) == 1:
                            data[i].pop("text_level", None)
            else:
                # 最后一段：最后一个子标题之后
                for i in range(start_idx + 1, len(data)):
                    if data[i].get("text_level") == 1:
                        num_parts = self.extract_number(data[i].get("text", ""))
                        if num_parts:
                            norm_parts = self.normalize(num_parts)
                            if len(norm_parts) == 1 and norm_parts[0] <= max_chapter:
                                data[i].pop("text_level", None)

        # 第三遍：重新调整 text_level
        for i, item in enumerate(data):
            if not item.get("text_level"):
                continue
            text = item.get("text")
            num_parts = self.extract_number(text)
            if not num_parts:
                continue
            norm_parts = self.normalize(num_parts)
            if len(norm_parts) == 2:
                item["text_level"] = 2
            elif len(norm_parts) == 3:
                item["text_level"] = 3
            # 单数字不改

        return data

    def process_all_files(self):
        """处理目录中的所有文件并保存，使用类初始化时指定的dir_path"""
        files_list = os.listdir(self.dir_path)
        for file_name in files_list:
            json_file = os.path.join(self.dir_path, file_name, f"{file_name}_content_list.json")
            if not os.path.exists(json_file):
                print(f"文件不存在: {json_file}")
                continue

            # 读取 JSON 文件
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 调用处理逻辑
            cleaned_data = self.find_invalid_and_clean(data)

            # 输出目录
            output_dir = os.path.join(self.dir_path, "result")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{file_name}_content_list.json")

            # 保存结果
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=4)

            print(f"处理完成：{output_path}")

if __name__ == "__main__":
    # 初始化分析器并指定目录路径
    analyzer = TitleAnalyzer(dir_path="/home/ubuntu/Projects/titleAnalysis/output_0730/")
    # 处理所有文件
    analyzer.process_all_files()
# --coding:utf-8--
