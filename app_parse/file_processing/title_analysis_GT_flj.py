import json
import os
import re
from typing import List, Optional, Dict, Any, Tuple


class TitleAnalyzer:
    def __init__(
        self,
        dir_path: str,
        require_mulu: bool = True,
        remove_trailing_numbers: bool = False,
        log_level: str = "INFO",
    ):
        self.dir_path = dir_path
        self.require_mulu = require_mulu
        self.remove_trailing_numbers = remove_trailing_numbers
        self.log_level = log_level

        self.title_keywords = [
            "章", "节", "部分", "篇", "编", "section", "chapter", "part",
            "附录", "附件", "参考文献", "致谢", "摘要", "引言", "结论", "总结",
            "前言", "序言", "目录", "目次", "索引", "术语", "缩略语",
        ]

    # =========================
    # Logging
    # =========================
    def _log_debug(self, msg: str):
        if self.log_level == "DEBUG":
            print(f"[TitleAnalyzer DEBUG] {msg}")

    def _log_info(self, msg: str):
        if self.log_level in ["DEBUG", "INFO"]:
            print(f"[TitleAnalyzer INFO] {msg}")

    def _log_warning(self, msg: str):
        if self.log_level in ["DEBUG", "INFO", "WARNING"]:
            print(f"[TitleAnalyzer WARNING] {msg}")

    def _log_error(self, msg: str):
        print(f"[TitleAnalyzer ERROR] {msg}")

    # =========================
    # Helpers
    # =========================
    def normalize(self, parts: List[int]) -> List[int]:
        return parts

    def _normalize_heading_code_text(self, text: str) -> str:
        if not text:
            return ""

        text_clean = text.strip().replace("．", ".").replace("　", " ")
        normalized_chars = []
        for ch in text_clean:
            code = ord(ch)
            if 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
                normalized_chars.append(chr(code - 0xFEE0))
            else:
                normalized_chars.append(ch)
        return re.sub(r"\s+", " ", "".join(normalized_chars)).strip()

    def extract_number(self, text: str) -> Optional[List[int]]:
        """
        提取开头的数字编号（支持全角点）
        """
        if not text:
            return None
        text_clean = text.strip().replace(" ", "").replace("．", ".")
        match = re.match(r"^(\d+(?:\.\d+)*)", text_clean)
        if match:
            try:
                return [int(x) for x in match.group(1).split(".")]
            except ValueError as e:
                self._log_warning(f"编号解析失败: {text} - {e}")
                return None
        return None

    def _extract_appendix_ordinal_info(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None

        text_clean = self._normalize_heading_code_text(text)
        if not text_clean:
            return None

        def build_info(
            prefix: str,
            letter: str,
            first_sep: str,
            number_expr: Optional[str],
        ) -> Dict[str, Any]:
            letter = letter.upper()
            normalized_sep = "." if first_sep and "." in first_sep else ""
            number_parts: List[str] = []
            if number_expr:
                normalized_number_expr = re.sub(r"\s*\.\s*", ".", number_expr.strip())
                number_parts = [p for p in normalized_number_expr.split(".") if p]
            else:
                normalized_number_expr = ""

            code = letter
            if number_parts:
                if normalized_sep == ".":
                    code = f"{letter}.{'.'.join(number_parts)}"
                else:
                    code = f"{letter}{number_parts[0]}"
                    if len(number_parts) > 1:
                        code += "." + ".".join(number_parts[1:])

            ordinal_number = f"{prefix}{letter}" if prefix and not number_parts else code
            return {
                "ordinal_number": ordinal_number,
                "text_level": min(1 + len(number_parts), 4),
            }

        match = re.match(
            r"^(附录|附件)\s*([A-Za-z])(?:((?:\s*[\.．]\s*)|\s*)"
            r"(\d+(?:\s*[\.．]\s*\d+)*))?",
            text_clean,
        )
        if match:
            return build_info(
                prefix=match.group(1),
                letter=match.group(2),
                first_sep=match.group(3) or "",
                number_expr=match.group(4),
            )

        match = re.match(
            r"^([A-Z])((?:\s*[\.．]\s*)|\s*)(\d+(?:\s*[\.．]\s*\d+)*)",
            text_clean,
        )
        if match:
            return build_info(
                prefix="",
                letter=match.group(1),
                first_sep=match.group(2) or "",
                number_expr=match.group(3),
            )

        return None

    def extract_appendix_ordinal(self, text: str) -> Optional[str]:
        info = self._extract_appendix_ordinal_info(text)
        if not info:
            return None
        return info["ordinal_number"]

    def extract_title_ordinal_info(self, text: str) -> Optional[Dict[str, Any]]:
        num_parts = self.extract_number(text)
        if num_parts:
            norm_parts = self.normalize(num_parts)
            return {
                "ordinal_number": self._ordinal_parts_to_str(norm_parts),
                "text_level": min(len(norm_parts), 4),
            }

        return self._extract_appendix_ordinal_info(text)

    def extract_title_ordinal(self, text: str) -> Optional[str]:
        info = self.extract_title_ordinal_info(text)
        if not info:
            return None
        return info["ordinal_number"]

    def _get_text_level_from_ordinal(self, ordinal: str) -> int:
        info = self.extract_title_ordinal_info(ordinal)
        if info:
            return info["text_level"]
        return 0

    def _ordinal_parts_to_str(self, parts: List[int]) -> str:
        return ".".join(str(x) for x in parts)

    def _strip_leading_ordinal_from_text(self, text: str) -> str:
        """
        把开头编号剥离掉：
          - '2.2 符号 9' -> '符号 9'
          - '3建 筑 11' -> '建 筑 11'
          - '3.1.7医疗救护...' -> '医疗救护...'
        只剥离“开头的数字(.数字)*”，不处理末尾页码
        """
        if not text:
            return text

        # 兼容全角点
        t = text.replace("．", ".")

        # 处理多行：只对第一行做剥离
        lines = t.splitlines()
        if not lines:
            return text

        first = lines[0].strip()

        appendix_match = re.match(
            r"^\s*(?:附录|附件)\s*[A-Za-zＡ-Ｚａ-ｚ](?:(?:\s*[\.．]?\s*)\d+(?:\s*[\.．]\s*\d+)*)?\s*",
            first,
        )
        if appendix_match:
            first2 = first[appendix_match.end():].lstrip(" 　:：、.．-—")
            lines[0] = first2
            return "\n".join(lines)

        appendix_sub_match = re.match(
            r"^\s*[A-ZＡ-Ｚ](?:\s*[\.．]?\s*\d+)(?:\s*[\.．]\s*\d+)*\s*",
            first,
        )
        if appendix_sub_match:
            first2 = first[appendix_sub_match.end():].lstrip(" 　:：、.．-—")
            lines[0] = first2
            return "\n".join(lines)

        # 目录里常见：1总则 1（编号后不一定有空格）
        first2 = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", first)
        # 如果编号后紧跟汉字且上一步没去掉（极少），再兜底一次：去掉开头连续数字+点
        first2 = re.sub(r"^\s*\d+(?:\.\d+)*", "", first2).lstrip()

        lines[0] = first2
        return "\n".join(lines)

    # =========================
    # TOC Detection
    # =========================
    def is_toc_heading(self, text: str) -> bool:
        if not text:
            return False
        s = re.sub(r"\s+", " ", text.strip()).strip().lower()
        compact = re.sub(r"\s+", "", s)
        return compact in {"目次", "目录"} or s in {"contents", "table of contents"}

    def _is_toc_line(self, line: str) -> bool:
        if not line:
            return False
        s = re.sub(r"\s+", " ", line.strip())
        if not s:
            return False

        page_tail = r"\s+\d{1,4}$"

        if re.match(r"^\d+(?:\.\d+)*.*" + page_tail, s):
            m = re.match(r"^(\d+(?:\.\d+)*)\s*(.*?)\s+(\d{1,4})$", s)
            if m:
                mid = (m.group(2) or "").strip()
                if mid and not re.fullmatch(r"\d+", mid):
                    return True

        appendix_match = re.match(
            r"^((?:附录|附件)\s*[A-Za-zＡ-Ｚａ-ｚ](?:(?:\s*[\.．]?\s*)\d+(?:\s*[\.．]\s*\d+)*)?|[A-ZＡ-Ｚ](?:\s*[\.．]?\s*\d+)(?:\s*[\.．]\s*\d+)*)\s*(.*?)\s+(\d{1,4})$",
            s,
        )
        if appendix_match:
            mid = (appendix_match.group(2) or "").strip()
            if mid and not re.fullmatch(r"\d+", mid):
                return True

        if re.match(r"^((?:附录|附件)[ＡA-Z]\b|本规范用词说明|条文说明)\s*.*" + page_tail, s):
            return True

        return False

    def is_toc_block(self, text: str) -> bool:
        if not text:
            return False
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False
        hit = sum(1 for ln in lines if self._is_toc_line(ln))
        if len(lines) == 1 and hit == 1:
            return True
        return hit >= 1 and (hit / len(lines)) >= 0.6

    # =========================
    # Bullet/List Detection
    # =========================
    def is_plain_number_bullet(self, text: str) -> bool:
        if not text:
            return False
        return self.extract_plain_number_bullet_number(text) is not None

    def extract_plain_number_bullet_number(self, text: str) -> Optional[int]:
        if not text:
            return None

        text_clean = text.strip().replace("　", " ")
        if not text_clean:
            return None

        compact = text_clean.replace(" ", "").replace("．", ".")
        if re.match(r"^\d+(?:\.\d+)+", compact):
            return None

        # OCR 有时会把“1 9度...”粘成“19度...”，这里按列表项 1 处理。
        stuck_unit_match = re.match(
            r"^([1-9])(?=\d+(?:度|级|类|层|个|种|年|d|h|m|cm|mm|%|％))",
            compact,
            re.IGNORECASE,
        )
        if stuck_unit_match:
            return int(stuck_unit_match.group(1))

        marker_match = re.match(r"^(\d{1,2})[、）)]", text_clean)
        if marker_match:
            return int(marker_match.group(1))

        plain_match = re.match(r"^(\d{1,2})(?![0-9\.])\s*(?=\S)", text_clean)
        if plain_match:
            return int(plain_match.group(1))

        return None

    def is_list_intro_sentence(self, text: str) -> bool:
        if not text:
            return False
        t = text.strip()
        if t.endswith("：") or t.endswith(":"):
            return True
        keywords = [
            "包括下列", "包括以下", "如下", "下列", "以下", "应包括",
            "应符合下列", "应符合以下", "应满足下列", "应进行下列",
            "应按下列", "应按以下",
        ]
        return any(k in t for k in keywords)

    def is_list_item(self, text: str) -> bool:
        if not text:
            return False

        text_clean = text.strip()

        symbol_pattern = r"^[•\-\*·]\s*.{2,}"
        if re.match(symbol_pattern, text_clean):
            return True

        if re.match(r"^\d{4}[\s\-－年月日]+", text_clean):
            return True

        def contains_title_keyword(text_part: str) -> bool:
            title_keywords_exact = [
                "总则", "范围", "引言", "术语", "符号", "附录", "附件",
                "一般规定", "基本规定", "设计", "施工", "验收",
                "结构", "建筑", "电气", "给水", "排水", "通风",
            ]
            for kw in title_keywords_exact:
                if kw in text_part:
                    return True

            single_char_keywords = ["章", "节", "编", "篇"]
            for kw in single_char_keywords:
                pattern = f"(^|[0-9一二三四五六七八九十第]){kw}($|[^件款项])"
                if re.search(pattern, text_part):
                    return True
            return False

        match1 = re.match(r"^([一二三四五六七八九十]{1,3})[、）)](.*)$", text_clean)
        if match1:
            after_num = match1.group(2).strip()
            if contains_title_keyword(after_num) and len(after_num) <= 20:
                return False
            return True

        match2 = re.match(r"^[（(]([一二三四五六七八九十]{1,3})[）)](.*)$", text_clean)
        if match2:
            after_num = match2.group(2).strip()
            if contains_title_keyword(after_num) and len(after_num) <= 20:
                return False
            return True

        match3 = re.match(r"^第[一二三四五六七八九十]{1,3}[、，](.*)$", text_clean)
        if match3:
            after_num = match3.group(1).strip()
            if contains_title_keyword(after_num) and len(after_num) <= 20:
                return False
            return True

        if re.match(r"^\d+[、）)]", text_clean):
            return True

        single_num_match = re.match(r"^(\d+)\s*(.+)$", text_clean)
        if single_num_match:
            text_part = single_num_match.group(2)

            if "." not in text_clean[:10]:
                if contains_title_keyword(text_part) and len(text_part) <= 20:
                    return False

                if re.match(r"^[当如若应宜可必须凡]", text_part):
                    return True
                if "$" in text_part or "\\" in text_part:
                    return True
                if re.search(r"[时则者且]，", text_part):
                    return True
                if re.match(r"^(包括|采用|设置|不得|不应|不宜)", text_part):
                    return True

        return False

    def text_starts_with_sequence_number(self, text: str, number: int) -> bool:
        if not text:
            return False
        compact = (
            text.strip()
            .replace(" ", "")
            .replace("　", "")
            .replace("．", ".")
        )
        return re.match(rf"^(?:注[:：]?)?{number}(?![0-9\.])", compact) is not None

    def get_previous_nonempty_text(
        self, data: List[Dict[str, Any]], idx: int
    ) -> str:
        for prev_idx in range(idx - 1, -1, -1):
            item = data[prev_idx]
            if not isinstance(item, dict):
                continue
            text = item.get("text") or ""
            if text.strip():
                return text
        return ""

    def demote_numbered_list_sequences(
        self, data: List[Dict[str, Any]], start_idx: int = 0
    ) -> int:
        """
        将“下列/如下/包括：”后面的连续单数字序列整体识别为列表项。
        这里会把已经是正文的项也纳入序列判断，只对其中误识别为标题的项降级。
        """
        marked = 0
        idx = max(0, start_idx)

        while idx < len(data):
            item = data[idx]
            if not isinstance(item, dict):
                idx += 1
                continue

            first_num = self.extract_plain_number_bullet_number(item.get("text") or "")
            if first_num is None:
                idx += 1
                continue

            run: List[Tuple[int, int]] = []
            expected = first_num
            cursor = idx

            while cursor < len(data):
                cur_item = data[cursor]
                if not isinstance(cur_item, dict):
                    break
                cur_text = cur_item.get("text") or ""
                if not cur_text.strip():
                    break

                cur_num = self.extract_plain_number_bullet_number(cur_text)
                if cur_num is None or cur_num != expected:
                    break

                run.append((cursor, cur_num))
                expected += 1
                cursor += 1

            if len(run) >= 2:
                prev_text = self.get_previous_nonempty_text(data, run[0][0])
                continues_previous = (
                    first_num > 1
                    and self.text_starts_with_sequence_number(prev_text, first_num - 1)
                )
                if self.is_list_intro_sentence(prev_text) or continues_previous:
                    for run_idx, _ in run:
                        run_item = data[run_idx]
                        if run_item.get("text_level", 0) > 0:
                            run_item["text_level"] = 0
                            marked += 1
                    idx = cursor
                    continue

            idx += 1

        return marked

    # =========================
    # Title Likelihood
    # =========================
    def is_likely_title(self, text: str) -> bool:
        if not text:
            return False
        text_clean = re.sub(r"^\d+(?:\.\d+)*\s*", "", text.strip())
        if len(text_clean) <= 1:
            return False
        if any(keyword in text for keyword in self.title_keywords):
            return True
        if len(text_clean) >= 2:
            return True
        return False

    def is_consecutive_sequence(self, numbers: List[int], start: int = 1) -> bool:
        if len(numbers) < 3:
            return False
        for i, num in enumerate(numbers):
            if num != start + i:
                return False
        return True

    # =========================
    # Pass 1: Collect chapter/subtitle info
    # =========================
    def find_chapter_info(
        self, data: List[Dict[str, Any]], start_idx: int
    ) -> Dict[int, Dict[str, Any]]:
        chapters: Dict[int, Dict[str, Any]] = {}

        for i in range(start_idx, len(data)):
            if not isinstance(data[i], dict):
                continue

            text = data[i].get("text")
            text_level = data[i].get("text_level")

            if not text or text_level is None or text_level <= 0:
                continue

            if self.is_toc_heading(text) or self.is_toc_block(text):
                continue

            if self.is_plain_number_bullet(text) and self.is_list_intro_sentence(
                self.get_previous_nonempty_text(data, i)
            ):
                continue

            if self.is_list_item(text):
                continue

            num_parts = self.extract_number(text)
            if not num_parts:
                continue

            norm_parts = self.normalize(num_parts)
            chapter_no = norm_parts[0]

            if chapter_no not in chapters:
                chapters[chapter_no] = {
                    "candidates": [],
                    "sub_titles": [],
                    "first_sub_idx": None,
                    "last_sub_idx": None,
                    "selected_title_idx": None,
                }

            if len(norm_parts) == 1:
                chapters[chapter_no]["candidates"].append((i, text))
            else:
                chapters[chapter_no]["sub_titles"].append((i, len(norm_parts)))
                if chapters[chapter_no]["first_sub_idx"] is None:
                    chapters[chapter_no]["first_sub_idx"] = i
                chapters[chapter_no]["last_sub_idx"] = i

        return chapters

    # =========================
    # Pass 2: Select best chapter title
    # =========================
    def select_best_title(
        self, candidates: List[Tuple[int, str]], first_sub_idx: Optional[int]
    ) -> Optional[int]:
        if not candidates:
            return None

        scores = []
        for idx, text in candidates:
            score = 0

            if self.is_likely_title(text):
                score += 10
            else:
                score -= 5

            if first_sub_idx is not None and idx < first_sub_idx:
                score += 5

            text_clean = re.sub(r"^\d+(?:\.\d+)*\s*", "", text.strip())
            if 2 <= len(text_clean) <= 50:
                score += 3

            position_bonus = max(0, (1000 - idx) / 1000)
            score += position_bonus

            scores.append((idx, score))
            self._log_debug(f"    候选索引{idx}: '{text[:30]}' 得分={score:.2f}")

        scores.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score = scores[0]

        if best_score < 5:
            self._log_debug("    所有候选得分都太低，不选择章标题")
            return None

        return best_idx

    # =========================
    # Pass 5: Assign Ordinal_number
    # =========================
    def assign_ordinal_numbers(self, data: List[Dict[str, Any]]) -> int:
        """
        对 text_level > 0 的项：
          - 提取开头编号写入 Ordinal_number
          - 并从 text 中剥离该编号
        返回：写入的数量
        """
        count = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            tl = item.get("text_level")
            if tl is None or tl <= 0:
                continue

            text = item.get("text") or ""
            title_ordinal = self.extract_title_ordinal(text)
            if not title_ordinal:
                # 没有编号的标题（如“摘要/参考文献”）不强行写 Ordinal_number
                continue

            item["Ordinal_number"] = title_ordinal

            # 剥离编号
            new_text = self._strip_leading_ordinal_from_text(text)
            item["text"] = new_text

            count += 1
        return count

    # =========================
    # Main cleaning pipeline
    # =========================
    def find_invalid_and_clean(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not data:
            self._log_warning("输入数据为空")
            return data

        # ========== 步骤0：找到目次区间 ==========
        start_check_idx = 0
        mulu_idx = None
        toc_end_idx = 0

        if self.require_mulu:
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                text = (item.get("text") or "").replace(" ", "")
                text_level = item.get("text_level")
                if self.is_toc_heading(text) and text_level in [0, 1]:
                    mulu_idx = i
                    start_check_idx = i + 1
                    self._log_info(
                        f"在索引 {i} 处找到目录标记，从索引 {start_check_idx} 开始检查"
                    )
                    break

            toc_end_idx = start_check_idx
            if mulu_idx is not None:
                toc_end_idx = len(data)
                for j in range(start_check_idx, len(data)):
                    it = data[j]
                    if not isinstance(it, dict):
                        continue
                    tx = it.get("text") or ""
                    tl = it.get("text_level")
                    if not tx.strip():
                        continue
                    if (
                        tl is not None
                        and tl >= 1
                        and (not self.is_toc_heading(tx))
                        and (not self.is_toc_block(tx))
                    ):
                        toc_end_idx = j
                        break
        else:
            start_check_idx = 0
            toc_end_idx = 0

        # ========== 第一遍：收集章节信息（从正文开始，跳过目录） ==========
        chapter_scan_start = (
            toc_end_idx if (self.require_mulu and mulu_idx is not None) else start_check_idx
        )

        sequence_marked = self.demote_numbered_list_sequences(data, chapter_scan_start)
        if sequence_marked > 0:
            self._log_info(f"按连续编号序列降级了 {sequence_marked} 个列表项")

        chapters = self.find_chapter_info(data, chapter_scan_start)
        self._log_info(f"找到 {len(chapters)} 个章节")

        # ========== 第二遍：选择最优章标题，标记其余为正文 ==========
        marked_count = 0
        for chapter_no in sorted(chapters.keys()):
            info = chapters[chapter_no]
            candidates = info["candidates"]
            first_sub_idx = info["first_sub_idx"]
            if not candidates:
                continue

            selected_idx = self.select_best_title(candidates, first_sub_idx)
            info["selected_title_idx"] = selected_idx

            if selected_idx is not None:
                self._log_info(
                    f"第 {chapter_no} 章：选择索引 {selected_idx} 作为章标题: '{data[selected_idx].get('text','')[:40]}'"
                )

            for idx, text in candidates:
                if idx != selected_idx:
                    data[idx]["text_level"] = 0
                    marked_count += 1
        self._log_info(f"标记了 {marked_count} 个未选中的单数字标题为正文")

        # ========== 第三遍：处理尾部小数字（可选） ==========
        if self.remove_trailing_numbers:
            trailing_marked = 0
            for chapter_no in sorted(chapters.keys()):
                info = chapters[chapter_no]
                last_sub_idx = info["last_sub_idx"]
                if last_sub_idx is None:
                    continue

                next_chapter_start = len(data)
                for next_no in sorted(chapters.keys()):
                    if next_no <= chapter_no:
                        continue
                    next_info = chapters[next_no]
                    if next_info["selected_title_idx"] is not None:
                        next_chapter_start = next_info["selected_title_idx"]
                    elif next_info["first_sub_idx"] is not None:
                        next_chapter_start = next_info["first_sub_idx"]
                    break

                trailing_numbers = []
                for i in range(last_sub_idx + 1, next_chapter_start):
                    if i >= len(data):
                        break
                    item = data[i]
                    if not isinstance(item, dict):
                        break
                    text_level = item.get("text_level")
                    if text_level not in [0, 1]:
                        break

                    num_parts = self.extract_number(item.get("text", ""))
                    if num_parts and len(self.normalize(num_parts)) == 1:
                        trailing_numbers.append((i, num_parts[0], item.get("text")))
                    else:
                        break

                if not trailing_numbers:
                    continue

                numbers_only = [num for _, num, _ in trailing_numbers]
                if self.is_consecutive_sequence(numbers_only, start=1):
                    for idx, _, _ in trailing_numbers:
                        data[idx]["text_level"] = 0
                        trailing_marked += 1
                else:
                    for idx, num, text in trailing_numbers:
                        if num <= chapter_no and not self.is_likely_title(text or ""):
                            data[idx]["text_level"] = 0
                            trailing_marked += 1
                        else:
                            break

            if trailing_marked > 0:
                self._log_info(f"标记了 {trailing_marked} 个尾部小数字为正文")

        # ========== 第四遍：重算层级（含目录保护 + 列举项降级） ==========
        level_adjusted = 0
        list_items_marked = 0
        no_number_marked = 0
        toc_forced_zero = 0
        bullets_forced_zero = 0

        prev_text_nonempty = ""

        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue

            current_level = item.get("text_level")
            if current_level is None:
                continue

            text = item.get("text") or ""
            text_stripped = text.strip()

            # 目录保护
            if (
                self.require_mulu
                and (mulu_idx is not None)
                and (start_check_idx <= idx < toc_end_idx)
            ):
                if self.is_toc_heading(text) or self.is_toc_block(text):
                    if current_level != 0:
                        item["text_level"] = 0
                        level_adjusted += 1
                        toc_forced_zero += 1

                if text_stripped:
                    prev_text_nonempty = text
                continue

            # 引出句后的 1/2/3 列举项强制正文
            if self.is_plain_number_bullet(text) and self.is_list_intro_sentence(prev_text_nonempty):
                if current_level != 0:
                    item["text_level"] = 0
                    level_adjusted += 1
                    bullets_forced_zero += 1
                if text_stripped:
                    prev_text_nonempty = text
                continue

            # 列表项强制正文
            if self.is_list_item(text):
                if current_level != 0:
                    item["text_level"] = 0
                    level_adjusted += 1
                    list_items_marked += 1
                if text_stripped:
                    prev_text_nonempty = text
                continue

            # 仅对已有标题(text_level>0)进行层级重算，正文保持为0
            if current_level <= 0:
                appendix_ordinal = self.extract_appendix_ordinal(text)
                if appendix_ordinal:
                    item["text_level"] = self._get_text_level_from_ordinal(appendix_ordinal)
                    level_adjusted += 1
                if text_stripped:
                    prev_text_nonempty = text
                continue

            title_ordinal = self.extract_title_ordinal(text)

            # 无编号强制正文（保留你原规则）
            if not title_ordinal:
                if current_level != 0:
                    item["text_level"] = 0
                    level_adjusted += 1
                    no_number_marked += 1
                if text_stripped:
                    prev_text_nonempty = text
                continue

            old_level = current_level
            item["text_level"] = self._get_text_level_from_ordinal(title_ordinal)

            if old_level != item.get("text_level"):
                level_adjusted += 1

            if text_stripped:
                prev_text_nonempty = text

        self._log_info(f"重新调整了 {level_adjusted} 个标题的层级")
        if toc_forced_zero > 0:
            self._log_info(f"  - 目录条目强制为正文: {toc_forced_zero} 个")
        if bullets_forced_zero > 0:
            self._log_info(f"  - 列举项(1/2/3)强制为正文: {bullets_forced_zero} 个")
        self._log_info(f"  - 列表项: {list_items_marked} 个")
        self._log_info(f"  - 无编号文本: {no_number_marked} 个")

        # ========== 第五遍：写入 Ordinal_number + 剥离 text 开头编号 ==========
        ordinal_written = self.assign_ordinal_numbers(data)
        if ordinal_written > 0:
            self._log_info(f"写入 Ordinal_number 并剥离编号: {ordinal_written} 个")

        return data

    # =========================
    # File processing
    # =========================
    def process_data(
        self, data: List[Dict[str, Any]], source_name: str = "<memory>"
    ) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(data, list):
            self._log_error(f"数据格式错误: {source_name} (期望列表类型)")
            return None

        self._log_info(f"开始处理文件: {source_name} (共 {len(data)} 条记录)")
        return self.find_invalid_and_clean(data)

    def process_file(self, json_file: str) -> bool:
        if not os.path.exists(json_file):
            self._log_error(f"文件不存在: {json_file}")
            return False

        try:
            print(f"[TitleAnalyzer] 读取文件: {json_file}")
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cleaned_data = self.process_data(data, source_name=json_file)
            if cleaned_data is None:
                return False

            print(f"[TitleAnalyzer] 保存处理结果到: {json_file}")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=4)

            self._log_info(f"✓ 处理完成: {json_file}")
            return True

        except json.JSONDecodeError as e:
            self._log_error(f"JSON解析失败: {json_file} - {e}")
            import traceback
            traceback.print_exc()
            return False
        except IOError as e:
            self._log_error(f"文件读写错误: {json_file} - {e}")
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            self._log_error(f"处理文件时发生未知错误: {json_file} - {e}")
            import traceback
            traceback.print_exc()
            return False

    def process_all_files(self) -> Dict[str, int]:
        stats = {"success": 0, "failed": 0, "skipped": 0}

        if not os.path.exists(self.dir_path):
            self._log_error(f"目录不存在: {self.dir_path}")
            return stats

        if not os.path.isdir(self.dir_path):
            self._log_error(f"路径不是目录: {self.dir_path}")
            return stats

        try:
            files_list = os.listdir(self.dir_path)
            self._log_info(f"开始批量处理，共 {len(files_list)} 个子项")

            for file_name in files_list:
                json_file = os.path.join(
                    self.dir_path, file_name, f"{file_name}_content_list.json"
                )

                if not os.path.exists(json_file):
                    self._log_warning(f"文件不存在，跳过: {json_file}")
                    stats["skipped"] += 1
                    continue

                if self.process_file(json_file):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

            print(f"\n{'='*60}")
            self._log_info(
                f"批量处理完成 - 成功: {stats['success']}, 失败: {stats['failed']}, 跳过: {stats['skipped']}"
            )
            print(f"{'='*60}")
            return stats

        except PermissionError as e:
            self._log_error(f"权限错误: {self.dir_path} - {e}")
            return stats
        except Exception as e:
            self._log_error(f"批量处理时发生未知错误 - {e}")
            import traceback
            traceback.print_exc()
            return stats


if __name__ == "__main__":
    analyzer = TitleAnalyzer(
        dir_path="E:\\PycharmProjects\\flaskFileFragment\\data\\json_data",
        require_mulu=True,
        remove_trailing_numbers=False,
        log_level="INFO",
    )
    stats = analyzer.process_all_files()
    print(f"\n最终统计: {stats}")
