#部分公式可以转换
import json
import os
import re
import latex2mathml.converter
from lxml import etree
from docx import Document
from docx.shared import Inches, Pt
from docx.oxml.ns import qn
from docx.oxml import parse_xml
from bs4 import BeautifulSoup

# ========== LaTeX 公式匹配 ==========
LATEX_MATH_PATTERN = re.compile(r'\$(.+?)\$')

# ========== 文档初始化 ==========
doc = Document()
style = doc.styles['Normal']
font = style.font
font.name = '仿宋'
font.size = Pt(16)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')

# ========== 工具函数 ==========
def set_paragraph_style(paragraph, font_name='仿宋', font_size=16, bold=False):
    for run in paragraph.runs:
        run.font.name = font_name
        run.bold = bold
        run.font.size = Pt(font_size)
        r = run._element
        r.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    p_format = paragraph.paragraph_format
    p_format.line_spacing_rule = 1  # 固定值
    p_format.line_spacing = Pt(29)

def clean_latex_expr(expr):
    expr = expr.replace(r'\\', '\\')
    expr = expr.replace(r'\ ', ' ')
    expr = expr.replace(r'\%', '%')
    expr = expr.replace(r'~', ' ')
    expr = expr.replace(r'\circ', '°')
    expr = expr.replace(r'\mathrm{', '')
    expr = expr.replace('}', '')
    expr = expr.replace(r'^{+3}', '^{+3}')
    return expr.strip()

def latex_to_omml(latex_expr):
    try:
        latex_expr = clean_latex_expr(latex_expr)
        mathml_str = latex2mathml.converter.convert(latex_expr)
        mathml_xml = etree.fromstring(mathml_str.encode('utf-8'))
        xslt_path = os.path.join(os.path.dirname(__file__), 'mml2omml.xsl')
        xslt_doc = etree.parse(xslt_path)
        transform = etree.XSLT(xslt_doc)
        omml_tree = transform(mathml_xml)
        omml_str = etree.tostring(omml_tree, encoding='unicode')
        omml_element = parse_xml(omml_str)
        return omml_element
    except Exception as e:
        print(f"[公式转换失败] {latex_expr} 错误: {e}")
        return None

def replace_latex_with_omml(paragraph, text):
    parts = LATEX_MATH_PATTERN.split(text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part:
                run = paragraph.add_run(part)
                set_paragraph_style(paragraph)
        else:
            omml = latex_to_omml(part)
            if omml is not None:
                paragraph._element.append(omml)
            else:
                run = paragraph.add_run(f"${part}$")
                set_paragraph_style(paragraph)

def add_content(doc, item, image_dir):
    if item['type'] == 'text':
        text = item.get('text', '').strip()
        level = item.get('text_level', None)

        if level == 1:
            para = doc.add_heading(text, level=1)
            set_paragraph_style(para, font_name='仿宋', font_size=22, bold=True)
        elif level == 2:
            para = doc.add_heading(text, level=2)
            set_paragraph_style(para, font_name='黑体', font_size=16, bold=True)
        else:
            para = doc.add_paragraph()
            replace_latex_with_omml(para, text)
            set_paragraph_style(para, font_name='仿宋', font_size=16)

    elif item['type'] == 'image':
        img_filename = item.get('img_path', '')
        img_path = os.path.join(image_dir, os.path.basename(img_filename))
        if os.path.exists(img_path):
            print(f"[图片导入成功] {img_path}")
            doc.add_picture(img_path, width=Inches(5))
        else:
            print(f"[图片未找到] {img_path}")

        if item.get('img_caption'):
            para = doc.add_paragraph("图注：" + ''.join(item['img_caption']))
            set_paragraph_style(para)
        if item.get('img_footnote'):
            para = doc.add_paragraph("脚注：" + ''.join(item['img_footnote']))
            set_paragraph_style(para)

    elif item['type'] == 'table':
        html = item.get('table_body', '')
        soup = BeautifulSoup(html, 'html.parser')
        table_tag = soup.find('table')

        if table_tag:
            rows = table_tag.find_all('tr')
            if rows:
                max_cols = max(len(row.find_all(['td', 'th'])) for row in rows)
                table = doc.add_table(rows=0, cols=max_cols)
                table.style = 'Table Grid'

                for row in rows:
                    row_cells = row.find_all(['td', 'th'])
                    doc_row = table.add_row()
                    for j, cell in enumerate(row_cells):
                        if j < max_cols:
                            para = doc_row.cells[j].paragraphs[0]
                            replace_latex_with_omml(para, cell.get_text(strip=True))
                            set_paragraph_style(para)
        else:
            print("[表格解析失败] 无法从 table_body 中提取 <table> 标签")

        if item.get('table_caption'):
            para = doc.add_paragraph("表注：" + ''.join(item['table_caption']))
            set_paragraph_style(para)
        if item.get('table_footnote'):
            para = doc.add_paragraph("脚注：" + ''.join(item['table_footnote']))
            set_paragraph_style(para)

# ========== 主处理逻辑 ==========
if __name__ == '__main__':
    # 路径配置
    input_path = 'data/jsonToWord/3246f125010542c29d515f88d7285b46/3246f125010542c29d515f88d7285b46_content_list.json'
    output_path = 'output/jsonToWord/yu.docx'
    image_dir = os.path.join(os.path.dirname(input_path), 'image')

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for item in data:
        add_content(doc, item, image_dir)

    doc.save(output_path)
    print(f"[完成] 文档已保存为：{output_path}")
