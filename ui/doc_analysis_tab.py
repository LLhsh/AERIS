from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, QTextEdit,
    QComboBox, QSizePolicy, QFileDialog, QMessageBox
)
from PySide2.QtCore import Qt, Signal, Slot, QSize, QSettings
from PySide2.QtGui import QMovie, QFocusEvent
import traceback

import os
import sys
import json
import xml.etree.ElementTree as ET

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 添加Code目录到系统路径以导入data模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from workers.api_worker import OllamaApiWorker
from workers.file_worker import FileParseWorker
from utils.xml_utils import clean_xml_output, convert_simple_xml_to_xmi, parse_xmi_to_tree_data, load_xml_file, save_xmi_file, convert_xmi_to_simple_xml, smart_chunk_text
from data.xml_to_reqif_converter import XMLToReqIFConverter
from batch_processing.batch_processor import BatchProcessor

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """
# 任务：提取火箭发动机数据并构建三级目录

请严格按照以下 4 条规则，处理用户提供的文档：

1. 锁定范围：仅提取【第五章】的内容，绝对忽略其他所有章节的任何信息。
2. 三级目录结构：请将提取的内容梳理成严格的三级目录结构：
   - 一级标题：大分类（如：1. 发动机总体指标）
   - 二级标题：子系统或需求类型（如：1.1 功能需求、1.2 性能需求）
   - 三级标题：具体的指标名称（如：1.1.1 推进剂、1.1.2 液体火箭发动机）
3. 描述提取规则：**只有三级标题需要附带详细描述**。请将该指标的数值、单位、测试工况融合成一句完整的话。一级和二级标题仅作为目录，不能有描述。
4. 归纳整理：如果原文零散，请根据发动机行业常识进行归类合并，不要遗漏任何量化数据。

请现在输出整理好的三级目录草稿。
"""

# JSON格式系统提示词
INTERNAL_BASE_PROMPT_JSON = """
请确保你的输出严格遵守以下要求：

1. 零废话原则：不要输出任何思考过程、分析步骤或解释性文字。
2. 纯净 JSON 数组：严格按照 JSON 格式输出，JSON 应为一个对象数组 `[{...}, {...}]`，其中每个对象代表表格的一行。不要在 JSON 前后添加任何 Markdown 标记（如 ```json ）或开场白。
3. 字段结构规范：每个对象必须包含以下明确的键（列名），如果没有相关信息则填入 `null`：
   - "entity": 关联的实体/组件名称（如：全箭、推力室、燃气发生器）
   - "category": 归纳后的指标大类（如：总体性能、尺寸质量）
   - "parameter_name": 原始或标准化后的指标名称（如：真空推力、室压）
   - "value": 指标的数值（必须使用标准 JSON 数字类型；如果是区间或带有特殊字符，则转为字符串）
   - "unit": 物理单位（如：kN, MPa, kg/s, s，无单位填 null）
   - "conditions": 工作或测试条件（如：海平面、额定工况，无条件填 null）
4. 格式严谨性：字符串值必须用双引号包围，不能包含未转义的特殊字符。确保输出是完全合法的 JSON。
"""

# XML格式系统提示词
INTERNAL_BASE_PROMPT_XML = """
# 任务：将整理好的数据转换为严格的 XML 格式

请将刚刚整理的三级目录数据，严格按照以下要求输出为 XML 代码：

1. 零废话原则：不要输出任何确认语、思考过程或解释。第一行必须直接是 `<?xml version="1.0" encoding="UTF-8"?>`。
2. 标签规范：根节点必须为 `<requirements>`。内部所有的一级、二级、三级目录，**标签名统一全都是 `<requirement>`**，并通过代码嵌套来体现父子级关系。
3. 属性规范：每个 `<requirement>` 标签必须且只能有 3 个属性：
   - `id`：顶级类目从 Sr_1 开始，下级继承父级，如 Sr_1.1，Sr_1.1.1。
   - `name`：只填标题名称（如“功能需求”或“真空推力”）。
   - `text`：详细描述。**一级和二级节点起归类作用，text 必须留空（text=""）。只有三级节点填写具体的描述句子**。

# 强制输出格式示例（必须照此嵌套）：
<?xml version="1.0" encoding="UTF-8"?>
<requirements>
    <requirement id="Sr_1" name="发动机总体指标" text="">
        <requirement id="Sr_1.1" name="功能需求" text="">
            <requirement id="Sr_1.1.1" name="推进剂" text="采用液氧煤油，常温下测试。" />
            <requirement id="Sr_1.1.2" name="启动方式" text="采用自身火药启动器。" />
        </requirement>
        <requirement id="Sr_1.2" name="性能需求" text="">
            <requirement id="Sr_1.2.1" name="真空推力" text="设计数值为1200，单位kN，额定工况下测得。" />
        </requirement>
    </requirement>
</requirements>
"""
class DocAnalysisTab(QWidget):
    """文档分析标签页
    
    支持两种输出格式：
    - JSON：表格数据提取
    - XML：需求建模（自动转换为XMI格式）
    
    导出功能：
    - 导出XML：XMI格式（用于建模工具）
    - 导出REQIF：ReqIF格式（用于需求管理工具）
    """
    # 定义信号，用于向主窗口传递数据
    data_ready = Signal(str, object, list)  # 传递(格式类型, 数据, 列顺序/None)
    extracted_text_ready = Signal(str)  # 传递提取的文本内容
    api_text_ready = Signal(str, str)  # 传递(raw_output, cleaned_output)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extracted_text_content = ""
        self.selected_file_path = ""
        self.user_prompt_placeholder_text = "例如：请提取文档中所有关于市场份额的数据，并与其他相关数据对比。"
        self.user_prompt_is_placeholder = True
        self.current_selected_model = "deepseek-r1:70b"  # 默认模型
        self.output_format = "XML"  # 默认输出格式
        
        self.raw_api_output = ""
        self.cleaned_api_output = ""
        self.json_data = None
        self.current_xmi_output = ""  # 存储转换后的XMI输出
        self.current_simple_xml = ""  # 存储简单XML格式（用于REQIF转换）
        self.is_api_running = False  # API是否正在运行的标志
        self.api_worker = None
        self.file_parse_worker = None
        
        self.settings = QSettings()
        
        # 初始化批量处理器
        self.batch_processor = BatchProcessor(self)
        self.batch_processor.progress_update.connect(self.on_batch_progress)
        self.batch_processor.status_update.connect(self.on_batch_status)
        self.batch_processor.finished.connect(self.on_batch_finished)
        self.batch_processor.error_occurred.connect(self.on_batch_error)
        self.batch_processor.chunk_result_ready.connect(self.on_batch_chunk_result)
        self.batch_processor.chunk_error.connect(self.on_batch_chunk_error)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # 文件选择区域
        file_button_layout = QHBoxLayout()
        self.upload_button = QPushButton("📁 上传文档")
        self.upload_button.clicked.connect(self.select_and_parse_file)
        file_button_layout.addWidget(self.upload_button)
        
        # 导入XML按钮
        self.import_xml_button = QPushButton("📥 导入XML")
        self.import_xml_button.clicked.connect(self.import_xml_file)
        file_button_layout.addWidget(self.import_xml_button)
        
        self.clear_file_button = QPushButton("🗑️ 清除文件")
        self.clear_file_button.clicked.connect(self.clear_content)
        self.clear_file_button.setEnabled(False)
        file_button_layout.addWidget(self.clear_file_button)
        layout.addLayout(file_button_layout)
        
        # 文件信息标签
        self.file_label = QLabel("未选择文件")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setWordWrap(True)
        self.file_label.setFixedHeight(45)
        layout.addWidget(self.file_label)
        
        # 配置区域 (使用网格布局保证整齐)
        config_layout = QGridLayout()
        config_layout.setSpacing(10)
        
        # 第一行：模型选择
        model_label = QLabel("选择模型:")
        model_label.setFixedWidth(60)
        config_layout.addWidget(model_label, 0, 0)
        
        self.model_selection_combobox = QComboBox()
        self.model_selection_combobox.setToolTip("请从列表中选择模型")
        self.model_selection_combobox.setMinimumWidth(200)
        self.model_selection_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_layout.addWidget(self.model_selection_combobox, 0, 1)
        
        # 将按钮放置在下拉列表下方的同一列
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        small_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #2196F3;
                border: 1px solid #2196F3;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
                font-weight: normal;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #E3F2FD;
            }
        """
        self.btn_add_model = QPushButton("➕ 添加模型")
        self.btn_add_model.setStyleSheet(small_btn_style)
        self.btn_add_model.clicked.connect(self.add_custom_model)
        
        self.btn_delete_model = QPushButton("🗑️ 删除模型")
        self.btn_delete_model.setStyleSheet(small_btn_style)
        self.btn_delete_model.clicked.connect(self.delete_custom_model)
        
        btn_layout.addWidget(self.btn_add_model)
        btn_layout.addWidget(self.btn_delete_model)
        btn_layout.addStretch()
        config_layout.addLayout(btn_layout, 1, 1)
        
        # 第三行：输出格式选择
        format_label = QLabel("输出格式:")
        format_label.setFixedWidth(60)
        config_layout.addWidget(format_label, 2, 0)
        
        self.format_selection_combobox = QComboBox()
        self.format_selection_combobox.addItems(["JSON", "XML"])
        self.format_selection_combobox.setCurrentText(self.output_format)
        self.format_selection_combobox.currentTextChanged.connect(self.on_format_changed)
        self.format_selection_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_layout.addWidget(self.format_selection_combobox, 2, 1)
        
        layout.addLayout(config_layout)
        
        # 系统提示词区域
        layout.addWidget(QLabel("系统提示词:"))
        self.system_prompt_textbox = QTextEdit()
        
        saved_system_prompt = self.settings.value("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.system_prompt_textbox.setPlainText(saved_system_prompt)
        self.system_prompt_textbox.textChanged.connect(self.save_system_prompt)
        self.system_prompt_textbox.setFixedHeight(200)
        layout.addWidget(self.system_prompt_textbox)
        
        # 用户提示词区域
        layout.addWidget(QLabel("用户自定义提示/问题:"))
        self.user_prompt_textbox = QTextEdit()
        self.user_prompt_textbox.setObjectName("userPromptTextEdit")
        self.user_prompt_textbox.setFixedHeight(150)
        self.user_prompt_textbox.setText(self.user_prompt_placeholder_text)
        self.user_prompt_textbox.setProperty("isPlaceholder", True)
        # 连接信号到槽函数
        self.user_prompt_textbox.textChanged.connect(self.on_user_prompt_text_changed)
        self.user_prompt_textbox.focusInEvent = self.on_user_prompt_focus_in
        self.user_prompt_textbox.focusOutEvent = self.on_user_prompt_focus_out
        layout.addWidget(self.user_prompt_textbox)
        
        # 发送按钮区域
        send_layout = QHBoxLayout()
        self.send_button = QPushButton("🚀 发送")
        self.send_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.send_button.clicked.connect(self.prepare_and_send_to_api)
        send_layout.addWidget(self.send_button)
        
        self.batch_button = QPushButton("⚡ 批量处理")
        self.batch_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.batch_button.clicked.connect(self.start_batch_processing)
        send_layout.addWidget(self.batch_button)
        
        # 加载动画
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
        send_layout.addWidget(self.loading_label)
        layout.addLayout(send_layout)
        
        # 导出按钮区域
        export_layout = QHBoxLayout()
        
        # 导出XMI按钮
        self.export_xmi_button = QPushButton("💾 导出XML")
        self.export_xmi_button.clicked.connect(self.export_xmi_file)
        self.export_xmi_button.setEnabled(False)
        export_layout.addWidget(self.export_xmi_button)
        
        # 导出REQIF按钮
        self.export_reqif_button = QPushButton("💾 导出REQIF")
        self.export_reqif_button.clicked.connect(self.export_reqif_file)
        self.export_reqif_button.setEnabled(False)
        export_layout.addWidget(self.export_reqif_button)
        
        # 合并XML按钮
        self.merge_xml_button = QPushButton("🔀 合并XML")
        self.merge_xml_button.clicked.connect(self.process_data)
        export_layout.addWidget(self.merge_xml_button)
        
        layout.addLayout(export_layout)
        
        # 状态标签
        self.status_label = QLabel("状态：就绪")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        
    def select_and_parse_file(self):
        """选择并解析文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", "所有文件 (*.*);;PDF 文件 (*.pdf);;Word 文档 (*.docx)"
        )
        if file_path:
            self.selected_file_path = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.status_label.setText(f"解析文件: {os.path.basename(file_path)}...")
            self.send_button.setEnabled(False)
            
            if self.loading_movie.isValid():
                self.loading_label.show()
                self.loading_movie.start()
            else:
                self.loading_label.setText("处理中...")
                self.loading_label.show()
            
            if self.file_parse_worker is not None:
                try:
                    self.file_parse_worker.wait()
                except Exception:
                    pass
                self.file_parse_worker = None
                
            self.file_parse_worker = FileParseWorker(file_path)
            self.file_parse_worker.finished.connect(self.on_file_parse_finished)
            self.file_parse_worker.start()
        else:
            self.file_label.setText("未选择文件")
            self.status_label.setText(f"文件选择已取消。")
    
    @Slot(str, str)
    def on_file_parse_finished(self, file_path_processed, result):
        """文件解析完成回调"""
        self.send_button.setEnabled(True)
        if self.loading_movie.isValid():
            self.loading_movie.stop()
        self.loading_label.hide()
        
        if file_path_processed != self.selected_file_path:  # 过时的任务
            return
        
        if result.startswith("错误:") or result.startswith("警告:"):
            self.extracted_text_content = ""
            self.status_label.setText(f"文件处理失败: {os.path.basename(file_path_processed)}")
            self.clear_file_button.setEnabled(False)
            QMessageBox.warning(self, "文件处理问题", result)
            # 发出信号，传递空文本
            self.extracted_text_ready.emit("")
        else:
            self.extracted_text_content = result
            self.status_label.setText(f"文件解析完成: {os.path.basename(file_path_processed)}. 当前模型: {self.current_selected_model}")
            self.clear_file_button.setEnabled(bool(self.extracted_text_content.strip()))
            # 发出信号，传递提取的文本
            self.extracted_text_ready.emit(self.extracted_text_content)
    
    def prepare_and_send_to_api(self):
        """准备并发送API请求"""
        # 如果API正在运行，则停止它
        if self.is_api_running:
            self.stop_api_call()
            return
            
        if not self.current_selected_model:
            QMessageBox.critical(self, "模型未选择", "请先在下拉列表中选择一个Ollama模型。")
            return
        
        user_visible_system_prompt = self.system_prompt_textbox.toPlainText().strip()
        user_custom_prompt_raw = self.user_prompt_textbox.toPlainText().strip()
        user_custom_prompt = ""
        if not self.user_prompt_is_placeholder:
            user_custom_prompt = user_custom_prompt_raw
        
        doc_text_available = bool(self.extracted_text_content and self.extracted_text_content.strip())
        user_prompt_available = bool(user_custom_prompt)
        
        # 根据输出格式选择对应的系统提示词
        json_internal_prompt = str(self.settings.value("internal_prompt_json", INTERNAL_BASE_PROMPT_JSON))
        xml_internal_prompt = str(self.settings.value("internal_prompt_xml", INTERNAL_BASE_PROMPT_XML))

        if self.output_format == "JSON":
            final_system_prompt = json_internal_prompt + \
                                  "\n\n---\n用户附加指令 (请严格遵守以下格式化要求):\n---\n" + \
                                  user_visible_system_prompt
        else:  # XML
            final_system_prompt = xml_internal_prompt + \
                                  "\n\n---\n用户附加指令 (请严格遵守以下格式化要求):\n---\n" + \
                                  user_visible_system_prompt
        user_content_for_api = ""
        
        if doc_text_available and user_prompt_available:
            user_content_for_api = f"## 文档内容摘要:\n{self.extracted_text_content.strip()}\n\n## 用户具体请求:\n{user_custom_prompt}"
        elif doc_text_available:
            user_content_for_api = f"## 文档内容摘要:\n{self.extracted_text_content.strip()}\n\n## 指令:\n请根据系统角色和用户附加指令处理上述文档内容。"
        elif user_prompt_available:
            user_content_for_api = f"## 用户具体请求:\n{user_custom_prompt}\n\n## 指令:\n请根据系统角色和用户附加指令处理此请求。"
        
        # 设置API运行状态并更新按钮
        self.is_api_running = True
        self.send_button.setText("⏹️ 停止")
        self.send_button.setEnabled(True)
        
        if self.loading_movie.isValid():
            self.loading_label.show()
            self.loading_movie.start()
        else:
            self.loading_label.setText("请求中...")
            self.loading_label.show()
        
        if self.api_worker is not None:
            try:
                self.api_worker.wait()
            except Exception:
                pass
            self.api_worker = None
            
        self.api_worker = OllamaApiWorker(final_system_prompt, user_content_for_api, self.current_selected_model)
        self.api_worker.finished.connect(self.on_api_finished)
        self.api_worker.status_update.connect(lambda text: self.status_label.setText(f"状态：{text}"))
        self.api_worker.start()
    
    @Slot(str, str)
    def on_api_finished(self, cleaned_output, raw_model_text):
        """API调用完成回调"""
        # 重置API运行状态和按钮
        self.is_api_running = False
        self.send_button.setText("🚀 发送")
        self.send_button.setEnabled(True)
        
        if self.loading_movie.isValid():
            self.loading_movie.stop()
        self.loading_label.hide()
        
        self.raw_api_output = raw_model_text
        self.cleaned_api_output = cleaned_output
        self.api_text_ready.emit(self.raw_api_output, self.cleaned_api_output)
        
        # 拦截来自 worker 的错误消息，直接提示并阻断解析
        if cleaned_output.startswith("错误：") or cleaned_output.startswith("连接错误") or cleaned_output.startswith("HTTP 错误") or cleaned_output.startswith("请求错误") or cleaned_output.startswith("发生未知错误"):
            QMessageBox.critical(self, "API 请求失败", cleaned_output)
            self.status_label.setText("API 调用失败。")
            return
        
        try:
            if self.output_format == "JSON":
                # JSON格式处理
                data = json.loads(cleaned_output)
                
                # 验证数据结构
                if not isinstance(data, list) or (data and not all(isinstance(item, dict) for item in data)):
                    if isinstance(data, dict) and len(data) > 0:
                        data = [data]
                    else:
                        raise ValueError("JSON顶层结构应为对象列表。")
                
                # 提取字段顺序信息
                column_order = []
                if data and len(data) > 0:
                    first_item_keys = list(data[0].keys())
                    column_order = first_item_keys.copy()
                    
                    for item in data:
                        for key in item.keys():
                            if key not in column_order:
                                column_order.append(key)
                
                # 发出信号，传递JSON数据
                self.data_ready.emit("JSON", data, column_order)
                self.status_label.setText("API 调用成功，JSON数据已处理完成。")
                
            else:  # XML格式处理
                # 清理XML输出（移除思考标签等）
                cleaned_xml = clean_xml_output(cleaned_output)
                
                # 转换为XMI格式
                xmi_output = convert_simple_xml_to_xmi(cleaned_xml)
                self.current_xmi_output = xmi_output
                self.current_simple_xml = cleaned_xml
                
                # 解析XMI为树状数据
                tree_data = parse_xmi_to_tree_data(xmi_output)
                
                # 发出信号，传递XMI树状数据
                self.data_ready.emit("XML", tree_data, [])
                self.status_label.setText("API 调用成功，XML数据已转换为XMI格式。")
                
                # 启用导出按钮
                self.export_xmi_button.setEnabled(True)
                self.export_reqif_button.setEnabled(True)
                
        except json.JSONDecodeError as e:
            cleaned_preview = (cleaned_output or "")[:1200]
            raw_preview = (raw_model_text or "")[:1200]
            if self.output_format == "JSON":
                QMessageBox.critical(
                    self,
                    "JSON解析错误",
                    "API返回的不是有效JSON。\n"
                    f"错误位置: line {e.lineno}, col {e.colno}\n"
                    f"错误信息: {e.msg}\n\n"
                    f"清洗后内容预览:\n{cleaned_preview}\n\n"
                    f"原始模型输出预览:\n{raw_preview}"
                )
                self.status_label.setText("JSON解析错误。")
            else:
                QMessageBox.critical(self, "处理错误", f"处理API结果时出错: {str(e)}。\n\n内容预览:\n{cleaned_preview}")
                self.status_label.setText("处理API结果时出错。")
        except ValueError as e:
            cleaned_preview = (cleaned_output or "")[:1200]
            if self.output_format == "JSON":
                QMessageBox.warning(
                    self,
                    "JSON数据格式错误",
                    f"API返回的JSON结构不符合预期：{str(e)}。\n\n"
                    f"内容预览:\n{cleaned_preview}"
                )
                self.status_label.setText("JSON数据格式错误。")
            else:
                QMessageBox.warning(
                    self,
                    "XML数据格式错误",
                    f"API返回的XML结构不符合预期：{str(e)}。\n\n"
                    f"内容预览:\n{cleaned_preview}"
                )
                self.status_label.setText("XML数据格式错误。")
        except Exception as e:
            format_name = self.output_format
            cleaned_preview = (cleaned_output or "")[:1200]
            raw_preview = (raw_model_text or "")[:1200]
            QMessageBox.critical(
                self,
                "处理错误",
                f"处理{format_name} API结果时出错: {str(e)}。\n\n"
                f"清洗后内容预览:\n{cleaned_preview}\n\n"
                f"原始模型输出预览:\n{raw_preview}\n\n"
                f"堆栈:\n{traceback.format_exc()}"
            )
            self.status_label.setText(f"处理{format_name} API结果时出错。")
    
    def clear_content(self):
        """清除内容"""
        if self.batch_processor.is_running:
            self.batch_processor.stop()
            self.batch_button.setText("⚡ 批量处理")
            
        self.extracted_text_content = ""
        self.selected_file_path = ""
        self.file_label.setText("未选择文件")
        
        self.raw_api_output = ""
        self.cleaned_api_output = ""
        self.json_data = None
        self.current_xmi_output = ""
        self.current_simple_xml = ""
        
        # 发出信号，清除数据
        self.data_ready.emit(self.output_format, [], [])
        self.extracted_text_ready.emit("")
        
        self.clear_file_button.setEnabled(False)
        self.export_xmi_button.setEnabled(False)
        self.export_reqif_button.setEnabled(False)
        self.status_label.setText(f"状态：内容已清除。当前模型: {self.current_selected_model}")
    
    def set_models(self, models):
        """设置可用模型列表"""
        self.model_selection_combobox.clear()
        self.model_selection_combobox.addItems(models)
        if models and self.current_selected_model in models:
            self.model_selection_combobox.setCurrentText(self.current_selected_model)
        elif models:
            self.current_selected_model = models[0]
            self.model_selection_combobox.setCurrentText(self.current_selected_model)
        self.model_selection_combobox.currentTextChanged.connect(self.on_model_changed)
        
    def add_custom_model(self):
        """允许用户手动添加并持久化新模型"""
        from PySide2.QtWidgets import QInputDialog
        from PySide2.QtCore import QSettings
        
        model_name, ok = QInputDialog.getText(self, "添加模型", "请输入自定义大模型名称\n(如: gpt-4, deepseek-chat):")
        if ok and model_name.strip():
            model_name = model_name.strip()
            
            # 使用原生设置保存
            settings = QSettings()
            models = settings.value("custom_models", [])
            if not isinstance(models, list):
                models = [str(models)] if models else []
                
            if model_name not in models:
                models.append(model_name)
                settings.setValue("custom_models", models)
                
                # 更新 UI
                self.model_selection_combobox.addItem(model_name)
                self.model_selection_combobox.setCurrentText(model_name)
                QMessageBox.information(self, "成功", f"成功添加并持久化保存模型：{model_name}")
            else:
                QMessageBox.warning(self, "提示", "该模型已存在列表中！")
                self.model_selection_combobox.setCurrentText(model_name)

    def delete_custom_model(self):
        """删除当前选中的自定义模型"""
        current_model = self.model_selection_combobox.currentText()
        if not current_model:
            return
            
        from PySide2.QtCore import QSettings
        reply = QMessageBox.question(self, "确认删除", f"确定要从持久化列表中永久删除模型 '{current_model}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            settings = QSettings()
            models = settings.value("custom_models", [])
            if not isinstance(models, list):
                models = [str(models)] if models else []
                
            if current_model in models:
                models.remove(current_model)
                settings.setValue("custom_models", models)
                
            # 更新 UI 中的下拉选项
            index = self.model_selection_combobox.findText(current_model)
            if index >= 0:
                self.model_selection_combobox.removeItem(index)
                
            QMessageBox.information(self, "成功", f"模版 '{current_model}' 已删除。")
    
    @Slot(str)
    def on_model_changed(self, model_name):
        """模型变更回调"""
        if model_name:
            self.current_selected_model = model_name
            self.status_label.setText(f"状态：当前模型: {self.current_selected_model}")
    
    @Slot(str)
    def on_format_changed(self, format_type):
        """输出格式变更回调"""
        if format_type:
            self.output_format = format_type
            self.status_label.setText(f"状态：输出格式已切换为 {self.output_format}")
    
    def get_json_data(self):
        """获取JSON数据"""
        return self.json_data
    
    def get_extracted_text(self):
        """获取提取的文本内容"""
        return self.extracted_text_content

    def on_user_prompt_focus_in(self, event):
        """用户提示输入框获得焦点时的处理"""
        if self.user_prompt_is_placeholder:
            self.user_prompt_textbox.clear()
            self.user_prompt_textbox.setProperty("isPlaceholder", False)
            self.user_prompt_textbox.setStyleSheet("")  # 触发样式表重新应用
            self.user_prompt_is_placeholder = False
        # 调用原始的焦点事件处理
        QTextEdit.focusInEvent(self.user_prompt_textbox, event)
    
    def on_user_prompt_focus_out(self, event):
        """用户提示输入框失去焦点时的处理"""
        if not self.user_prompt_textbox.toPlainText().strip():
            self.user_prompt_textbox.setText(self.user_prompt_placeholder_text)
            self.user_prompt_textbox.setProperty("isPlaceholder", True)
            self.user_prompt_textbox.setStyleSheet("")  # 触发样式表重新应用
            self.user_prompt_is_placeholder = True
        # 调用原始的焦点事件处理
        QTextEdit.focusOutEvent(self.user_prompt_textbox, event)
    
    def save_system_prompt(self):
        """保存系统提示词到本地设置"""
        self.settings.setValue("system_prompt", self.system_prompt_textbox.toPlainText())

    def on_user_prompt_text_changed(self):
        """用户提示输入框文本变化时的处理"""
        if not self.user_prompt_is_placeholder:
            text = self.user_prompt_textbox.toPlainText().strip()
            if not text and not self.user_prompt_textbox.hasFocus():
                self.user_prompt_textbox.setText(self.user_prompt_placeholder_text)
                self.user_prompt_textbox.setProperty("isPlaceholder", True)
                self.user_prompt_textbox.setStyleSheet("")  # 触发样式表重新应用
                self.user_prompt_is_placeholder = True 

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
                
                self.status_label.setText("API调用已取消")
                
                # 重置状态和按钮
                self.is_api_running = False
                self.send_button.setText("🚀 发送")
                self.send_button.setEnabled(True)
            except Exception as e:
                print(f"停止API调用时出错: {e}")
    
    def import_xml_file(self):
        """导入XML文件并转换为XMI"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择XML文件", "", "XML 文件 (*.xml);;所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            # 加载XML内容
            xml_content = load_xml_file(file_path)
            
            if xml_content.startswith("错误:"):
                QMessageBox.critical(self, "加载失败", xml_content)
                return
            
            # 判断是简单XML还是XMI格式
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                QMessageBox.critical(self, "XML解析错误", f"无法解析XML文件: {e}")
                return
            
            # 检查根元素判断格式
            if root.tag.endswith('XMI'):
                # 已经是XMI格式，直接使用，并转换为简单XML以支持REQIF导出
                xmi_output = xml_content
                simple_xml = convert_xmi_to_simple_xml(xml_content)
                self.current_simple_xml = simple_xml
                self.status_label.setText(f"导入XMI文件: {os.path.basename(file_path)}")
            elif root.tag == 'requirements':
                # 简单XML格式，需要转换为XMI
                cleaned_xml = clean_xml_output(xml_content)
                xmi_output = convert_simple_xml_to_xmi(cleaned_xml)
                self.current_simple_xml = cleaned_xml
                self.status_label.setText(f"导入并转换XML文件: {os.path.basename(file_path)}")
            else:
                QMessageBox.warning(self, "格式错误", "不支持的XML格式。请导入简单XML或XMI格式文件。")
                return
            
            # 保存XMI输出
            self.current_xmi_output = xmi_output
            
            # 解析XMI为树状数据
            tree_data = parse_xmi_to_tree_data(xmi_output)
            
            # 发出信号，传递数据到主窗口
            self.data_ready.emit("XML", tree_data, [])
            
            # 更新UI状态
            self.file_label.setText(f"已导入: {os.path.basename(file_path)}")
            self.export_xmi_button.setEnabled(True)
            self.export_reqif_button.setEnabled(True)
            self.clear_file_button.setEnabled(True)
            
        except ValueError as e:
            QMessageBox.critical(self, "转换错误", f"XML转换失败: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "导入错误", f"导入XML文件时出错: {str(e)}")
    
    def export_xmi_file(self):
        """导出当前XMI数据到文件"""
        if not self.current_xmi_output:
            QMessageBox.warning(self, "无数据", "没有可导出的XMI数据。请先生成或导入XML数据。")
            return
        
        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存XMI文件", "ASA.xml", "XML 文件 (*.xml);;所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        # 保存XMI文件
        success = save_xmi_file(self.current_xmi_output, file_path)
        
        if success:
            QMessageBox.information(self, "导出成功", f"XMI文件已成功保存到:\n{file_path}")
            self.status_label.setText(f"XMI文件已导出: {os.path.basename(file_path)}")
        else:
            QMessageBox.critical(self, "导出失败", "保存XMI文件失败，请检查文件路径和权限。")
    
    def export_reqif_file(self):
        """导出当前简单XML数据为REQIF文件"""
        if not self.current_simple_xml:
            QMessageBox.warning(self, "无数据", "没有可导出的XML数据。请先生成或导入简单XML数据。")
            return
        
        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存REQIF文件", "ASA.reqif", "REQIF 文件 (*.reqif);;所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            # 创建转换器实例
            converter = XMLToReqIFConverter()
            
            # 从字符串解析XML
            converter.parse_xml_string(self.current_simple_xml)
            
            # 生成REQIF文件
            converter.generate_reqif(file_path)
            
            QMessageBox.information(self, "导出成功", f"REQIF文件已成功保存到:\n{file_path}")
            self.status_label.setText(f"REQIF文件已导出: {os.path.basename(file_path)}")
            
        except ET.ParseError as e:
            QMessageBox.critical(self, "XML解析错误", f"XML格式不正确: {str(e)}")
            self.status_label.setText("REQIF导出失败：XML解析错误。")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"保存REQIF文件失败: {str(e)}")
            self.status_label.setText("REQIF导出失败。")

    def process_data(self):
        from PySide2.QtWidgets import QFileDialog, QMessageBox
        from PySide2.QtCore import QThread, Signal
        import os

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择多个XML文件", "", "XML 文件 (*.xml);;所有文件 (*.*)")
        if not file_paths:
            return

        class XmlMergeWorker(QThread):
            finished_signal = Signal(str)
            error_signal = Signal(str)

            def __init__(self, file_paths):
                super().__init__()
                self.file_paths = file_paths

            def run(self):
                try:
                    import re
                    from utils.xml_utils import convert_xmi_to_simple_xml, clean_xml_output
                    
                    # 🔥 直接文本合并，不做任何XML解析
                    merged_content = []
                    merged_content.append('<?xml version="1.0" encoding="UTF-8"?>')
                    merged_content.append('<requirements>')

                    for fp in self.file_paths:
                        try:
                            with open(fp, 'r', encoding='utf-8') as f:
                                content = f.read()

                            # 判断是否为 XMI 格式，如果是则先转换为简单 XML
                            if '<xmi:XMI' in content:
                                content = convert_xmi_to_simple_xml(content)
                            else:
                                content = clean_xml_output(content)

                            # 移除 XML 声明和外层 <requirements> 标签
                            content = re.sub(r'<\?xml.*?\?>', '', content, flags=re.IGNORECASE)
                            content = re.sub(r'<\s*requirements\s*>', '', content, flags=re.IGNORECASE)
                            content = re.sub(r'<\s*/\s*requirements\s*>', '', content, flags=re.IGNORECASE)
                            merged_content.append(content.strip())

                        except Exception as e:
                            print(f"跳过文件 {os.path.basename(fp)}：{str(e)}")
                            continue

                    merged_content.append('</requirements>')
                    final_xml = '\n'.join(merged_content)

                    # --- 实现 ID 层级重新格式化 ---
                    counters = [0]
                    
                    def replace_id(match):
                        tag = match.group(0)
                        if tag.startswith('</'):
                            if len(counters) > 1:
                                counters.pop()
                            return tag
                        else:
                            counters[-1] += 1
                            new_id = "Sr_" + ".".join(map(str, counters))
                            
                            # 替换 id 属性 (支持单双引号和空格)
                            if re.search(r'\bid\s*=\s*["\'][^"\']*["\']', tag):
                                tag = re.sub(r'\bid\s*=\s*["\'][^"\']*["\']', f'id="{new_id}"', tag)
                            else:
                                tag = re.sub(r'<(requirement|metric)\b', r'<\1 id="' + new_id + '"', tag)
                            
                            # 检查是否为自闭合标签
                            if tag.endswith('/>') or tag.endswith('/ >'):
                                pass
                            else:
                                counters.append(0)
                            return tag
                            
                    # 匹配 <requirement ...>, </requirement>, <metric ...>, </metric>
                    final_xml = re.sub(r'</requirement>|</metric>|<requirement\b[^>]*>|<metric\b[^>]*>', replace_id, final_xml)

                    self.finished_signal.emit(final_xml)

                except Exception as e:
                    self.error_signal.emit(str(e))

        # ================= 合并完成回调 =================
        def on_merge_finished(result_xml):
            try:
                print("✅ 最终合并XML：")
                print(result_xml)

                self.current_simple_xml = result_xml

                from utils.xml_utils import convert_simple_xml_to_xmi, parse_xmi_to_tree_data
                try:
                    self.current_xmi_output = convert_simple_xml_to_xmi(result_xml)
                except:
                    self.current_xmi_output = result_xml

                try:
                    tree_data = parse_xmi_to_tree_data(self.current_xmi_output)
                    self.data_ready.emit("XML", tree_data, [])
                except:
                    pass

                self.export_xmi_button.setEnabled(True)
                self.export_reqif_button.setEnabled(True)
                QMessageBox.information(self, "成功", "XML 合并完成！")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"处理失败：{str(e)}")

        def on_merge_error(msg):
            QMessageBox.critical(self, "失败", f"合并错误：{msg}")

        self.worker = XmlMergeWorker(file_paths)
        self.worker.finished_signal.connect(on_merge_finished)
        self.worker.error_signal.connect(on_merge_error)
        self.status_label.setText("正在合并...")
        self.worker.start()

    def start_batch_processing(self):
        """开始或停止批量处理"""
        # 如果批量处理正在运行，则停止它
        if self.batch_processor.is_running:
            self.batch_processor.stop()
            self.batch_button.setText("⚡ 批量处理")
            self.send_button.setEnabled(True)
            if self.loading_movie.isValid():
                self.loading_movie.stop()
            self.loading_label.hide()
            return

        if not self.extracted_text_content or not self.extracted_text_content.strip():
            QMessageBox.warning(self, "无内容", "请先上传并解析文档！")
            return
            
        if not self.current_selected_model:
            QMessageBox.critical(self, "模型未选择", "请先在下拉列表中选择一个大模型。")
            return

        # 获取配置
        chunk_size_str = str(self.settings.value("batch_chunk_size", "300"))
        save_dir = str(self.settings.value("batch_save_dir", ""))
        
        try:
            chunk_size = int(chunk_size_str)
            if chunk_size <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.critical(self, "配置错误", f"无效的分段字数配置: {chunk_size_str}。请在配置页面中修改为大于0的整数。")
            return
            
        if not save_dir or not os.path.isdir(save_dir):
            QMessageBox.critical(
                self, "配置错误", 
                f"保存路径不存在或未配置: '{save_dir}'。\n请先点击右上角 [⚙️ 配置] 按钮设置有效的保存路径。"
            )
            return
            
        # 分段：以字符数切分 extracted_text_content
        text = self.extracted_text_content.strip()
        # chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        chunks = smart_chunk_text(text, max_chunk_size=chunk_size)
        
        # 确认框
        reply = QMessageBox.question(
            self, "确认批量处理",
            f"分段字数: {chunk_size}\n"
            f"总字数: {len(text)}\n"
            f"将切分为 {len(chunks)} 段进行顺序处理。\n"
            f"结果将自动保存至目录:\n{save_dir}\n\n是否开始批量处理？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
            
        # 禁用普通发送按钮，更改批量按钮文字
        self.send_button.setEnabled(False)
        self.batch_button.setText("⏹️ 停止批量")
        
        # 显示加载状态
        if self.loading_movie.isValid():
            self.loading_label.show()
            self.loading_movie.start()
        else:
            self.loading_label.setText("批量处理中...")
            self.loading_label.show()
            
        # 构造系统提示词
        user_visible_system_prompt = self.system_prompt_textbox.toPlainText().strip()
        xml_internal_prompt = str(self.settings.value("internal_prompt_xml", INTERNAL_BASE_PROMPT_XML))
        final_system_prompt = xml_internal_prompt + \
                              "\n\n---\n用户附加指令 (请严格遵守以下格式化要求):\n---\n" + \
                              user_visible_system_prompt
                              
        # 启动批量处理器
        self.batch_processor.start(chunks, save_dir, final_system_prompt, self.current_selected_model)


    @Slot(int, int)
    def on_batch_progress(self, current, total):
        self.status_label.setText(f"批量处理进度: {current}/{total}")

    @Slot(str)
    def on_batch_status(self, text):
        self.status_label.setText(text)

    @Slot()
    def on_batch_finished(self):
        self.send_button.setEnabled(True)
        self.batch_button.setText("⚡ 批量处理")
        if self.loading_movie.isValid():
            self.loading_movie.stop()
        self.loading_label.hide()
        QMessageBox.information(self, "批量处理完成", f"所有分段已解析完成，XML文件已保存至配置的目录。")

    @Slot(str)
    def on_batch_error(self, error_msg):
        self.send_button.setEnabled(True)
        self.batch_button.setText("⚡ 批量处理")
        if self.loading_movie.isValid():
            self.loading_movie.stop()
        self.loading_label.hide()
        QMessageBox.critical(self, "批量处理错误", error_msg)
        self.status_label.setText("批量处理因错误终止。")

    @Slot(int, str, str, list)
    def on_batch_chunk_result(self, chunk_num, cleaned_xml, xmi_output, tree_data):
        """当前分段解析完成回调，实时更新界面各区域"""
        # 1. 保存当前分段数据，供可能的手动导出
        self.current_xmi_output = xmi_output
        self.current_simple_xml = cleaned_xml
        
        # 2. 触发信号，更新右侧的 “文本输出” 框
        self.raw_api_output = xmi_output
        self.cleaned_api_output = cleaned_xml
        self.api_text_ready.emit(xmi_output, cleaned_xml)
        
        # 3. 触发信号，将当前分段的 XML 数据渲染至 “需求树” 中
        self.data_ready.emit("XML", tree_data, [])
        
        # 4. 更新文件预览区为当前处理的分段文本
        if 0 <= chunk_num - 1 < len(self.batch_processor.chunks):
            current_chunk_text = self.batch_processor.chunks[chunk_num - 1]
            self.extracted_text_ready.emit(current_chunk_text)
            
        # 5. 允许单段导出
        self.export_xmi_button.setEnabled(True)
        self.export_reqif_button.setEnabled(True)

    @Slot(int, str)
    def on_batch_chunk_error(self, chunk_num, error_msg):
        """单个分段处理出错时的回调（不中断批量执行）"""
        self.status_label.setText(f"⚠️ 第 {chunk_num} 段处理错误，已记录并跳过。")