import sys
import os
from PySide2.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QProgressBar, QFileDialog,
                             QMessageBox, QGroupBox, QTextEdit, QFrame, QSplashScreen)
from PySide2.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, Property, QTimer
from PySide2.QtGui import QFont, QIcon, QPixmap, QColor, QPalette, QDrag, QDragEnterEvent, QDropEvent
from word_to_ppt_converter import WordToPPTConverter

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

# 自定义可拖放文件的LineEdit
class DragDropLineEdit(QLineEdit):
    def __init__(self, parent=None, file_type=""):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.file_type = file_type  # 例如 ".docx" 或 ".pptx"
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls and len(urls) > 0:
            file_path = urls[0].toLocalFile()
            if not self.file_type or file_path.endswith(self.file_type):
                self.setText(file_path)
                self.textChanged.emit(file_path)
            else:
                QMessageBox.warning(self, "文件类型错误", f"请拖放{self.file_type}类型的文件")

# 主应用窗口
class WordToPPTApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        # 设置窗口基本属性
        self.setWindowTitle("Word转PPT工具")
        self.setMinimumSize(700, 500)
        
        # 设置窗口图标
        self.setWindowIcon(QIcon(self.get_resource_path("icons/app_icon.png")))
        
        # 创建中央部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 应用样式表
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: #F5F5F5;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #1c6ea4;
            }
            QLineEdit {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }
            QLabel {
                color: #333333;
            }
        """)
        
        # 标题
        title_label = QLabel("Word文档转PPT工具")
        title_font = QFont("Microsoft YaHei", 16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        main_layout.addWidget(title_label)
        
        # 文件选择区域
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        
        # Word文件选择
        word_layout = QHBoxLayout()
        word_label = QLabel("Word文件：")
        word_label.setMinimumWidth(100)
        self.word_path_edit = DragDropLineEdit(file_type=".docx")
        self.word_path_edit.setPlaceholderText("拖放Word文件到这里或点击选择按钮")
        self.word_path_edit.textChanged.connect(self.on_word_file_changed)
        
        word_button = QPushButton("选择文件")
        word_button.setIcon(QIcon(self.get_resource_path("icons/word_icon.png")))
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
        ppt_button.setIcon(QIcon(self.get_resource_path("icons/ppt_icon.png")))
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
        template_button.setIcon(QIcon(self.get_resource_path("icons/template_icon.png")))
        template_button.setIconSize(QSize(20, 20))
        template_button.clicked.connect(self.select_template_file)
        template_layout.addWidget(template_label)
        template_layout.addWidget(self.template_path_edit)
        template_layout.addWidget(template_button)
        file_layout.addLayout(template_layout)
        
        main_layout.addWidget(file_group)
        
        # 进度条和状态
        progress_group = QGroupBox("转换进度")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = StyledProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("准备就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = QFont("Microsoft YaHei", 10)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(progress_group)
        
        # 转换按钮
        convert_button = QPushButton("开始转换")
        convert_button.setMinimumHeight(40)
        convert_button.setIcon(QIcon(self.get_resource_path("icons/convert_icon.png")))
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
        main_layout.addWidget(convert_button)
        
        # 帮助文本
        # 帮助文本
        help_group = QGroupBox("使用说明")
        help_layout = QVBoxLayout(help_group)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        
        # 获取图标的绝对路径
        info_icon_path = self.get_resource_path("icons/info_icon.png")
        
        help_text.setHtml(f"""
        <p><img src="{info_icon_path}" width="16" height="16"> 1. 选择要转换的Word文档</p>
        <p><img src="{info_icon_path}" width="16" height="16"> 2. 选择PPT文件保存位置</p>
        <p><img src="{info_icon_path}" width="16" height="16"> 3. 可选：选择PPT模板文件</p>
        <p><img src="{info_icon_path}" width="16" height="16"> 4. 点击'开始转换'按钮</p>
        <p><b>提示：</b>您可以直接将文件拖放到对应的输入框中</p>
        """)
        help_text.setMaximumHeight(120)
        help_text.setStyleSheet("background-color: #F8F9FA; border: none;")
        help_layout.addWidget(help_text)
        main_layout.addWidget(help_group)
        
        # 创建图标资源目录
        # 注释或删除这一行
        # self.create_icon_resources()
        
    def get_resource_path(self, relative_path):
        # 获取资源文件的绝对路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, relative_path)
    
    def create_icon_resources(self):
        # 创建图标资源目录
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        if not os.path.exists(icons_dir):
            os.makedirs(icons_dir)
            
        # 创建默认图标（如果不存在）
        icons = {
            "app_icon.png": "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",
            "word_icon.png": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAASBJREFUOI2lk71KA1EQhb/Zu9mIYGGRJ7ASC0FJoYKVD2Bh4QvYWPgcPoKdnYUgCFZpUgQsLBQ0EEgTSJpA2Nk1P5YbWE0gkBw4MMydc+4ZZuCfJfMGZnYKnAA7wBcwlJQtDDCzI+AcOAQiwAMj4E5S/jtAzK6AC2AlmD6BnqRu2QzMbA+4BNYDuA/cS3qYAZjZJnADbAXwK3Ak6bkA1MxawH0Az4A2cCvpvWiGmtk6cAesB/AncCypnwOY2QbQA7YDeAK0JD0VzVAzawKDAJ4CJ5KeiwZpZuvALdAI4DFwLOlhBmBmDaALNAP4HWhJepwBmFkN6ACHATwBmpIGRYOUkJWkL0kd4Ax4C+Aa0P8VXFaSvoCupDPgJYBrS4P/rG/VjYYpfJJfmwAAAABJRU5ErkJggg==",
            "ppt_icon.png": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAASBJREFUOI2lk71KA1EQhb/Zu9mIYGGRJ7ASC0FJoYKVD2Bh4QvYWPgcPoKdnYUgCFZpUgQsLBQ0EEgTSJpA2Nk1P5YbWE0gkBw4MMydc+4ZZuCfJfMGZnYKnAA7wBcwlJQtDDCzI+AcOAQiwAMj4E5S/jtAzK6AC2AlmD6BnqRu2QzMbA+4BNYDuA/cS3qYAZjZJnADbAXwK3Ak6bkA1MxawH0Az4A2cCvpvWiGmtk6cAesB/AncCypnwOY2QbQA7YDeAK0JD0VzVAzawKDAJ4CJ5KeiwZpZuvALdAI4DFwLOlhBmBmDaALNAP4HWhJepwBmFkN6ACHATwBmpIGRYOUkJWkL0kd4Ax4C+Aa0P8VXFaSvoCupDPgJYBrS4P/rG/VjYYpfJJfmwAAAABJRU5ErkJggg==",
            "template_icon.png": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAARdJREFUOI2lkj9LQnEYxj/Pe68ZhENDEBE0NLRFa1NzS1NTH6A+QEtfwMHRsaUhaGhpaQiioSAIGiIhCPT+aTiH7r3qrQ48y+F5fs/7vC/8WapmCZiPlXNIimEeLpf7kbqJcgbMYrUP7AJboboC7oCjIskfewNVc3wCHAPym/oWOM2S/KI3YBorBa6BtT/GH8B+keQPnYCqOc6AS2BlzvgNHGVJfj0VUDXHe8ABMHNOfjtlcwcwjdUWcA9sOCd/gMMiyW86AVNf7QJXwLpz8gvYK5L8qRMQh+oAOAdWnZM3YFgk+UsnIA7VJnAJbDknT8CkSPLXTkAcql3gDthwTp6BcZHk752AOFT7wAWw5pw8A+Miyed/XvnPWgBYJpUaPgEiVwAAAABJRU5ErkJggg==",
            "convert_icon.png": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAATtJREFUOI2lk79KA0EQxn+zd7eIYJEiT2AjFoJgIQhWPoGFhS9gY+FzWNnZCIJgZWMhCFZpUgQsUggJJHeSZMndroUHh0YSMA4Mw8x833wz7MJ/S1UdAYuhcglJMczD1XI/UrdRzoB5rA6APWA7VFfAPXCcJflzb6BqTk6BE0B+U98C51mSX/YGzGKlwA2w8cf4AzjMkvyxE1A1JzlwBazMGb+B4yzJb6YCqubkADgCFs7Jb6ds7gCmsRoBD8CWc/ILOMqS/LYTMIvVLnANrDsnv4CDLMmfOwFxqI6AC2DFOXkHRlmSv3YC4lBtA5fAyDl5AqZZkr91AuJQ7QMPwKZz8gxMsiR/7wTEoRoCXWDHOZkD4yzJF1OvvGQtAJZJpYZPkMgVMM+SfPHnlf+sBcAyqdTwCRK5/Asv/1nfJLCGKdnVEKAAAAAASUVORK5CYII=",
            "info_icon.png": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAANJJREFUOI2lkzFOAzEQRd+MvU5DmStwhbQpOAIlR0CiTkGdA3AEGo5AkYIqHAFxBVJQJJFCvGtTrJFWWbGRgCdZlkf/vxlbcGSpGgPTULmEpBjm4Wq5H6mbKCfANFQHwB6wHaor4B44ypL8uTdQNccnwDEgv6lvgdMsyS96A6ahUuAGWPtj/AEcZkn+0AmommMGXAErc8Zv4DhL8uupgKo53gMHwMw5+e2UzR3ANFZbwAOw4Zz8Ao6yJL/tBExDtQtcA+vOyS9gP0vyp05AHKoD4AJYdU7egGGW5O+dgP/WL5JJhimQm8HoAAAAAElFTkSuQmCC"
        }
        
        for icon_name, icon_data in icons.items():
            icon_path = os.path.join(icons_dir, icon_name)
            if not os.path.exists(icon_path):
                import base64
                with open(icon_path, "wb") as f:
                    f.write(base64.b64decode(icon_data))
    
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
            "Word文档 (*.docx)"
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
            "PowerPoint模板 (*.pptx)"
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
            
            QApplication.processEvents()
            
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

def show_splash_screen():
    # 显示启动画面
    app = QApplication.instance()
    splash_pix = QPixmap(200, 200)
    splash_pix.fill(QColor("#3498db"))
    splash = QSplashScreen(splash_pix)
    splash.showMessage("正在加载Word转PPT工具...", Qt.AlignCenter, Qt.white)
    splash.show()
    app.processEvents()
    
    # 模拟加载过程
    for i in range(1, 5):
        app.processEvents()
        import time
        time.sleep(0.3)
    
    return splash

def main():
    app = QApplication(sys.argv)
    # 使用Fusion风格，在所有平台上看起来都很现代
    app.setStyle("Fusion")
    
    # 显示启动画面
    splash = show_splash_screen()
    
    # 创建并显示主窗口
    window = WordToPPTApp()
    window.show()
    
    # 关闭启动画面
    splash.finish(window)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()