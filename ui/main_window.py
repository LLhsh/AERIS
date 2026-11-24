from PySide2.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame, 
    QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem, QTextEdit, 
    QPushButton, QAbstractItemView, QLabel, QMessageBox, QTreeWidget, 
    QTreeWidgetItem, QLineEdit
)
from PySide2.QtCore import Qt, QSize, Slot, QTimer, QSettings
from PySide2.QtGui import QFont, QIcon
from ui.ppt_generation_tab import PPTGenerationTab
import os
import sys
import requests
import json

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.doc_analysis_tab import DocAnalysisTab
from ui.excel_word_tab import ExcelWordTab
from utils.xml_utils import parse_xmi_to_tree_data
from ui.config_dialog import ConfigDialog
from workers.api_worker import ChatApiWorker


class MainWindow(QMainWindow):
    """主窗口类"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文档分析助手")
        self.setGeometry(100, 100, 1320, 900)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        
        # 当前选择的模型
        self.current_selected_model = "deepseek-r1:70b"
        
        # ── 读取配置 ──
        # 使用系统的原生机制存储配置（不再硬编码 config.ini）
        self.settings = QSettings()
        
        # 文档和JSON数据
        self.extracted_text_content = ""
        self.json_data = None
        self.chat_history = []
        self.chat_worker = None
        self.is_chat_running = False
        
        self.init_ui()
        self.load_models()
        self.apply_styles()
    
    def init_ui(self):
        """初始化UI"""
        # 主布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 左侧面板
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_panel.setFrameShape(QFrame.Shape.StyledPanel)
        left_panel.setFixedWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建标签页控件
        self.left_tab_widget = QTabWidget()
        
        # 把配置按钮放在标签页的右上角
        self.config_btn = QPushButton("⚙️ 配置")
        self.config_btn.setToolTip("配置 Ollama 远端地址")
        self.config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.config_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #666;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #0078D7;
            }
        """)
        self.config_btn.clicked.connect(self.open_config_dialog)
        self.left_tab_widget.setCornerWidget(self.config_btn, Qt.Corner.TopRightCorner)
        
        left_layout.addWidget(self.left_tab_widget)
        
        # 创建文档分析标签页
        self.doc_analysis_tab = DocAnalysisTab(self)
        self.doc_analysis_tab.data_ready.connect(self.on_data_ready)
        self.doc_analysis_tab.extracted_text_ready.connect(self.on_extracted_text_ready)
        self.doc_analysis_tab.api_text_ready.connect(self.on_api_text_ready)
        self.left_tab_widget.addTab(self.doc_analysis_tab, "📄 文档分析")
        
        # 创建Excel-Word工具标签页
        self.excel_word_tab = ExcelWordTab(self)
        self.left_tab_widget.addTab(self.excel_word_tab, "📊 智能表格插入")
        self.ppt_generation_tab = PPTGenerationTab(self)
        self.left_tab_widget.addTab(self.ppt_generation_tab, "🎬 智能PPT生成")
        
        # 右侧面板
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 文件预览区域
        preview_group = QWidget()
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(0, 0, 0, 8)
        preview_layout.addWidget(QLabel("📑 文件内容预览:"))
        self.extracted_text_display = QTextEdit()
        self.extracted_text_display.setReadOnly(True)
        preview_layout.addWidget(self.extracted_text_display)
        splitter.addWidget(preview_group)
        
        # 输出结果区域
        output_group_widget = QWidget()
        output_group_layout = QVBoxLayout(output_group_widget)
        output_group_layout.setContentsMargins(0, 8, 0, 0)
        output_group_layout.addWidget(QLabel("💡 输出结果:"))
        
        # 输出标签页
        self.output_tab_widget = QTabWidget()
        output_group_layout.addWidget(self.output_tab_widget)
        
        # 表格输出标签页
        table_tab_content_widget = QWidget()
        table_tab_layout = QVBoxLayout(table_tab_content_widget)
        table_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.output_table_widget = QTableWidget()
        self.output_table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.output_table_widget.setAlternatingRowColors(True)
        self.output_table_widget.horizontalHeader().setStretchLastSection(True)
        self.output_table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.output_table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # 禁用排序功能，确保列顺序不会被改变
        self.output_table_widget.setSortingEnabled(False)
        table_tab_layout.addWidget(self.output_table_widget)
        self.output_tab_widget.addTab(table_tab_content_widget, "📊 表格结果")
        
        # 文本输出标签页
        text_tab_content_widget = QWidget()
        text_tab_layout = QVBoxLayout(text_tab_content_widget)
        text_tab_layout.setContentsMargins(0, 5, 0, 0)
        
        self.toggle_text_output_button = QPushButton("显示原始输出")
        self.toggle_text_output_button.setEnabled(False)
        self.toggle_text_output_button.clicked.connect(self.toggle_api_text_output_view)
        text_tab_layout.addWidget(self.toggle_text_output_button)
        
        self.api_text_output_display = QTextEdit()
        self.api_text_output_display.setReadOnly(True)
        text_tab_layout.addWidget(self.api_text_output_display)
        self.output_tab_widget.addTab(text_tab_content_widget, "📝 文本输出")
        
        # 需求树标签页
        tree_tab_content_widget = QWidget()
        tree_tab_layout = QVBoxLayout(tree_tab_content_widget)
        tree_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.output_tree_widget = QTreeWidget()
        self.output_tree_widget.setHeaderLabels(["#", "Name", "详细描述"])
        self.output_tree_widget.setColumnWidth(0, 150)
        self.output_tree_widget.setColumnWidth(1, 200)
        self.output_tree_widget.setAlternatingRowColors(True)
        
        # 设置树形控件的样式，修复选中时的颜色问题
        tree_style = """
        QTreeWidget {
            selection-background-color: #3daee9;
            selection-color: white;
            alternate-background-color: #f5f5f5;
        }
        QTreeWidget::item:selected {
            background-color: #3daee9;
            color: white;
        }
        QTreeWidget::item:hover {
            background-color: #e8f4fd;
            color: black;
        }
        """
        self.output_tree_widget.setStyleSheet(tree_style)
        tree_tab_layout.addWidget(self.output_tree_widget)
        self.output_tab_widget.addTab(tree_tab_content_widget, "📋 需求树")

        # 对话标签页
        chat_tab_content_widget = QWidget()
        chat_tab_layout = QVBoxLayout(chat_tab_content_widget)
        chat_tab_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("这里显示对话内容和错误信息。")
        chat_tab_layout.addWidget(self.chat_display)

        chat_input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入消息并按回车或点击发送")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        chat_input_layout.addWidget(self.chat_input)

        self.chat_send_btn = QPushButton("发送")
        self.chat_send_btn.clicked.connect(self.send_chat_message)
        chat_input_layout.addWidget(self.chat_send_btn)

        self.chat_clear_btn = QPushButton("清空")
        self.chat_clear_btn.clicked.connect(self.clear_chat_history)
        chat_input_layout.addWidget(self.chat_clear_btn)

        chat_tab_layout.addLayout(chat_input_layout)
        self.output_tab_widget.addTab(chat_tab_content_widget, "💬 对话")
        
        splitter.addWidget(output_group_widget)
        QTimer.singleShot(0, lambda: splitter.setSizes([self.height() // 2 - 70, self.height() // 2 + 70]))
        
        right_layout.addWidget(splitter)
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)
        
        # 设置应用图标
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
    
    def load_models(self):
        """加载自定义模型列表（从系统注册表）。
        允许用户在 UI 层面自行增删模型，不再使用硬编码的静态列表。
        """
        saved_models = self.settings.value("custom_models", [])
        if not isinstance(saved_models, list):
            # QSettings 读取时可能会将单元素列表变成字符串
            saved_models = [str(saved_models)] if saved_models else []
            
        # 如果用户第一次打开，且列表为空，给两个默认值作为引导演示
        if not saved_models:
            saved_models = ["deepseek-r1:70b"]
            self.settings.setValue("custom_models", saved_models)
            
        loaded_models = saved_models
        
        # 将模型列表传递给文档分析标签页
        self.doc_analysis_tab.set_models(loaded_models)
        
        # 设置Excel-Word标签页的当前模型
        if loaded_models and self.current_selected_model not in loaded_models:
            self.current_selected_model = loaded_models[0]
        self.excel_word_tab.set_current_model(self.current_selected_model)
        
        # 连接文档分析标签页的模型选择信号
        self.doc_analysis_tab.model_selection_combobox.currentTextChanged.connect(self.on_model_changed)
        
    def open_config_dialog(self):
        """打开配置对话框"""
        dialog = ConfigDialog(self)
        dialog.exec_()
    
    def apply_styles(self):
        """应用样式表"""
        qss_file_name = "style.qss"
        qss_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), qss_file_name)
        try:
            with open(qss_file_path, "r", encoding="utf-8") as f:
                style_sheet_content = f.read()
                self.setStyleSheet(style_sheet_content)
            print(f"QSS样式已从 {qss_file_name} 加载并应用。")
        except FileNotFoundError:
            print(f"警告: 无法找到样式文件 {qss_file_name} 于路径: {qss_file_path}。将使用默认Qt样式。")
        except Exception as e:
            print(f"从 {qss_file_name} 加载QSS样式时发生错误: {e}")
    
    @Slot(str)
    def on_model_changed(self, model_name):
        """处理模型变更"""
        if model_name and model_name != self.current_selected_model:
            self.current_selected_model = model_name
            # 同步更新Excel-Word标签页的模型
            self.excel_word_tab.set_current_model(model_name)
            print(f"模型已更改为: {model_name}")
    
    @Slot(str, object, list)
    def on_data_ready(self, format_type, data, column_order):
        """处理数据就绪信号"""
        # 更新文本输出
        if hasattr(self.doc_analysis_tab, 'cleaned_api_output'):
            self.api_text_output_display.setText(self.doc_analysis_tab.cleaned_api_output)
            self.toggle_text_output_button.setEnabled(True)
        
        if format_type == "JSON":
            # 处理JSON数据
            self.json_data = data
            self.excel_word_tab.set_json_data(data)
            
            # 清空表格
            self.output_table_widget.clear()
            self.output_table_widget.setRowCount(0)
            self.output_table_widget.setColumnCount(0)
            
            # 清空树控件
            self.output_tree_widget.clear()
            
            # 如果数据有效，填充表格
            if data and isinstance(data, list) and len(data) > 0:
                # 使用传递的列顺序
                if column_order:
                    all_keys = column_order.copy()
                else:
                    first_item_keys = list(data[0].keys())
                    all_keys = first_item_keys.copy()
                    for item in data:
                        for key in item.keys():
                            if key not in all_keys:
                                all_keys.append(key)
                
                # 设置表格列数和表头
                self.output_table_widget.setColumnCount(len(all_keys))
                self.output_table_widget.setHorizontalHeaderLabels(all_keys)
                
                # 填充表格数据
                self.output_table_widget.setRowCount(len(data))
                for row_idx, row_data in enumerate(data):
                    for col_idx, header in enumerate(all_keys):
                        cell_value = str(row_data.get(header, ""))
                        self.output_table_widget.setItem(row_idx, col_idx, QTableWidgetItem(cell_value))
                
                # 调整列宽
                self.output_table_widget.resizeColumnsToContents()
            
            # 切换到表格标签页
            self.output_tab_widget.setCurrentIndex(0)
        
        elif format_type == "XML":
            # 处理XMI树状数据
            # 清空表格
            self.output_table_widget.clear()
            self.output_table_widget.setRowCount(0)
            self.output_table_widget.setColumnCount(0)
            
            # 清空树控件
            self.output_tree_widget.clear()
            
            # 填充树控件（data已经是XMI解析后的树状数据）
            if data and isinstance(data, list):
                self._populate_tree_recursive(self.output_tree_widget.invisibleRootItem(), data)
                self.output_tree_widget.expandAll()
            
            # 切换到需求树标签页
            self.output_tab_widget.setCurrentIndex(2)
    
    def _populate_tree_recursive(self, parent_item, nodes):
        """递归填充树控件"""
        for node in nodes:
            # 创建树项
            item = QTreeWidgetItem(parent_item)
            item.setText(0, node.get('id', ''))
            item.setText(1, node.get('name', ''))
            item.setText(2, node.get('text', ''))
            
            # 递归处理子节点
            if 'children' in node and node['children']:
                self._populate_tree_recursive(item, node['children'])
    
    @Slot(str)
    def on_extracted_text_ready(self, text):
        """处理文本提取就绪信号"""
        self.extracted_text_content = text
        self.extracted_text_display.setText(text)
        self.excel_word_tab.set_extracted_text(text)

    @Slot(str, str)
    def on_api_text_ready(self, raw_output, cleaned_output):
        """API返回文本更新（无论后续解析是否成功）。"""
        display_text = cleaned_output if cleaned_output else raw_output
        self.api_text_output_display.setText(display_text)
        self.toggle_text_output_button.setEnabled(bool(raw_output or cleaned_output))
        self.toggle_text_output_button.setText("显示原始输出")
    
    def toggle_api_text_output_view(self):
        """切换API文本输出视图"""
        if not hasattr(self.doc_analysis_tab, 'raw_api_output') or not hasattr(self.doc_analysis_tab, 'cleaned_api_output'):
            return
            
        current_text = self.api_text_output_display.toPlainText()
        if current_text == self.doc_analysis_tab.raw_api_output:
            # 切换到清理后的输出
            self.api_text_output_display.setText(self.doc_analysis_tab.cleaned_api_output)
            self.toggle_text_output_button.setText("显示原始输出")
        else:
            # 切换到原始输出
            self.api_text_output_display.setText(self.doc_analysis_tab.raw_api_output)
            self.toggle_text_output_button.setText("显示解析后输出")

    def _append_chat_line(self, role, text):
        role_map = {
            "user": "你",
            "assistant": "助手",
            "error": "错误"
        }
        role_name = role_map.get(role, role)
        self.chat_display.append(f"[{role_name}]\n{text}\n")

    def send_chat_message(self):
        if self.is_chat_running:
            return

        user_text = self.chat_input.text().strip()
        if not user_text:
            return

        self._append_chat_line("user", user_text)
        self.chat_history.append({"role": "user", "content": user_text})
        self.chat_input.clear()
        self.output_tab_widget.setCurrentIndex(3)

        self.is_chat_running = True
        self.chat_send_btn.setEnabled(False)
        self.chat_send_btn.setText("发送中...")

        model_name = self.current_selected_model
        self.chat_worker = ChatApiWorker(self.chat_history.copy(), model_name)
        self.chat_worker.status_update.connect(self.on_chat_status_update)
        self.chat_worker.finished.connect(self.on_chat_finished)
        self.chat_worker.start()

    @Slot(str)
    def on_chat_status_update(self, text):
        self.statusBar().showMessage(text, 4000)

    @Slot(bool, str, str)
    def on_chat_finished(self, success, message, raw_response):
        self.is_chat_running = False
        self.chat_send_btn.setEnabled(True)
        self.chat_send_btn.setText("发送")

        if success:
            self._append_chat_line("assistant", message)
            self.chat_history.append({"role": "assistant", "content": message})
        else:
            self._append_chat_line("error", message)

    def clear_chat_history(self):
        self.chat_history = []
        self.chat_display.clear()
    
    def closeEvent(self, event):
        """关闭窗口事件处理"""
        # 确保批量处理器已停止
        if hasattr(self.doc_analysis_tab, 'batch_processor') and self.doc_analysis_tab.batch_processor.is_running:
            self.doc_analysis_tab.batch_processor.stop()

        # 确保所有工作线程都已停止
        for worker_attr in ['file_parse_worker', 'api_worker']:
            if hasattr(self.doc_analysis_tab, worker_attr):
                worker = getattr(self.doc_analysis_tab, worker_attr)
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1000)  # 等待最多1秒

        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.chat_worker.quit()
            self.chat_worker.wait(1000)
        event.accept() 