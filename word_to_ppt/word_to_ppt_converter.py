import os
import sys
from docx import Document
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
import argparse
import tempfile  # 添加这行导入语句

class WordToPPTConverter:
    def __init__(self, template_path=None):
        if template_path and os.path.exists(template_path):
            self.prs = Presentation(template_path)
        else:
            self.prs = Presentation()
        self.slide_layout = self.prs.slide_layouts[7]  # 使用标题和内容布局
        
    def read_word_document(self, word_file_path):
        """读取Word文档内容"""
        try:
            doc = Document(word_file_path)
            content = []
            current_heading = None
            current_heading_index = None
            heading_index_map = {}  # 存储标题与索引的映射
            heading_counter = 0  # 一级标题计数器
            tables_by_heading = {}  # 存储每个标题下的表格
            
            # 遍历段落，将图片插入到正确的位置
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    # 根据段落样式判断类型
                    style_name = paragraph.style.name.lower()
                    if style_name == 'title':
                        content.append({
                            'type': 'title',
                            'text': paragraph.text.strip()
                        })
                    elif style_name == 'subtitle':
                        content.append({
                            'type': 'subtitle',
                            'text': paragraph.text.strip()
                        })
                    elif style_name.startswith('heading'):
                        # 遇到新的一级标题时，更新当前标题和索引
                        if style_name.endswith('1'):
                            heading_counter += 1
                            current_heading = paragraph.text.strip()
                            current_heading_index = heading_counter
                            heading_index_map[current_heading] = current_heading_index
                            tables_by_heading[current_heading_index] = []
                            print(f"发现一级标题: {current_heading}, 索引: {current_heading_index}")
                        
                        content.append({
                            'type': 'heading',
                            'text': paragraph.text.strip(),
                            'level': int(style_name.split()[-1]) if style_name.split()[-1].isdigit() else 1,
                            'heading': current_heading,
                            'heading_index': current_heading_index
                        })
                    else:
                        content.append({
                            'type': 'paragraph',
                            'text': paragraph.text.strip(),
                            'heading': current_heading,
                            'heading_index': current_heading_index
                        })
                
                # 检查段落中的图片
                for run in paragraph.runs:
                    # 获取段落中的所有图片
                    for inline in run._element.findall('.//wp:inline', 
                            {'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}):
                        blip = inline.find('.//a:blip', 
                            {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
                        if blip is not None:
                            rId = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                            image_part = doc.part.related_parts[rId]
                            # 将图片添加到当前位置
                            content.append({
                                'type': 'image',
                                'data': image_part.blob,
                                'heading': current_heading,
                                'heading_index': current_heading_index
                            })
            
            # 处理表格
            for table in doc.tables:
                table_data = []
                for row in table.rows:
                    row_data = []
                    for cell in row.cells:
                        row_data.append(cell.text.strip())
                    table_data.append(row_data)
                
                # 找出表格所属的章节索引
                table_heading = current_heading
                table_heading_index = current_heading_index
                
                # 将表格添加到对应标题索引的列表中
                if table_heading_index is not None:
                    tables_by_heading[table_heading_index].append(table_data)
                    print(f"添加表格到标题索引 {table_heading_index}, 所属章节: {table_heading}, 行数: {len(table_data)}")
                
                content.append({
                    'type': 'table',
                    'data': table_data,
                    'heading': table_heading,
                    'heading_index': table_heading_index
                })
            
            # 将表格映射添加到返回内容中
            content.append({
                'type': 'tables_map',
                'data': tables_by_heading
            })
            
            return content
        except Exception as e:
            print(f"读取Word文档时出错: {e}")
            return None

    def process_content(self, content_data):
        if not content_data:
            return False
        
        # 初始化标题和副标题
        main_title = None
        subtitle = None
        current_section = None
        tables_by_heading = None
        
        # 提取表格映射
        for item in content_data:
            if item['type'] == 'tables_map':
                tables_by_heading = item['data']
                break
        
        if not tables_by_heading:
            print("警告：没有找到表格映射数据")
            tables_by_heading = {}
        
        # 第一遍遍历：找出主标题和副标题
        for item in content_data:
            if item['type'] == 'title':
                main_title = item['text']
            elif item['type'] == 'subtitle':
                subtitle = item['text']
        
        # 如果有标题，创建标题页
        if main_title:
            self.create_title_slide(main_title, subtitle)
        
        # 收集所有章节及其内容
        sections = {}
        section_indices = {}
        
        # 第二遍遍历：收集所有章节及其内容
        for item in content_data:
            if item['type'] == 'heading' and item.get('level', 1) == 1:
                # 创建新的章节
                section_title = item['text']
                section_index = item.get('heading_index')
                if section_title not in sections:
                    sections[section_title] = {
                        'title': section_title,
                        'content': [],
                        'images': [],
                        'tables': [],
                        'index': section_index
                    }
                    section_indices[section_index] = section_title
            elif item['type'] == 'paragraph':
                # 将段落添加到其所属的章节
                heading = item.get('heading')
                if heading and heading in sections:
                    sections[heading]['content'].append(item['text'])
            elif item['type'] == 'image':
                # 将图片添加到其所属的章节
                heading = item.get('heading')
                if heading and heading in sections:
                    sections[heading]['images'].append(item['data'])
            elif item['type'] == 'table' and item.get('type') != 'tables_map':
                # 将表格添加到其所属的章节
                heading = item.get('heading')
                heading_index = item.get('heading_index')
                if heading and heading in sections:
                    sections[heading]['tables'].append(item['data'])
        
        # 按照索引顺序创建幻灯片
        for index in sorted(section_indices.keys()):
            section_title = section_indices[index]
            section_data = sections[section_title]
            
            # 获取该章节对应的表格数据
            section_tables = tables_by_heading.get(index, [])
            
            print(f"创建章节幻灯片: {section_title}, 索引: {index}, 表格数量: {len(section_tables)}")
            
            self.create_content_slide(
                section_data['title'],
                section_data['content'],
                section_data['images'],
                section_tables
            )
        
        return True
    
    def create_content_slide(self, title, content_list, images=None, tables=None):
        # 创建内容页
        slide = self.prs.slides.add_slide(self.slide_layout)
        table_placeholder_found = False
        
        # 遍历所有占位符，找到对应的内容区域
        for shape in slide.placeholders:
            print(f"占位符类型: {shape.placeholder_format.type}, 名称: {shape.name}")
            
            if shape.placeholder_format.type == 1:  # 标题占位符
                shape.text = title
                shape.text_frame.paragraphs[0].font.size = Pt(32)
                shape.text_frame.paragraphs[0].font.bold = True
            elif shape.placeholder_format.type == 2:  # 正文占位符
                text_frame = shape.text_frame
                text_frame.clear()
                # 添加文本内容
                for i, content in enumerate(content_list):
                    if i == 0:
                        p = text_frame.paragraphs[0]
                    else:
                        p = text_frame.add_paragraph()
                    p.text = content
                    p.font.size = Pt(18)
                    p.font.name = 'Microsoft YaHei'
                    if i < len(content_list) - 1:
                        p.space_after = Pt(12)
            elif shape.placeholder_format.type == 18:  # 图片占位符
                if images and len(images) > 0:
                    # 获取占位符的尺寸
                    width = shape.width
                    height = shape.height
                    left = shape.left
                    top = shape.top
                    
                    # 计算每个图片的大小
                    image_count = len(images)
                    image_width = width / image_count
                    image_height = height
                    
                    # 添加图片
                    for i, image_data in enumerate(images):
                        # 保存图片到临时文件
                        temp_dir = tempfile.gettempdir()
                        temp_image = os.path.join(temp_dir, f'temp_image_{i}.png')
                        with open(temp_image, 'wb') as f:
                            f.write(image_data)
                        
                        # 在占位符区域内添加图片
                        x = left + (i * image_width)
                        slide.shapes.add_picture(
                            temp_image,
                            x, top,
                            width=image_width,
                            height=image_height
                        )
                        
                        try:
                            os.remove(temp_image)
                        except:
                            pass
            elif shape.placeholder_format.type == 12:  # 表格占位符
                table_placeholder_found = True
                if tables and len(tables) > 0:
                    print(f"在幻灯片 '{title}' 中找到表格占位符，准备插入表格")
                    # 获取表格数据
                    table_data = tables[0]  # 使用当前章节的第一个表格
                    rows = len(table_data)
                    cols = len(table_data[0]) if rows > 0 else 0
                    
                    if rows > 0 and cols > 0:
                        # 在占位符位置创建表格
                        table = shape.insert_table(rows, cols).table
                        
                        # 填充表格数据
                        for row_idx, row in enumerate(table_data):
                            for col_idx, cell_text in enumerate(row):
                                if col_idx < cols:
                                    cell = table.cell(row_idx, col_idx)
                                    cell.text = cell_text
                                    paragraph = cell.text_frame.paragraphs[0]
                                    paragraph.font.size = Pt(12)
                                    paragraph.font.name = 'Microsoft YaHei'
                                    paragraph.alignment = PP_ALIGN.CENTER
        
        # 如果没有找到表格占位符但有表格数据，说明可能使用了错误的布局
        if not table_placeholder_found and tables and len(tables) > 0:
            print(f"警告：在幻灯片 '{title}' 中没有找到表格占位符，请检查模板布局是否正确")
        
        return slide
    
    def create_title_slide(self, title, subtitle=None):
        """创建标题幻灯片，支持副标题"""
        slide_layout = self.prs.slide_layouts[0]  # 标题幻灯片布局
        slide = self.prs.slides.add_slide(slide_layout)
        
        # 设置主标题
        title_shape = slide.shapes.title
        title_shape.text = title
        title_shape.text_frame.paragraphs[0].font.size = Pt(44)
        title_shape.text_frame.paragraphs[0].font.bold = True
        title_shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        
        # 设置副标题
        if subtitle:
            subtitle_shape = slide.placeholders[1]  # 副标题占位符
            subtitle_shape.text = subtitle
            subtitle_shape.text_frame.paragraphs[0].font.size = Pt(32)
            subtitle_shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        
        return slide
    
    def save_presentation(self, output_path):
        """保存PPT文件"""
        try:
            self.prs.save(output_path)
            return True
        except Exception as e:
            print(f"保存PPT文件时出错: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='将Word文档转换为PowerPoint演示文稿')
    parser.add_argument('input_file', help='输入的Word文件路径')
    parser.add_argument('-o', '--output', help='输出的PPT文件路径（可选）')
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input_file):
        print(f"错误：找不到输入文件 {args.input_file}")
        sys.exit(1)
    
    # 确定输出文件路径
    if args.output:
        output_file = args.output
    else:
        base_name = os.path.splitext(os.path.basename(args.input_file))[0]
        output_file = f"{base_name}.pptx"
    
    # 确保输出文件有正确的扩展名
    if not output_file.endswith('.pptx'):
        output_file += '.pptx'
    
    print(f"正在处理文件: {args.input_file}")
    print(f"输出文件: {output_file}")
    
    # 创建转换器实例
    converter = WordToPPTConverter()
    
    # 读取Word文档
    content = converter.read_word_document(args.input_file)
    if content is None:
        print("读取Word文档失败")
        sys.exit(1)
    
    # 处理内容并生成PPT
    if not converter.process_content(content):
        print("处理内容失败")
        sys.exit(1)
    
    # 保存PPT文件
    if converter.save_presentation(output_file):
        print(f"成功生成PPT文件: {output_file}")
    else:
        print("保存PPT文件失败")
        sys.exit(1)

if __name__ == "__main__":
    main()