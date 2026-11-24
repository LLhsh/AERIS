import os
import PyPDF2
from docx import Document as DocxDocument
from docx.shared import Inches
from PIL import Image
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.text.paragraph import Paragraph

def parse_file(file_path):
    """从PDF或DOCX文件中提取文本内容"""
    text = ""
    if not file_path:
        return None
    try:
        file_name = os.path.basename(file_path)
        if file_path.lower().endswith(".pdf"):
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                if not pdf_reader.pages:
                    return f"警告: 文件 '{file_name}' 是一个空的或无法读取的 PDF。"
                for page in pdf_reader.pages:
                    text += page.extract_text() or ""
        elif file_path.lower().endswith(".docx"):
            document = DocxDocument(file_path)
            for para in document.paragraphs:
                text += para.text + "\n"
        else:
            return f"错误: 不支持的文件类型: '{file_name}'. 请上传 PDF 或 DOCX 文件。"
    except Exception as e:
        return f"错误: 解析文件 '{os.path.basename(file_path)}' 时出错: {e}"
    return text

def insert_paragraph_after(paragraph, text='', style=None):
    """在指定段落后插入新段落"""
    new_p = OxmlElement('w:p')
    paragraph._p.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    if text:
        new_para.add_run(text)
    if style:
        new_para.style = style
    return new_para

def set_table_borders(table):
    """设置表格边框"""
    tbl = table._element
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), '000000')
        borders.append(border)
    tblPr.append(borders)

def auto_fit_table_to_contents(table):
    """自动调整表格大小以适应内容"""
    tbl = table._element
    tblPr = tbl.tblPr
    tblW = tblPr.xpath("./w:tblW")
    if tblW:
        tblPr.remove(tblW[0])
    tblLayout = tblPr.find(qn('w:tblLayout'))
    if tblLayout is not None:
        tblPr.remove(tblLayout)

def center_cell(cell):
    """设置单元格内容居中"""
    # 水平居中
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 垂直居中
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER 