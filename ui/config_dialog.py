import requests
from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QComboBox, QTextEdit, QTabWidget, QWidget,
    QSizePolicy, QFormLayout, QSplitter
)
from PySide2.QtCore import Qt, QSettings
from PySide2.QtGui import QIntValidator
import traceback

from utils.api_utils import build_api_url, build_authorization_value, normalize_api_path
from utils.api_utils import normalize_connection_defaults
from ui.doc_analysis_tab import INTERNAL_BASE_PROMPT_JSON, INTERNAL_BASE_PROMPT_XML


class ConfigDialog(QDialog):
    """Nginx 反向代理地址配置对话框。

    用户只需填写代理服务器的 IP 和端口，无需了解后端路径细节。
    本地测试时可填 127.0.0.1:7870（按本地代理实际端口）；
    真实部署时填服务器真实 IP 和 Nginx 监听端口。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代理服务器配置")
        self.setMinimumWidth(420)
        self.resize(680, 620)

        # 读取持久化配置
        # ── 利用系统的原生机制存储配置（解决打包 exe 后 ini 文件丢失/只读的问题） ──
        # 不再硬编码 config.ini，直接调用无参 QSettings()
        # 依赖于 main.py 中定义的 app.setOrganizationName 和 app.setApplicationName
        self.settings = QSettings()
        self._migrate_legacy_settings()

        self._init_ui()

    def _migrate_legacy_settings(self):
        host = self.settings.value("proxy_host", "")
        port = self.settings.value("proxy_port", "")
        path = self.settings.value("api_path", "")

        new_host, new_port, new_path, migrated = normalize_connection_defaults(host, port, path)
        if migrated:
            self.settings.setValue("proxy_host", new_host)
            self.settings.setValue("proxy_port", new_port)
            self.settings.setValue("api_path", new_path)
            if not self.settings.value("auth_mode", ""):
                self.settings.setValue("auth_mode", "auto")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.network_tab = QWidget()
        self.prompt_tab = QWidget()
        self.batch_tab = QWidget()
        self.tabs.addTab(self.network_tab, "网络配置")
        self.tabs.addTab(self.prompt_tab, "提示词配置")
        self.tabs.addTab(self.batch_tab, "批量配置")

        self._init_network_tab()
        self._init_prompt_tab()
        self._init_batch_tab()

        # ── 按钮 ───────────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()

        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_and_accept)
        self.save_btn.setDefault(True)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _init_network_tab(self):
        layout = QVBoxLayout(self.network_tab)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        # ── 说明文字 ──────────────────────────────────────────────────────────
        info_label = QLabel(
            "请填写真实服务器上接口地址、端口以及 API Key。"
        )
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        # ── IP 地址输入 ────────────────────────────────────────────────────────
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.settings.value("proxy_host", "127.0.0.1"))
        self.ip_input.setPlaceholderText("例如: 192.168.1.100 或 example.com")
        form_layout.addRow("代理 IP：", self.ip_input)

        # ── 端口输入 ───────────────────────────────────────────────────────────
        self.port_input = QLineEdit()
        self.port_input.setText(self.settings.value("proxy_port", "7870"))
        self.port_input.setPlaceholderText("例如: 80 或 443")
        self.port_input.setMaximumWidth(180)
        # 只允许输入数字，范围 1-65535
        self.port_input.setValidator(QIntValidator(1, 65535, self))
        form_layout.addRow("端口：", self.port_input)

        # ── API Path 输入（应对 gemerate/generate 拼写错误） ──────────────────
        self.path_input = QLineEdit()
        self.path_input.setText(self.settings.value("api_path", "/v1/chat/completion"))
        self.path_input.setPlaceholderText("例如: /v1/chat/completion")
        form_layout.addRow("API 路径：", self.path_input)
        
        # ── API Key（可选）────────────────────────────────────────────────────
        self.key_input = QLineEdit()
        self.key_input.setText(self.settings.value("api_key", ""))
        self.key_input.setPlaceholderText("填 sk-xxx 或 Bearer sk-xxx；留空则不带 Authorization")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("API Key：", self.key_input)

        # ── 认证方式 ─────────────────────────────────────────────────────────
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem("自动（推荐）", "auto")
        self.auth_mode_combo.addItem("Bearer", "bearer")
        self.auth_mode_combo.addItem("原样透传", "raw")
        self.auth_mode_combo.addItem("不发送", "none")
        saved_auth_mode = str(self.settings.value("auth_mode", "auto") or "auto")
        saved_index = self.auth_mode_combo.findData(saved_auth_mode)
        if saved_index >= 0:
            self.auth_mode_combo.setCurrentIndex(saved_index)
        form_layout.addRow("认证方式：", self.auth_mode_combo)

        layout.addLayout(form_layout)
        layout.addStretch(1)

    def _init_prompt_tab(self):
        layout = QVBoxLayout(self.prompt_tab)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        hint = QLabel("高级配置：可编辑 JSON/XML 内置提示词。修改后将持久化保存。")
        hint.setWordWrap(True)
        hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Vertical)

        json_container = QWidget()
        json_layout = QVBoxLayout(json_container)
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.setSpacing(6)
        json_layout.addWidget(QLabel("JSON 内置提示词："))
        self.json_prompt_input = QTextEdit()
        self.json_prompt_input.setPlainText(
            str(self.settings.value("internal_prompt_json", INTERNAL_BASE_PROMPT_JSON))
        )
        json_layout.addWidget(self.json_prompt_input)
        splitter.addWidget(json_container)

        xml_container = QWidget()
        xml_layout = QVBoxLayout(xml_container)
        xml_layout.setContentsMargins(0, 0, 0, 0)
        xml_layout.setSpacing(6)
        xml_layout.addWidget(QLabel("XML 内置提示词："))
        self.xml_prompt_input = QTextEdit()
        self.xml_prompt_input.setPlainText(
            str(self.settings.value("internal_prompt_xml", INTERNAL_BASE_PROMPT_XML))
        )
        xml_layout.addWidget(self.xml_prompt_input)
        splitter.addWidget(xml_container)

        splitter.setSizes([260, 260])
        layout.addWidget(splitter, 1)

    def _init_batch_tab(self):
        layout = QVBoxLayout(self.batch_tab)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        
        info_label = QLabel("批量处理配置：设置文档切分字数和自动保存XML文件的路径。")
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(info_label)
        
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)
        
        # 分段字数输入
        self.batch_chunk_size_input = QLineEdit()
        self.batch_chunk_size_input.setText(str(self.settings.value("batch_chunk_size", "300")))
        self.batch_chunk_size_input.setValidator(QIntValidator(10, 100000, self))
        self.batch_chunk_size_input.setPlaceholderText("例如: 300")
        form_layout.addRow("分段字数：", self.batch_chunk_size_input)
        
        # 保存路径输入
        path_layout = QHBoxLayout()
        self.batch_save_dir_input = QLineEdit()
        self.batch_save_dir_input.setText(str(self.settings.value("batch_save_dir", "")))
        self.batch_save_dir_input.setPlaceholderText("选择XML文件自动保存的文件夹")
        path_layout.addWidget(self.batch_save_dir_input)
        
        self.batch_browse_btn = QPushButton("浏览...")
        self.batch_browse_btn.clicked.connect(self._browse_batch_save_dir)
        path_layout.addWidget(self.batch_browse_btn)
        
        form_layout.addRow("保存路径：", path_layout)
        
        layout.addLayout(form_layout)
        layout.addStretch(1)
        
    def _browse_batch_save_dir(self):
        from PySide2.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, "选择XML自动保存目录", self.batch_save_dir_input.text() or "")
        if dir_path:
            self.batch_save_dir_input.setText(dir_path)

    # ── 内部方法 ───────────────────────────────────────────────────────────────

    def _get_current_inputs(self):
        """返回 (host, port_str, api_path, api_key, auth_mode)。"""
        host = self.ip_input.text().strip()
        port = self.port_input.text().strip()
        api_path = normalize_api_path(self.path_input.text().strip(), "/v1/chat/completion")
        api_key = self.key_input.text().strip()
        auth_mode = self.auth_mode_combo.currentData()
        return host, port, api_path, api_key, auth_mode

    def _test_connection(self):
        """向指定的代理路径发送一个最小化 POST，验证代理连通性。"""
        host, port, api_path, api_key, auth_mode = self._get_current_inputs()
        if not host or not port:
            QMessageBox.warning(self, "警告", "IP 地址和端口不能为空！")
            return

        test_url = build_api_url(host, port, api_path)
        test_payload = {
            "model": "deepseek-r1:70b",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False
        }
        headers = {"Content-Type": "application/json"}
        auth_header_value, effective_mode = build_authorization_value(api_key, auth_mode)
        if auth_header_value:
            headers["Authorization"] = auth_header_value

        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")

        try:
            # 只要收到任意 HTTP 响应（包括 4xx/5xx）说明 Nginx 可达
            response = requests.post(test_url, headers=headers, json=test_payload, timeout=10)
            if response.status_code == 200:
                preview = response.text[:500]
                QMessageBox.information(
                    self, "成功",
                    f"✓ 测试通过！\n地址: {test_url}\n认证模式: {effective_mode}\n\n响应预览:\n{preview}"
                )
            else:
                error_body = response.text[:1200]
                QMessageBox.warning(
                    self, "部分成功",
                    f"代理可达，但返回状态码 {response.status_code}。\n"
                    f"地址: {test_url}\n"
                    f"认证模式: {effective_mode}\n\n"
                    f"响应内容:\n{error_body}"
                )
        except requests.exceptions.ConnectionError as e:
            QMessageBox.critical(
                self, "连接失败",
                f"无法连接到 {test_url}。\n\n"
                "请检查：\n"
                "  1. IP 和端口是否正确\n"
                "  2. 服务器的 Nginx 服务是否正在运行且防火墙已放行\n\n"
                f"错误详情: {e}"
            )
        except requests.exceptions.Timeout as e:
            QMessageBox.critical(self, "超时", f"连接 {test_url} 超时（10秒），请检查网络或服务器状态。\n错误详情: {e}")
        except requests.exceptions.RequestException as e:
            detail = traceback.format_exc()
            QMessageBox.critical(self, "请求错误", f"测试失败：{e}\n\n堆栈:\n{detail}")
        except Exception as e:
            detail = traceback.format_exc()
            QMessageBox.critical(self, "未知错误", f"测试失败：{e}\n\n堆栈:\n{detail}")
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")

    def _save_and_accept(self):
        """将 IP、端口和 API Key 持久化到 config.ini 后关闭对话框。"""
        host, port, api_path, api_key, auth_mode = self._get_current_inputs()
        if not host or not port:
            QMessageBox.warning(self, "警告", "IP 地址和端口不能为空！")
            return

        self.settings.setValue("proxy_host", host)
        self.settings.setValue("proxy_port", port)
        self.settings.setValue("api_key", api_key)
        self.settings.setValue("api_path", api_path)
        self.settings.setValue("auth_mode", auth_mode)
        self.settings.setValue("internal_prompt_json", self.json_prompt_input.toPlainText())
        self.settings.setValue("internal_prompt_xml", self.xml_prompt_input.toPlainText())
        self.settings.setValue("batch_chunk_size", self.batch_chunk_size_input.text().strip())
        self.settings.setValue("batch_save_dir", self.batch_save_dir_input.text().strip())

        self.accept()

    # ── 公开查询方法（供调用方读取保存后的值）────────────────────────────────

    def get_proxy_host(self):
        return self.settings.value("proxy_host", "127.0.0.1")

    def get_proxy_port(self):
        return self.settings.value("proxy_port", "7870")
    
    def get_api_path(self):
        return self.settings.value("api_path", "/v1/chat/completion")
