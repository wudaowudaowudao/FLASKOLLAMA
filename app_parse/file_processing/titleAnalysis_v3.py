import os
import re
import json
import shutil
from collections import Counter


class TitleAnalyzer:
    def __init__(self, dir_path):
        self.dir = dir_path
        self.level_queue = {}  # 初始化时暂不设置，后续动态生成

    def normalize_text(self, text):
        """标准化文本：去除空格、替换全角符号"""
        text = text.strip()
        text = text.replace("．", ".").replace("。", ".")
        text = text.replace("，", "、").replace("：", ":")
        text = text.replace("（", "(").replace("）", ")")
        text = text.replace(" ", "")
        return text

    def detect_chinese_heading(self, data):
        """判断是否存在中文编号作为一级标题"""
        for item in data:
            if item.get("type") == "text":
                if re.match(r'^[一二三四五六七八九十]+[、.]?', self.normalize_text(item["text"])):
                    return True
        return False

    def build_level_queue(self, has_chinese_heading):
        """根据是否有中文编号生成标题层级的正则规则"""
        q = {}
        if has_chinese_heading:
            q[1] = [r'^[一二三四五六七八九十]+[、.]?']
            q[2] = [r'^\d+(?![\.\d])', r'^\d+\.(?!\d)']
            start = 3
        else:
            q[1] = [r'^[一二三四五六七八九十]+[、.]?', r'^\d+(?![\.\d])', r'^\d+\.(?!\d)']
            start = 2
        for i in range(start, 7):
            pattern = r'^' + r'\d+' + ''.join([r'\.\d+'] * (i - 1)) + r'(?!\.)'
            q[i] = [pattern]
        self.level_queue = q

    def determine_level(self, text):
        """判断文本是否为标题，以及其等级"""
        text = self.normalize_text(text)

        # 尝试匹配规则
        for i in range(1, 7):
            for pattern in self.level_queue[i]:
                if re.match(pattern, text):
                    num_match = re.match(r'^(\d+)', text)
                    if num_match:
                        num = int(num_match.group(1))
                        if num >= 100:
                            continue
                    return i

        # OCR错误兼容：例如"1 2标题"，空格替换为点后再判断
        if re.match(r'^\d+\s+\d+', text):
            text_fixed = text.replace(" ", ".", 1)
            return self.determine_level(text_fixed)

        return 0

    def extract_titles(self, data):
        levels = []
        titles = []
        for item in data:
            if item.get("type") == "text":
                level = self.determine_level(item["text"])
                if level != 0:
                    levels.append(level)
                    titles.append([self.normalize_text(item["text"]), level])
        return levels, titles

    def filter_levels(self, levels):
        count = Counter(levels)
        filtered = [lvl for lvl, c in sorted(count.items()) if c > 3]
        return [(lvl, i + 1) for i, lvl in enumerate(filtered)]

    def normalize_title_levels(self, titles, level_map):
        for item in titles:
            for orig_lvl, new_lvl in level_map:
                if item[1] == orig_lvl:
                    item[1] = new_lvl
        return titles

    def set_text_levels(self, data, titles):
        title_dict = {text: level for text, level in titles}
        for item in data:
            if item.get("type") == "text":
                text = self.normalize_text(item["text"])
                if text in title_dict:
                    item["text_level"] = title_dict[text]
                else:
                    # 无编号短标题作为一级
                    if not re.match(r'^\d', text) and not re.search(r'[。.!?]$', text) and len(text) <= 20:
                        item["text_level"] = 1
                    else:
                        item["text_level"] = 0
        return data

    def process_file(self, json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        has_chinese_heading = self.detect_chinese_heading(data)
        self.build_level_queue(has_chinese_heading)

        levels, titles = self.extract_titles(data)
        level_map = self.filter_levels(levels)
        normalized_titles = self.normalize_title_levels(titles, level_map)
        data = self.set_text_levels(data, normalized_titles)

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"处理完成: {json_file}")
        return data

    def process_all_files(self):
        """处理目录中的所有文件"""
        files_list = os.listdir(self.dir)
        for file_name in files_list:
            json_file = os.path.join(self.dir, file_name, f"{file_name}_content_list.json")
            if not os.path.exists(json_file):
                print(f"文件不存在: {json_file}")
                continue
            self.process_file(json_file)

    def copy_file(self, json_file):
        if not os.path.exists(json_file):
            print(f"文件不存在: {json_file}")
            return
        base, ext = os.path.splitext(json_file)
        new_file = f"{base}_titleless{ext}"
        shutil.copy2(json_file, new_file)
        print(f"文件已复制到: {new_file}")

if __name__ == "__main__":
    # 你的 JSON 文件夹路径
    analyzer = TitleAnalyzer(dir_path="/home/crrc/Projects/flaskFileFragment/data/jsonTitle")
    analyzer.process_all_files()
