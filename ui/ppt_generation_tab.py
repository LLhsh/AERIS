import os
import sys
from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar, QLineEdit
)
from PySide2.QtCore import Qt, Signal, Slot, QSize, QTimer
from PySide2.QtGui import QFont, QIcon
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QLineEdit, QProgressBar,
                              QGroupBox, QTextEdit, QSizePolicy)

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from word_to_ppt.word_to_ppt_converter import WordToPPTConverter

# 自定义可拖放文件的LineEdit
class DragDropLineEdit(QLineEdit):
    def __init__(self, parent=None, file_type=""):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.file_type = file_type  # 例如 ".docx" 或 ".pptx"
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and len(urls) > 0:
            file_path = urls[0].toLocalFile()
            if not self.file_type or file_path.endswith(self.file_type):
                self.setText(file_path)
                self.textChanged.emit(file_path)
            else:
                QMessageBox.warning(self, "文件类型错误", f"请拖放{self.file_type}类型的文件")

# 自定义样式的进度条
class StyledProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QProgressBar {
                border: 2px solid #76797C;
                border-radius: 5px;
                text-align: center;
                background-color: #F0F0F0;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                width: 10px;
                margin: 0.5px;
                border-radius: 3px;
            }
        """)

class PPTGenerationTab(QWidget):
    """智能PPT生成标签页"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 文件选择区域
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(10)
        
        # 设置文件选择区域为固定高度，增大其占比
        file_group.setMinimumHeight(200)  # 增加最小高度
        file_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(file_group)
        
        # Word文件选择
        word_layout = QHBoxLayout()
        word_label = QLabel("Word文件：")
        word_label.setMinimumWidth(100)
        self.word_path_edit = DragDropLineEdit(file_type=".docx")
        self.word_path_edit.setPlaceholderText("拖放Word文件到这里或点击选择按钮")
        self.word_path_edit.textChanged.connect(self.on_word_file_changed)
        
        word_button = QPushButton("选择文件")
        word_button.setIcon(QIcon(self.get_resource_path("app_icon.png")))
        word_button.setIconSize(QSize(20, 20))
        word_button.clicked.connect(self.select_word_file)
        word_layout.addWidget(word_label)
        word_layout.addWidget(self.word_path_edit)
        word_layout.addWidget(word_button)
        file_layout.addLayout(word_layout)
        
        # PPT保存位置
        ppt_layout = QHBoxLayout()
        ppt_label = QLabel("PPT保存位置：")
        ppt_label.setMinimumWidth(100)
        self.ppt_path_edit = DragDropLineEdit(file_type=".pptx")
        self.ppt_path_edit.setPlaceholderText("选择PPT保存位置")
        
        ppt_button = QPushButton("选择位置")
        ppt_button.setIcon(QIcon(self.get_resource_path("app_icon.png")))
        ppt_button.setIconSize(QSize(20, 20))
        ppt_button.clicked.connect(self.select_ppt_location)
        ppt_layout.addWidget(ppt_label)
        ppt_layout.addWidget(self.ppt_path_edit)
        ppt_layout.addWidget(ppt_button)
        file_layout.addLayout(ppt_layout)
        
        # PPT模板选择
        template_layout = QHBoxLayout()
        template_label = QLabel("PPT模板：")
        template_label.setMinimumWidth(100)
        self.template_path_edit = DragDropLineEdit(file_type=".pptx")
        self.template_path_edit.setPlaceholderText("可选：拖放PPT模板到这里或点击选择按钮")
        
        template_button = QPushButton("选择模板")
        template_button.setIcon(QIcon(self.get_resource_path("app_icon.png")))
        template_button.setIconSize(QSize(20, 20))
        template_button.clicked.connect(self.select_template_file)
        template_layout.addWidget(template_label)
        template_layout.addWidget(self.template_path_edit)
        template_layout.addWidget(template_button)
        file_layout.addLayout(template_layout)
        
        layout.addWidget(file_group)
        
        # 进度条和状态
        progress_group = QGroupBox("转换进度")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(8)
        
        # 设置进度条区域为较大的固定高度
        progress_group.setMinimumHeight(100)  # 增加最小高度
        progress_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.progress_bar = StyledProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        # 增加进度条的高度
        self.progress_bar.setMinimumHeight(20)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("准备就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = QFont("Microsoft YaHei", 10)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        # 增加状态标签的上下边距
        self.status_label.setContentsMargins(0, 10, 0, 10)
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # 转换按钮
        convert_button = QPushButton("开始转换")
        convert_button.setMinimumHeight(40)
        convert_button.setIcon(QIcon(self.get_resource_path("app_icon.png")))
        convert_button.setIconSize(QSize(24, 24))
        convert_button.clicked.connect(self.start_conversion)
        button_font = QFont("Microsoft YaHei", 11)
        button_font.setBold(True)
        convert_button.setFont(button_font)
        convert_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:pressed {
                background-color: #16a085;
            }
        """)
        layout.addWidget(convert_button)
        
        # 帮助文本
        help_group = QGroupBox("使用说明")
        help_layout = QVBoxLayout(help_group)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        
        help_text.setHtml(f"""
        <p>1. 选择要转换的Word文档</p>
        <p>2. 选择PPT文件保存位置</p>
        <p>3. 选择PPT模板文件</p>
        <p>4. 点击'开始转换'按钮</p>
        <p><b>提示：</b>您可以直接将文件拖放到对应的输入框中</p>
        """)
        help_text.setStyleSheet("background-color: #F8F9FA; border: none;")
        help_layout.addWidget(help_text)
        
        # 设置帮助文本区域为较小的固定高度
        help_group.setMaximumHeight(300)  # 减小最大高度
        help_group.setMinimumHeight(300)  # 设置最小高度与最大高度相同，使其保持固定
        help_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(help_group)
        
        # 移除弹性空间
        # layout.addStretch(1)  # 删除这一行
    
    def get_resource_path(self, relative_path):
        # 获取资源文件的绝对路径
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, relative_path)
    
    def on_word_file_changed(self, file_path):
        # 当Word文件路径改变时，自动设置PPT保存路径
        if file_path and os.path.exists(file_path):
            default_ppt = os.path.splitext(file_path)[0] + ".pptx"
            self.ppt_path_edit.setText(default_ppt)
    
    def select_word_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择Word文档",
            "",
            "所有文件 (*.*);;Word文档 (*.docx *.doc)"
        )
        if filename:
            self.word_path_edit.setText(filename)
            # 自动设置默认的PPT保存路径
            default_ppt = os.path.splitext(filename)[0] + ".pptx"
            self.ppt_path_edit.setText(default_ppt)
    
    def select_ppt_location(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "选择PPT保存位置",
            "",
            "PowerPoint演示文稿 (*.pptx)"
        )
        if filename:
            if not filename.endswith(".pptx"):
                filename += ".pptx"
            self.ppt_path_edit.setText(filename)
    
    def select_template_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择PPT模板",
            "",
            "所有文件 (*.*);;PPT文档 (*.pptx)"
        )
        if filename:
            self.template_path_edit.setText(filename)
    
    def start_conversion(self):
        word_file = self.word_path_edit.text()
        ppt_file = self.ppt_path_edit.text()
        template_file = self.template_path_edit.text()
        
        if not word_file or not ppt_file:
            QMessageBox.critical(self, "错误", "请选择Word文件和PPT保存位置")
            return
        
        if not os.path.exists(word_file):
            QMessageBox.critical(self, "错误", "所选Word文件不存在")
            return
        
        if template_file and not os.path.exists(template_file):
            QMessageBox.critical(self, "错误", "所选PPT模板文件不存在")
            return
        
        try:
            # 显示转换中的动画效果
            self.status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
            self.status_label.setText("正在转换...")
            
            # 创建进度条动画
            self.progress_bar.setValue(0)
            
            # 使用QTimer模拟进度更新
            self.progress_timer = QTimer(self)
            self.progress_timer.timeout.connect(self.update_progress)
            self.progress_timer.start(100)  # 每100毫秒更新一次
            
            # 创建转换器实例时传入模板路径
            converter = WordToPPTConverter(template_file if template_file else None)
            
            # 读取Word文档
            content = converter.read_word_document(word_file)
            
            if content is None:
                raise Exception("无法读取Word文档")
            
            # 处理内容
            if not converter.process_content(content):
                raise Exception("处理内容失败")
            
            # 保存PPT
            if not converter.save_presentation(ppt_file):
                raise Exception("保存PPT文件失败")
            
            # 停止进度条动画
            self.progress_timer.stop()
            self.progress_bar.setValue(100)
            
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.status_label.setText("转换完成！")
            
            # 显示成功消息框
            success_msg = QMessageBox(self)
            success_msg.setWindowTitle("成功")
            success_msg.setIcon(QMessageBox.Information)
            success_msg.setText(f"PPT文件已成功保存至：\n{ppt_file}")
            success_msg.setStandardButtons(QMessageBox.Ok)
            
            # 添加打开文件按钮
            open_button = success_msg.addButton("打开文件", QMessageBox.ActionRole)
            open_button.clicked.connect(lambda: os.startfile(ppt_file))
            
            success_msg.exec_()
            
        except Exception as e:
            # 停止进度条动画
            if hasattr(self, 'progress_timer'):
                self.progress_timer.stop()
            
            self.progress_bar.setValue(0)
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.status_label.setText("转换失败")
            
            QMessageBox.critical(self, "错误", f"转换过程中出错：\n{str(e)}")
    
    def update_progress(self):
        # 模拟进度更新
        current_value = self.progress_bar.value()
        if current_value < 90:  # 最大到90%，留10%给最终完成
            self.progress_bar.setValue(current_value + 1)