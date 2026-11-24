#!/usr/bin/env python3
# coding: utf-8

import sys
from PySide2.QtWidgets import QApplication
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("文档数据助手")
    app.setOrganizationName("个人作品")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 