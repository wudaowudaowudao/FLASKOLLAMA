import os
import re
import markdown2
import latex2mathml.converter
from lxml import etree
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Pt, Inches
from docx.oxml import parse_xml
from docx.oxml.ns import qn

LATEX_MATH_PATTERN = re.compile(r'\$(.+?)\$')

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

def latex_to_omml(latex_expr):
    try:
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

def md_to_docx(md_file_path, docx_file_path):
    with open(md_file_path, 'r', encoding='utf-8') as file:
        md_content = file.read()

    html_content = markdown2.markdown(md_content)
    soup = BeautifulSoup(html_content, 'html.parser')

    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = '仿宋'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')

    for elem in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol', 'img', 'table']):
        if elem.name == 'h1':
            para = doc.add_heading(elem.get_text(strip=True), level=1)
            set_paragraph_style(para, font_name='仿宋', font_size=22, bold=True)
        elif elem.name == 'h2':
            para = doc.add_heading(elem.get_text(strip=True), level=2)
            set_paragraph_style(para, font_name='黑体', font_size=16, bold=True)
        elif elem.name == 'h3':
            para = doc.add_heading(elem.get_text(strip=True), level=3)
            set_paragraph_style(para, font_name='黑体', font_size=16, bold=True)
        elif elem.name == 'p':
            para = doc.add_paragraph()
            replace_latex_with_omml(para, elem.get_text())
            set_paragraph_style(para)
        elif elem.name == 'ul':
            for li in elem.find_all('li'):
                para = doc.add_paragraph(li.get_text(strip=True), style='List Bullet')
                set_paragraph_style(para)
        elif elem.name == 'ol':
            for li in elem.find_all('li'):
                para = doc.add_paragraph(li.get_text(strip=True), style='List Number')
                set_paragraph_style(para)
        elif elem.name == 'img':
            src = elem.get('src')
            if src:
                img_path = os.path.abspath(src)
                if os.path.exists(img_path):
                    para = doc.add_paragraph()
                    run = para.add_run()
                    run.add_picture(img_path, width=Inches(4))
                    set_paragraph_style(para)
                else:
                    print(f"❌ 图片文件不存在: {img_path}")
        elif elem.name == 'table':
            rows = elem.find_all('tr')
            if not rows:
                continue
            num_cols = len(rows[0].find_all(['th', 'td']))
            table = doc.add_table(rows=0, cols=num_cols)
            table.style = 'Table Grid'
            for row in rows:
                table_row = table.add_row()
                cells = row.find_all(['th', 'td'])
                for idx, cell in enumerate(cells):
                    if idx < num_cols:
                        cell_text = cell.get_text(strip=True)
                        paragraph = table_row.cells[idx].paragraphs[0]
                        paragraph.add_run(cell_text)
                        set_paragraph_style(paragraph)

    doc.save(docx_file_path)
    print(f"✅ Word 文件已保存至：{docx_file_path}")

if __name__ == "__main__":
    md_file_path = r"E:\PycharmProjects\FlaskOllama\output\zhang1\new\zhang1_zh.md"
    docx_file_path = r"E:\PycharmProjects\FlaskOllama\output\zhang1\new\zhang1_zh.docx"
    md_to_docx(md_file_path, docx_file_path)
