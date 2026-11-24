from PySide2.QtCore import QThread, Signal
import sys
import os

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.file_utils import parse_file

class FileParseWorker(QThread):
    """文件解析工作线程"""
    finished = Signal(str, str)  # (file_path, result)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        
    def run(self):
        result = parse_file(self.file_path)
        self.finished.emit(self.file_path, result) 