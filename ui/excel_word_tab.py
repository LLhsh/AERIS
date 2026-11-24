from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QFileDialog, QMessageBox, QComboBox, QToolButton, QMenu, QInputDialog, QAction
)
from PySide2.QtCore import Qt, Signal, Slot, QSize
from PySide2.QtGui import QMovie, QIcon

import os
import sys
import json
import pandas as pd

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.api_worker import OllamaApiWorker
from utils.file_utils import (
    insert_paragraph_after, set_table_borders, auto_fit_table_to_contents, center_cell
)
from docx import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT

class ExcelWordTab(QWidget):
    """Excel-Word工具标签页"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 数据变量
        self.word_file_path = ""
        self.json_data_for_table = None
        self.extracted_text_content = ""
        self.current_selected_model = "deepseek-r1:70b"  # 默认模型
        self.excel_df = None  # 存储Excel数据
        self.excel_file_path = ""  # Excel文件路径
        self.api_worker = None  # 保存API工作线程的引用
        self.is_api_running = False  # API是否正在运行的标志
        self.current_insert_mode = "smart"  # 默认使用智能定位模式
        self.fill_mode = "only_existing"  # 默认仅填充已有参数
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # 设置所有按钮的统一宽度
        button_width = 380
        
        # Excel数据提取按钮
        excel_btn_layout = QHBoxLayout()
        self.btn_open_excel = QPushButton('📊 选择Excel文件并提取数据')
        self.btn_open_excel.setMinimumWidth(button_width)
        self.btn_open_excel.setFixedWidth(button_width)
        self.btn_open_excel.setFixedHeight(32)
        self.btn_open_excel.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-radius: 4px;
                padding: 5px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        self.btn_open_excel.clicked.connect(self.open_excel_and_extract)
        excel_btn_layout.addWidget(self.btn_open_excel)
        excel_btn_layout.addStretch()
        layout.addLayout(excel_btn_layout)
        
        # Excel数据填充Word按钮组（主按钮+下拉按钮）
        fill_btn_layout = QHBoxLayout()
        fill_btn_layout.setSpacing(0)  # 设置按钮之间无间距
        
        # 主填充Word按钮
        self.btn_fill_word = QPushButton('📝 填充Word文档（仅填充已有参数）')
        self.btn_fill_word.setMinimumWidth(button_width - 32)  # 减去下拉按钮的宽度
        self.btn_fill_word.setFixedHeight(32)
        self.btn_fill_word.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 5px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        self.btn_fill_word.clicked.connect(self.on_fill_button_clicked)
        fill_btn_layout.addWidget(self.btn_fill_word)
        
        # 下拉菜单按钮
        self.btn_fill_dropdown = QPushButton('▼')
        self.btn_fill_dropdown.setFixedSize(32, 32)
        self.btn_fill_dropdown.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        
        # 创建菜单
        self.fill_menu = QMenu()
        self.action_fill_existing = QAction('📝 填充Word文档（仅填充已有参数）', self)
        self.action_fill_all = QAction('📝 填充Word文档（添加缺失参数）', self)
        
        # 添加菜单项
        self.fill_menu.addAction(self.action_fill_existing)
        self.fill_menu.addAction(self.action_fill_all)
        
        # 连接事件
        self.action_fill_existing.triggered.connect(lambda: self.change_fill_mode("only_existing"))
        self.action_fill_all.triggered.connect(lambda: self.change_fill_mode("add_missing"))
        
        # 设置下拉按钮的点击事件
        self.btn_fill_dropdown.clicked.connect(self.show_fill_menu)
        
        fill_btn_layout.addWidget(self.btn_fill_dropdown)
        fill_btn_layout.addStretch()
        
        layout.addLayout(fill_btn_layout)
        
        # 表格插入按钮组（主按钮+下拉按钮）
        table_btn_layout = QHBoxLayout()
        table_btn_layout.setSpacing(0)  # 设置按钮之间无间距
        
        # 主插入表格按钮
        self.btn_insert_table = QPushButton('📊 智能插入表格到Word（使用大模型）')
        self.btn_insert_table.setMinimumWidth(button_width - 32)  # 减去下拉按钮的宽度
        self.btn_insert_table.setFixedHeight(32)
        self.btn_insert_table.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 5px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        self.btn_insert_table.clicked.connect(self.on_insert_button_clicked)
        table_btn_layout.addWidget(self.btn_insert_table)
        
        # 下拉菜单按钮
        self.btn_table_dropdown = QPushButton('▼')
        self.btn_table_dropdown.setFixedSize(32, 32)
        self.btn_table_dropdown.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        
        # 创建菜单
        self.table_insert_menu = QMenu()
        self.action_smart_insert = QAction('📊 智能插入表格到Word（使用大模型）', self)
        self.action_direct_insert = QAction('📊 直接插入表格到Word（使用占位符）', self)
        
        # 添加菜单项
        self.table_insert_menu.addAction(self.action_smart_insert)
        self.table_insert_menu.addAction(self.action_direct_insert)
        
        # 连接事件
        self.action_smart_insert.triggered.connect(lambda: self.change_insert_mode("smart"))
        self.action_direct_insert.triggered.connect(lambda: self.change_insert_mode("direct"))
        
        # 设置下拉按钮的点击事件
        self.btn_table_dropdown.clicked.connect(self.show_table_insert_menu)
        
        table_btn_layout.addWidget(self.btn_table_dropdown)
        table_btn_layout.addStretch()
        
        layout.addLayout(table_btn_layout)
        
        # 图片插入按钮
        btn_layout2 = QHBoxLayout()
        self.btn_insert_img = QPushButton('🖼️ 插入图片到Word')
        self.btn_insert_img.setMinimumWidth(button_width)
        self.btn_insert_img.setFixedWidth(button_width)
        self.btn_insert_img.setFixedHeight(32)
        self.btn_insert_img.setStyleSheet("""
            QPushButton {
                background-color: #0078d7;
                color: white;
                border-radius: 4px;
                padding: 5px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #00639c;
            }
            QPushButton:pressed {
                background-color: #004e8c;
            }
        """)
        self.btn_insert_img.clicked.connect(self.insert_image_to_word)
        btn_layout2.addWidget(self.btn_insert_img)
        btn_layout2.addStretch()
        layout.addLayout(btn_layout2)
        
        # Excel数据显示区域
        layout.addWidget(QLabel("Excel提取的数据:"))
        self.excel_data_display = QTextEdit()
        self.excel_data_display.setReadOnly(True)
        self.excel_data_display.setFixedHeight(200)  # 略微减小Excel数据显示区域高度
        layout.addWidget(self.excel_data_display)
        
        # 表格插入提示词
        layout.addWidget(QLabel("智能表格插入提示词:"))
        self.table_position_prompt = QTextEdit()
        self.table_position_prompt.setPlainText("""请分析文档内容，找出最适合插入财务数据表格的位置，所要求规则如下。
        1.请确保你的回复只包含这个关键词或短语，且这个关键词或者短语本身在我传入给你的文本信息中，即如果我发送给你的文本信息不存在这个关键词则不能够输出，不要有任何额外说明或格式。
        2.请仅回复一个简单的关键词或短语，这将作为定位表格插入点的标记。例如，如果文档中有"财务概况"部分，你可以回复"财务概况"，如若没有则不可以回复相应的关键词和短语。
        """)
        self.table_position_prompt.setFixedHeight(180)  # 增加提示词输入框高度
        layout.addWidget(self.table_position_prompt)
        
        # 状态标签区域（添加加载动画）
        status_layout = QHBoxLayout()
        
        status_label_layout = QVBoxLayout()
        status_label_layout.addWidget(QLabel("Excel/表格状态:"))
        self.table_position_status = QLabel("未确定")
        self.table_position_status.setObjectName("statusLabel")
        status_label_layout.addWidget(self.table_position_status)
        status_layout.addLayout(status_label_layout, 1)
        
        # 添加加载动画
        self.loading_label = QLabel()
        self.loading_label.setObjectName("loadingLabel")
        gif_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "loading.gif")
        self.loading_movie = QMovie(gif_path)
        if not self.loading_movie.isValid():
            print(f"警告: 无法加载 loading.gif 文件于路径: {gif_path}。加载动画将不可用。")
            self.loading_label.setText("处理中...")
        else:
            self.loading_label.setMovie(self.loading_movie)
        self.loading_movie.setScaledSize(QSize(28, 28))
        self.loading_label.setFixedSize(32, 32)
        self.loading_label.hide()
        status_layout.addWidget(self.loading_label)
        
        layout.addLayout(status_layout)
        
        # 当前可用数据状态
        layout.addWidget(QLabel("当前数据状态:"))
        self.data_status_label = QLabel("无可用的表格数据")
        self.data_status_label.setObjectName("statusLabel")
        layout.addWidget(self.data_status_label)
    
    def open_excel_and_extract(self):
        """选择Excel文件并提取数据"""
        file_path, _ = QFileDialog.getOpenFileName(self, '选择Excel文件', '', '所有文件 (*.*);;Excel files (*.xlsx *.xls)')
        if not file_path:
            return
        
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'无法读取Excel文件：{str(e)}')
            return
        
        if df.shape[1] < 2:
            QMessageBox.critical(self, '错误', 'Excel文件应至少有两列，第一列为型号，后面为参数')
            return
        
        self.excel_df = df.fillna('').astype(str)
        self.excel_file_path = file_path
        
        # 显示提取的数据
        self.excel_data_display.clear()
        self.excel_data_display.append(f'已提取Excel文件: {os.path.basename(file_path)}\n')
        self.excel_data_display.append('提取的Excel内容（型号及对应参数）：\n')
        
        for idx, row in self.excel_df.iterrows():
            model = row.iloc[0].strip()
            if not model:
                continue
            self.excel_data_display.append(f'型号: {model}')
            for col_name in self.excel_df.columns[1:]:
                val = row[col_name].strip()
                self.excel_data_display.append(f'  {col_name}: {val}')
            self.excel_data_display.append('')
        
        self.table_position_status.setText(f"Excel文件已加载，共 {len(self.excel_df)} 行数据")
        
        # 如果有JSON数据，可以用于表格插入
        if self.json_data_for_table is None and len(self.excel_df) > 0:
            # 将Excel数据转换为JSON格式
            json_data = []
            for _, row in self.excel_df.iterrows():
                row_dict = {}
                for col in self.excel_df.columns:
                    row_dict[col] = row[col]
                json_data.append(row_dict)
            
            self.json_data_for_table = json_data
            self.data_status_label.setText(f"当前有 {len(json_data)} 条表格数据可用（来自Excel，仅用于参数填充功能）")
            # QMessageBox.information(self, "注意", "Excel数据已加载，但请注意，表格插入功能仍需要使用文档分析标签页提取的表格数据。Excel数据仅用于参数填充功能。")
        else:
            self.data_status_label.setText(f"当前有 {len(self.excel_df)} 条Excel数据可用（仅用于参数填充功能）")
    
    def insert_paragraph_after(self, paragraph, text='', style=None):
        """在指定段落后插入新段落"""
        from docx.oxml import OxmlElement
        from docx.text.paragraph import Paragraph
        
        new_p = OxmlElement('w:p')
        paragraph._p.addnext(new_p)
        new_para = Paragraph(new_p, paragraph._parent)
        if text:
            new_para.add_run(text)
        if style:
            new_para.style = style
        return new_para

    def insert_into_word(self, add_missing_params=False, file_path=None):
        """将Excel数据插入到Word文档中"""
        if self.excel_df is None:
            QMessageBox.warning(self, '提示', '请先上传并提取Excel内容')
            return
        
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(self, '选择已有Word文档', '', '所有文件 (*.*);;Word Document (*.docx)')
            if not file_path:
                return
        
        try:
            doc = DocxDocument(file_path)
            paras = doc.paragraphs
            models = self.excel_df.iloc[:, 0].astype(str).str.strip().tolist()
            param_names = list(self.excel_df.columns[1:])
            placeholder = "填充"
            idx = 0
            
            while idx < len(paras):
                para_text = paras[idx].text.strip()
                current_model = None
                
                for model in models:
                    if model in para_text:
                        current_model = model
                        break
                
                if current_model:
                    data_row = self.excel_df[self.excel_df.iloc[:, 0].astype(str).str.strip() == current_model]
                    if data_row.empty:
                        idx += 1
                        continue
                    data_row = data_row.iloc[0]
                    desc_start_idx = idx
                    desc_end_idx = len(paras)
                    
                    # 找到当前模型描述结束位置
                    for j in range(idx + 1, len(paras)):
                        para_j_text = paras[j].text.strip()
                        for other_model in models:
                            if other_model != current_model and other_model in para_j_text:
                                desc_end_idx = j
                                break
                        if desc_end_idx != len(paras):
                            break
                    
                    found_params = set()
                    last_filled_para = None  # 记录最后一个实际填充的段落对象
                    
                    for desc_idx in range(desc_start_idx, desc_end_idx):
                        p_text = paras[desc_idx].text
                        for param in param_names:
                            if param in p_text:
                                param_pos = p_text.find(param)
                                after_param = p_text[param_pos + len(param):]
                                check_length = min(3, len(after_param))
                                check_text = after_param[:check_length]
                                has_placeholder = placeholder in check_text
                                if has_placeholder:
                                    found_params.add(param)
                                    value = str(data_row[param])
                                    if after_param.startswith('：') or after_param.startswith(':'):
                                        colon = '：' if after_param.startswith('：') else ':'
                                        before_colon = p_text[:param_pos + len(param) + 1]
                                        new_text = before_colon + value
                                        paras[desc_idx].text = new_text
                                    else:
                                        new_text = p_text[:param_pos + len(param)] + value
                                        paras[desc_idx].text = new_text
                                    last_filled_para = paras[desc_idx]  # 更新插入参考位置
                    
                    if add_missing_params:
                        missing_params = set(param_names) - found_params
                        if missing_params:
                            insert_after_para = last_filled_para if last_filled_para else paras[desc_end_idx - 1]
                            for mp in missing_params:
                                value = str(data_row[mp])
                                insert_after_para = self.insert_paragraph_after(insert_after_para, f"{mp}：{value}")
                    
                    idx = desc_end_idx
                else:
                    idx += 1
            
            save_path, _ = QFileDialog.getSaveFileName(self, '另存为新Word文档', f"填充后_{os.path.basename(file_path)}", 'Word Document (*.docx)')
            if not save_path:
                return
            doc.save(save_path)
            QMessageBox.information(self, '成功', 'Word文档填充完成并已保存！')
        
        except Exception as e:
            QMessageBox.critical(self, '错误', f'填充Word失败：{str(e)}')
            
    def set_json_data(self, data):
        """设置JSON数据"""
        self.json_data_for_table = data
        if data and isinstance(data, list) and len(data) > 0:
            self.data_status_label.setText(f"当前有 {len(data)} 条表格数据可用")
        else:
            self.data_status_label.setText("无可用的表格数据")
    
    def set_extracted_text(self, text):
        """设置提取的文本内容"""
        self.extracted_text_content = text
    
    def set_current_model(self, model_name):
        """设置当前使用的模型"""
        self.current_selected_model = model_name
    
    def smart_insert_table_to_word(self):
        """智能表格插入 - 使用大模型确定位置并插入表格"""
        # 检查是否有文档解析数据
        if not self.extracted_text_content:
            QMessageBox.warning(self, "提示", "使用智能定位需要先在文档分析标签页上传并解析文档")
            return
            
        # 检查是否有表格数据
        if not self.json_data_for_table:
            QMessageBox.warning(self, "数据错误", "没有可用的表格数据。请先在文档分析标签页使用API提取文档中的表格数据。")
            return
            
        # 设置API正在运行标志
        self.is_api_running = True
        
        # 更改按钮文本为停止
        self.btn_insert_table.setText("⏹️ 停止API调用")
        
        # 提示用户正在处理，并显示加载动画
        self.table_position_status.setText(f"正在调用大模型确定表格插入位置（使用模型：{self.current_selected_model}）...")
        if self.loading_movie.isValid():
            self.loading_label.show()
            self.loading_movie.start()
        else:
            self.loading_label.setText("处理中...")
            self.loading_label.show()
        
        # 获取提示词
        position_prompt = self.table_position_prompt.toPlainText()
        
        # 调用API确定位置
        system_prompt = """你是一个文档分析助手，负责确定在Word文档中插入表格的最佳位置。
根据用户提供的文档内容，找出最适合插入财务数据表格的位置关键词。
你的回复应该只包含一个简单的关键词或短语，例如"财务概况"、"公司业绩"等。
不要添加任何解释、格式或额外的文字，只返回这个关键词或短语。"""
        
        # 清理之前的worker（如果存在）
        if self.api_worker is not None:
            try:
                self.api_worker.finished.disconnect()
                self.api_worker.status_update.disconnect()
                self.api_worker = None
            except:
                pass
        
        # 创建并保存worker引用
        self.api_worker = OllamaApiWorker(system_prompt, f"文档内容：\n{self.extracted_text_content}\n\n{position_prompt}", self.current_selected_model)
        self.api_worker.finished.connect(self.on_table_position_api_finished)
        self.api_worker.status_update.connect(lambda status: self.table_position_status.setText(f"状态：{status}"))
        self.api_worker.start()
    
    @Slot(str, str)
    def on_table_position_api_finished(self, cleaned_output, raw_output):
        """处理表格位置API返回结果"""
        # 重置API运行状态
        self.is_api_running = False
        
        # 恢复按钮文本
        if self.current_insert_mode == "smart":
            self.btn_insert_table.setText('📊 智能插入表格到Word（使用大模型）')
        else:
            self.btn_insert_table.setText('📊 直接插入表格到Word（使用占位符）')
        
        # 停止加载动画
        if self.loading_movie.isValid():
            self.loading_movie.stop()
        self.loading_label.hide()
        
        # 拦截来自 worker 的错误消息，直接提示并阻断解析
        if cleaned_output.startswith("错误：") or cleaned_output.startswith("连接错误") or cleaned_output.startswith("HTTP 错误") or cleaned_output.startswith("请求错误") or cleaned_output.startswith("发生未知错误"):
            QMessageBox.critical(self, "API 请求失败", cleaned_output)
            self.table_position_status.setText("API 调用失败。")
            return
            
        # 清理API输出，获取简单的关键词或短语
        import re
        position_keyword = cleaned_output.strip()
        # 移除可能的JSON格式和引号
        position_keyword = re.sub(r'^\s*[\[\{\"\']|[\]\}\"\']$\s*', '', position_keyword)
        
        self.table_position_status.setText(f"确定的表格插入位置关键词: {position_keyword}")
        
        # 清理worker引用
        if self.api_worker is not None:
            try:
                self.api_worker.finished.disconnect()
                self.api_worker.status_update.disconnect()
                self.api_worker = None
            except:
                pass
        
        # 调用实际的表格插入功能
        self.insert_table_at_position(position_keyword)
    
    def insert_table_at_position(self, position_keyword):
        """在确定的位置插入表格"""
        if not self.word_file_path or not os.path.exists(self.word_file_path):
            QMessageBox.warning(self, "文件错误", "Word文档路径无效，请重新选择文档")
            return
        
        if not self.json_data_for_table:
            QMessageBox.warning(self, "数据错误", "没有可用的表格数据")
            return
        
        try:
            # 显示加载动画
            self.table_position_status.setText("正在插入表格...")
            if self.loading_movie.isValid():
                self.loading_label.show()
                self.loading_movie.start()
            else:
                self.loading_label.setText("处理中...")
                self.loading_label.show()
            
            doc = DocxDocument(self.word_file_path)
            
            # 提取表格数据和表头
            data = self.json_data_for_table
            all_keys = []
            for item in data:
                for key in item.keys():
                    if key not in all_keys:
                        all_keys.append(key)
            headers = all_keys
            
            # 查找插入位置
            target_para = None
            table_placeholder = "Table_In"
            
            # 首先查找包含position_keyword和Table_In的段落
            for i, para in enumerate(doc.paragraphs):
                para_text = para.text.strip()
                if position_keyword.lower() in para_text.lower():
                    # 检查当前段落或下一段落是否包含Table_In
                    if table_placeholder in para_text:
                        target_para = para
                        break
                    elif i + 1 < len(doc.paragraphs) and table_placeholder in doc.paragraphs[i + 1].text:
                        target_para = doc.paragraphs[i + 1]
                        break
            
            # 如果没找到带Table_In的位置，则找最接近position_keyword的段落
            if not target_para:
                for i, para in enumerate(doc.paragraphs):
                    para_text = para.text.strip()
                    if position_keyword.lower() in para_text.lower():
                        # 在关键词后面添加一个新段落用于表格
                        new_para = insert_paragraph_after(para, f"{table_placeholder}")
                        target_para = new_para
                        break
            
            # 如果仍然没找到位置，使用第一个非空段落
            if not target_para:
                for para in doc.paragraphs:
                    if para.text.strip():
                        # 在第一个非空段落后添加新段落
                        new_para = insert_paragraph_after(para, f"{position_keyword} {table_placeholder}")
                        target_para = new_para
                        break
            
            # 最后的备选方案：添加到文档末尾
            if not target_para:
                target_para = doc.add_paragraph(f"{position_keyword} {table_placeholder}")
            
            # 分割文本，得到插入表格前后的文字
            parts = target_para.text.split(table_placeholder)
            before = parts[0].strip()
            after = parts[1].strip() if len(parts) > 1 else ""
            
            # 清空段落，重写文字（插入表格前后的文字）
            target_para.clear()
            if before:
                target_para.add_run(before)
            
            # 插入表格，表格直接插入在target_para段落之后
            table = doc.add_table(rows=1, cols=len(headers))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True
            auto_fit_table_to_contents(table)
            
            # 添加表头
            hdr_cells = table.rows[0].cells
            for i, header in enumerate(headers):
                hdr_cells[i].text = header
                center_cell(hdr_cells[i])
            
            # 添加数据行
            for item in data:
                row_cells = table.add_row().cells
                for i, key in enumerate(headers):
                    row_cells[i].text = str(item.get(key, ''))
                    center_cell(row_cells[i])
            
            # 设置表格边框
            set_table_borders(table)
            
            # 将表格插入到段落后面（不是文档末尾）
            target_elm = target_para._p
            tbl_elm = table._tbl
            target_elm.addnext(tbl_elm)
            
            # 插入后段文字，表格后插入新段落
            if after:
                after_para = insert_paragraph_after(target_para, after)
            
            # 完成后隐藏加载动画
            if self.loading_movie.isValid():
                self.loading_movie.stop()
            self.loading_label.hide()
            
            # 保存文档
            save_path, _ = QFileDialog.getSaveFileName(self, '另存为新Word文档', f"表格已插入_{os.path.basename(self.word_file_path)}", 'Word Document (*.docx)')
            if not save_path:
                return
            
            doc.save(save_path)
            QMessageBox.information(self, '成功', '表格已成功插入并保存为新文档！')
            self.table_position_status.setText(f"表格已成功插入到位置: {position_keyword}")
            
        except Exception as e:
            # 发生错误时也隐藏加载动画
            if self.loading_movie.isValid():
                self.loading_movie.stop()
            self.loading_label.hide()
            
            QMessageBox.critical(self, '错误', f'插入表格失败：{str(e)}')
            self.table_position_status.setText(f"表格插入失败: {str(e)}")
    
    def insert_image_to_word(self):
        """插入图片到Word文档"""
        image_paths, _ = QFileDialog.getOpenFileNames(self, '选择图片文件（可多选）', '', '所有文件 (*.*);;Image files (*.jpg *.jpeg *.png *.bmp *.gif)')
        if not image_paths:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(self, '选择要插入图片的Word文档', '', '所有文件 (*.*);;Word Document (*.docx)')
        if not file_path:
            return
        
        try:
            from PIL import Image
            from docx.shared import Inches
            
            doc = DocxDocument(file_path)
            paras = doc.paragraphs
            image_placeholder = "Image_In"
            inserted_count = 0
            not_inserted_images = []
            
            for image_path in image_paths:
                image_filename = os.path.basename(image_path)
                image_name = os.path.splitext(image_filename)[0]
                image_inserted = False
                
                for i, para in enumerate(paras):
                    para_text = para.text.strip()
                    if image_name in para_text:
                        if image_placeholder in para_text:
                            placeholder_pos = para_text.find(image_placeholder)
                            text_before = para_text[:placeholder_pos]
                            text_after = para_text[placeholder_pos + len(image_placeholder):]
                            para.clear()
                            if text_before:
                                para.add_run(text_before)
                            
                            img = Image.open(image_path)
                            width, height = img.size
                            max_width_inches = 6.0
                            if width > height:
                                doc_width = Inches(max_width_inches)
                                doc_height = Inches(max_width_inches * height / width)
                            else:
                                max_height_inches = 4.0
                                doc_height = Inches(max_height_inches)
                                doc_width = Inches(max_height_inches * width / height)
                            
                            run = para.add_run()
                            run.add_picture(image_path, width=doc_width, height=doc_height)
                            
                            if text_after:
                                para.add_run(text_after)
                            
                            image_inserted = True
                            inserted_count += 1
                            break
                        elif i + 1 < len(paras) and image_placeholder in paras[i + 1].text.strip():
                            next_para = paras[i + 1]
                            next_para_text = next_para.text.strip()
                            placeholder_pos = next_para_text.find(image_placeholder)
                            text_before = next_para_text[:placeholder_pos]
                            text_after = next_para_text[placeholder_pos + len(image_placeholder):]
                            
                            next_para.clear()
                            if text_before:
                                next_para.add_run(text_before)
                            
                            img = Image.open(image_path)
                            width, height = img.size
                            max_width_inches = 6.0
                            if width > height:
                                doc_width = Inches(max_width_inches)
                                doc_height = Inches(max_width_inches * height / width)
                            else:
                                max_height_inches = 4.0
                                doc_height = Inches(max_height_inches)
                                doc_width = Inches(max_height_inches * width / height)
                            
                            run = next_para.add_run()
                            run.add_picture(image_path, width=doc_width, height=doc_height)
                            
                            if text_after:
                                next_para.add_run(text_after)
                            
                            image_inserted = True
                            inserted_count += 1
                            break
                
                if not image_inserted:
                    not_inserted_images.append(image_name)
            
            if inserted_count == 0:
                QMessageBox.information(self, '提示', f"未在文档中找到任何与所选图片名称匹配且当前行或下一行有'Image_In'占位符的位置，请检查图片名称或在Word文档中添加正确的占位符后重试")
                return
            
            save_path, _ = QFileDialog.getSaveFileName(self, '另存为新Word文档', f"图片已插入_{os.path.basename(file_path)}", 'Word Document (*.docx)')
            if not save_path:
                return
            
            doc.save(save_path)
            
            if not_inserted_images:
                QMessageBox.information(self, '部分成功', f"已成功插入{inserted_count}张图片并保存为新的Word文档！\n\n以下{len(not_inserted_images)}张图片未找到匹配位置：\n{', '.join(not_inserted_images)}")
            else:
                QMessageBox.information(self, '成功', f"已成功插入所有{inserted_count}张图片并保存为新的Word文档！")
        
        except Exception as e:
            QMessageBox.critical(self, '错误', f'插入图片失败：{str(e)}')
    
    def direct_insert_table_to_word(self):
        """直接插入表格到Word - 使用文档中预设的占位符"""
        # 检查是否有表格数据
        if not self.json_data_for_table:
            QMessageBox.warning(self, "数据错误", "没有可用的表格数据。请先在文档分析标签页使用API提取文档中的表格数据。")
            return
            
        # 获取用户输入的关键词
        base_name, ok = QInputDialog.getText(self, "输入关键词", 
                                           "请输入要查找的关键词（用于定位表格插入位置）：\n\n"
                                           "系统将查找包含此关键词且含有\"Table_In\"占位符的段落。\n\n"
                                           "注意：将插入从文档分析中提取的表格数据。")
        if not ok or not base_name.strip():
            return
            
        base_name = base_name.strip()
        
        # 提示用户正在处理，并显示加载动画
        self.table_position_status.setText(f"正在查找关键词\"{base_name}\"并插入文档分析提取的表格...")
        if self.loading_movie.isValid():
            self.loading_label.show()
            self.loading_movie.start()
        else:
            self.loading_label.setText("处理中...")
            self.loading_label.show()
        
        try:
            doc = DocxDocument(self.word_file_path)
            
            # 提取表格数据和表头
            data = self.json_data_for_table
            all_keys = []
            for item in data:
                for key in item.keys():
                    if key not in all_keys:
                        all_keys.append(key)
            headers = all_keys
            
            # 查找插入位置
            target_para = None
            table_placeholder = "Table_In"
            
            # 遍历段落查找包含base_name的段落，并且本段或下一段包含Table_In
            for i, para in enumerate(doc.paragraphs):
                para_text = para.text.strip()
                if base_name.lower() in para_text.lower():
                    # 检查当前段落是否包含Table_In
                    if table_placeholder in para_text:
                        target_para = para
                        break
                    # 检查下一段是否包含Table_In
                    elif i + 1 < len(doc.paragraphs) and table_placeholder in doc.paragraphs[i + 1].text:
                        target_para = doc.paragraphs[i + 1]
                        break
            
            if target_para is None:
                # 停止加载动画
                if self.loading_movie.isValid():
                    self.loading_movie.stop()
                self.loading_label.hide()
                
                QMessageBox.warning(self, "未找到位置", 
                                    f"未找到匹配关键词\"{base_name}\"且含有\"Table_In\"占位符的段落。\n\n"
                                    f"请确保文档中包含此关键词，并在相应位置添加\"Table_In\"作为表格插入点标记。")
                return
            
            # 分割文本，得到插入表格前后的文字
            parts = target_para.text.split(table_placeholder)
            before = parts[0].strip()
            after = parts[1].strip() if len(parts) > 1 else ""
            
            # 清空段落，重写文字（插入表格前后的文字）
            target_para.clear()
            if before:
                target_para.add_run(before)
            
            # 插入表格，表格直接插入在target_para段落之后
            table = doc.add_table(rows=1, cols=len(headers))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True
            auto_fit_table_to_contents(table)
            
            # 添加表头
            hdr_cells = table.rows[0].cells
            for i, header in enumerate(headers):
                hdr_cells[i].text = header
                center_cell(hdr_cells[i])
            
            # 添加数据行
            for item in data:
                row_cells = table.add_row().cells
                for i, key in enumerate(headers):
                    row_cells[i].text = str(item.get(key, ''))
                    center_cell(row_cells[i])
            
            # 设置表格边框
            set_table_borders(table)
            
            # 将表格插入到段落后面（不是文档末尾）
            target_elm = target_para._p
            tbl_elm = table._tbl
            target_elm.addnext(tbl_elm)
            
            # 插入后段文字，表格后插入新段落
            if after:
                after_para = insert_paragraph_after(target_para, after)
            
            # 完成后隐藏加载动画
            if self.loading_movie.isValid():
                self.loading_movie.stop()
            self.loading_label.hide()
            
            # 保存文档
            save_path, _ = QFileDialog.getSaveFileName(self, '另存为新Word文档', f"表格已插入_{os.path.basename(self.word_file_path)}", 'Word Document (*.docx)')
            if not save_path:
                return
            
            doc.save(save_path)
            QMessageBox.information(self, '成功', '表格已成功插入并保存为新文档！')
            self.table_position_status.setText(f"表格已成功插入到位置: 关键词\"{base_name}\"")
            
        except Exception as e:
            # 发生错误时也隐藏加载动画
            if self.loading_movie.isValid():
                self.loading_movie.stop()
            self.loading_label.hide()
            
            QMessageBox.critical(self, '错误', f'插入表格失败：{str(e)}')
            self.table_position_status.setText(f"表格插入失败: {str(e)}")
    
    def stop_api_call(self):
        """停止当前的API调用"""
        if self.api_worker is not None and self.is_api_running:
            try:
                # 终止线程
                self.api_worker.terminate()
                self.api_worker.wait(1000)  # 等待最多1秒
                
                # 清理连接
                self.api_worker.finished.disconnect()
                self.api_worker.status_update.disconnect()
                self.api_worker = None
                
                # 更新UI
                if self.loading_movie.isValid():
                    self.loading_movie.stop()
                self.loading_label.hide()
                
                self.table_position_status.setText("API调用已取消")
                
                # 重置状态和按钮
                self.is_api_running = False
                if self.current_insert_mode == "smart":
                    self.btn_insert_table.setText('📊 智能插入表格到Word（使用大模型）')
                else:
                    self.btn_insert_table.setText('📊 直接插入表格到Word（使用占位符）')
            except Exception as e:
                print(f"停止API调用时出错: {e}")
    
    def closeEvent(self, event):
        """重写关闭事件，确保清理所有线程"""
        # 清理API线程（如果存在）
        if hasattr(self, 'api_worker') and self.api_worker is not None:
            try:
                self.api_worker.terminate()
                self.api_worker = None
            except:
                pass
        super().closeEvent(event)

    def show_table_insert_menu(self):
        """显示表格插入模式菜单"""
        # 计算菜单位置
        button_pos = self.btn_table_dropdown.mapToGlobal(self.btn_table_dropdown.rect().bottomLeft())
        # 显示菜单
        self.table_insert_menu.exec_(button_pos)
    
    def change_insert_mode(self, mode):
        """更改插入模式"""
        self.current_insert_mode = mode
        if mode == "smart":
            self.btn_insert_table.setText('📊 智能插入表格到Word（使用大模型）')
        else:
            self.btn_insert_table.setText('📊 直接插入表格到Word（使用占位符）')
    
    def on_insert_button_clicked(self):
        """处理插入按钮点击事件"""
        # 如果API正在运行，则停止它
        if self.is_api_running:
            self.stop_api_call()
            return
            
        # 检查是否有JSON数据
        if not self.json_data_for_table or not isinstance(self.json_data_for_table, list) or len(self.json_data_for_table) == 0:
            QMessageBox.warning(self, "数据错误", "无法获取表格数据。请先在文档分析标签页使用API提取文档中的表格数据。")
            return
            
        # 如果选择智能定位，需要检查是否有文档解析数据
        if self.current_insert_mode == "smart" and not self.extracted_text_content:
            QMessageBox.warning(self, "提示", "使用智能定位需要先在文档分析标签页上传并解析文档")
            return
        
        # 选择Word文档
        file_path, _ = QFileDialog.getOpenFileName(self, '选择要插入表格的Word文档', '', '所有文件 (*.*);;Word Document (*.docx)')
        if not file_path:
            return
            
        # 保存文件路径
        self.word_file_path = file_path
        
        # 根据模式调用相应的插入方法
        if self.current_insert_mode == "smart":
            self.smart_insert_table_to_word()
        else:  # 手动定位（使用占位符）
            self.direct_insert_table_to_word()
    
    def show_fill_menu(self):
        """显示填充模式菜单"""
        # 计算菜单位置
        button_pos = self.btn_fill_dropdown.mapToGlobal(self.btn_fill_dropdown.rect().bottomLeft())
        # 显示菜单
        self.fill_menu.exec_(button_pos)
    
    def change_fill_mode(self, mode):
        """更改填充模式"""
        self.fill_mode = mode
        if mode == "only_existing":
            self.btn_fill_word.setText('📝 填充Word文档（仅填充已有参数）')
        else:
            self.btn_fill_word.setText('📝 填充Word文档（添加缺失参数）')
    
    def on_fill_button_clicked(self):
        """处理填充按钮点击事件"""
        if self.excel_df is None:
            QMessageBox.warning(self, '提示', '请先上传并提取Excel内容')
            return
        
        file_path, _ = QFileDialog.getOpenFileName(self, '选择已有Word文档', '', '所有文件 (*.*);;Word Document (*.docx)')
        if not file_path:
            return
        
        # 根据填充模式调用insert_into_word方法
        add_missing_params = (self.fill_mode == "add_missing")
        self.insert_into_word(add_missing_params, file_path) 