import requests
import json
from PySide2.QtCore import QThread, Signal
import sys
import os
from traceback import format_exc

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.json_utils import clean_model_output
from utils.api_utils import (
    build_api_url,
    build_authorization_value,
    mask_secret,
    normalize_connection_defaults,
    normalize_model_name,
)

# 流式/温度参数（可按需调整）
STREAM_ENABLED = False
TEMPERATURE_VALUE = 0


class OllamaApiWorker(QThread):
    """通过 Nginx 反向代理调用后端大模型 API 的工作线程。

    在本地测试时，代理地址指向迷你 Nginx 模拟器（validate_nginx_proxy.py）。
    在真实部署时，只需在 UI 配置弹窗中修改 proxy_host 和 proxy_port，
    代码本身无需任何改动。
    """
    finished = Signal(str, str)   # (cleaned_output, raw_output)
    status_update = Signal(str)

    def __init__(self, system_prompt, user_content, model_name):
        super().__init__()
        self.system_prompt = system_prompt
        self.user_content = user_content
        self.model_name = model_name

    def run(self):
        self.status_update.emit(f"正在调用 API (模型: {self.model_name})...")

        # ── 从 config.ini 读取代理地址和可选的 API Key ──────────────────────
        # ── 利用系统的原生机制存储配置（解决打包 exe 后 ini 文件只读/丢失的问题） ──
        # 不再硬编码 config.ini 的路径，而是直接调用无参 QSettings()。
        # 只要 main.py 中设置了 app.setOrganizationName 和 app.setApplicationName，
        # Windows 下它会自动写进注册表 (HKEY_CURRENT_USER\Software\...)，安全又持久。
        from PySide2.QtCore import QSettings
        settings = QSettings()

        proxy_host = settings.value("proxy_host", "127.0.0.1")
        proxy_port = settings.value("proxy_port", "7870")
        # 允许用户在 UI 里修改路径，应对 Nginx 里把 generate 写成 gemerate 的由于拼写错误发生的情况
        api_path = settings.value("api_path", "/v1/chat/completion")
        api_key = settings.value("api_key", "")
        auth_mode = settings.value("auth_mode", "auto")

        proxy_host, proxy_port, api_path, migrated = normalize_connection_defaults(
            proxy_host, proxy_port, api_path
        )
        if migrated:
            settings.setValue("proxy_host", proxy_host)
            settings.setValue("proxy_port", proxy_port)
            settings.setValue("api_path", api_path)

        model_name = normalize_model_name(self.model_name)

        # 动态拼接完整的 API URL
        api_url = build_api_url(proxy_host, proxy_port, api_path)

        # ── 构造请求头 ────────────────────────────────────────────────────────
        headers = {"Content-Type": "application/json"}
        auth_header_value, effective_mode = build_authorization_value(api_key, auth_mode)
        if auth_header_value:
            headers["Authorization"] = auth_header_value

        # ── 构造请求体 ────────────────────────────────────────────────────────
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": self.user_content}
            ],
            "stream": STREAM_ENABLED,
            "temperature": TEMPERATURE_VALUE,
            "max_tokens": 16384,
            "options": {
                "num_ctx": 16384,
                "num_predict": -1
            }
        }

        raw_model_response_content = ""
        response = None
        try:
            if not str(api_key).strip() and str(auth_mode).lower() != "none":
                self.status_update.emit("警告：未配置 API Key，鉴权接口可能返回 401。")

            self.status_update.emit(
                f"请求中：{api_url} (auth={effective_mode}, key={mask_secret(api_key)}, model={model_name})"
            )
            response = requests.post(api_url, headers=headers, json=payload, timeout=3000)
            response.raise_for_status()
            response_data = response.json()

            # 兼容常见聊天返回结构 (OpenAI 格式 vs Ollama 原生格式)
            raw_model_response_content = ""
            if "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
                # OpenAI 标准格式 (如 /v1/chat/completions)
                message_obj = response_data["choices"][0].get("message", {})
                raw_model_response_content = str(message_obj.get("content", "")).strip()
            elif "message" in response_data and isinstance(response_data["message"], dict):
                # Ollama 原生格式 (如 /api/chat)
                raw_model_response_content = str(response_data["message"].get("content", "")).strip()
            elif "response" in response_data:
                # Ollama 原生单次生成格式 (如 /api/generate)
                raw_model_response_content = str(response_data.get("response", "")).strip()

            if raw_model_response_content:
                print(f"\n--- Raw Model Output ({self.model_name}) ---\n"
                      f"{raw_model_response_content}\n--- End Raw Model Output ---\n")

                cleaned_json_candidate = clean_model_output(raw_model_response_content)
                print(f"\n--- Cleaned Model Output (for JSON parsing) ---\n"
                      f"{cleaned_json_candidate}\n--- End Cleaned Model Output ---\n")

                self.finished.emit(cleaned_json_candidate, raw_model_response_content)
                self.status_update.emit("API 调用成功。")
            else:
                actual_response_str = json.dumps(response_data, ensure_ascii=False, indent=2)
                error_info = response_data.get("error") or "响应缺少支持的文本内容结构(已兼容 OpenAI/Ollama 格式)"
                msg = (
                    "错误：API 响应问题\n"
                    f"URL: {api_url}\n"
                    f"HTTP状态: {response.status_code}\n"
                    f"认证模式: {effective_mode}\n"
                    f"服务端错误字段: {error_info}\n"
                    f"服务端完整响应:\n{actual_response_str}"
                )
                self.finished.emit(msg, msg)
                self.status_update.emit(f"API 响应问题: {error_info}")

        except requests.exceptions.ConnectionError as conn_err:
            err_msg = (
                f"连接错误: 无法连接到代理服务器 ({api_url})。\n"
                f"请检查 Nginx是否正在运行，以及 IP/端口是否正确。\n"
                f"认证模式: {effective_mode}\n"
                f"详情: {conn_err}"
            )
            self.finished.emit(err_msg, err_msg)
            self.status_update.emit(f"无法连接到代理服务器 ({proxy_host}:{proxy_port})。")

        except requests.exceptions.HTTPError as http_err:
            error_detail = "未知服务器错误详情"
            try:
                error_content = response.json()
                error_detail = json.dumps(error_content, indent=2, ensure_ascii=False)
            except Exception:
                if response is not None and hasattr(response, "text"):
                    error_detail = response.text
            status_code = response.status_code if response is not None else "unknown"
            err_msg = (
                f"HTTP 错误: {http_err}\n"
                f"URL: {api_url}\n"
                f"HTTP状态: {status_code}\n"
                f"认证模式: {effective_mode}\n"
                f"响应详情:\n{error_detail}"
            )
            self.finished.emit(err_msg, err_msg)
            self.status_update.emit("API 调用 HTTP 错误。")

        except requests.exceptions.RequestException as req_err:
            response_preview = ""
            if response is not None and hasattr(response, "text"):
                response_preview = f"\n服务器返回:\n{response.text[:1500]}"
            err_msg = (
                f"请求错误: {req_err}\n"
                f"URL: {api_url}\n"
                f"认证模式: {effective_mode}"
                f"{response_preview}"
            )
            self.finished.emit(err_msg, err_msg)
            self.status_update.emit("API 调用请求错误。")

        except Exception as e:
            extra_info = ""
            if "response" in locals() and response is not None and hasattr(response, "text"):
                extra_info = f"\n服务器返回的原始内容:\n{response.text[:1000]}"
            err_msg = (
                f"发生未知错误: {e}\n"
                f"URL: {api_url}\n"
                f"认证模式: {effective_mode}\n"
                f"堆栈:\n{format_exc()}"
                f"{extra_info}"
            )
            self.finished.emit(err_msg, err_msg)
            self.status_update.emit(f"API 调用时发生未知错误。")


class ChatApiWorker(QThread):
    """聊天对话 API 工作线程。"""

    finished = Signal(bool, str, str)  # (success, message, raw_response)
    status_update = Signal(str)

    def __init__(self, messages, model_name):
        super().__init__()
        self.messages = messages
        self.model_name = model_name

    def run(self):
        from PySide2.QtCore import QSettings

        settings = QSettings()
        proxy_host = settings.value("proxy_host", "127.0.0.1")
        proxy_port = settings.value("proxy_port", "7870")
        api_path = settings.value("api_path", "/v1/chat/completion")
        api_key = settings.value("api_key", "")
        auth_mode = settings.value("auth_mode", "auto")

        proxy_host, proxy_port, api_path, migrated = normalize_connection_defaults(
            proxy_host, proxy_port, api_path
        )
        if migrated:
            settings.setValue("proxy_host", proxy_host)
            settings.setValue("proxy_port", proxy_port)
            settings.setValue("api_path", api_path)

        model_name = normalize_model_name(self.model_name)

        api_url = build_api_url(proxy_host, proxy_port, api_path)
        headers = {"Content-Type": "application/json"}
        auth_header_value, effective_mode = build_authorization_value(api_key, auth_mode)
        if auth_header_value:
            headers["Authorization"] = auth_header_value

        payload = {
            "model": model_name,
            "messages": self.messages,
            "stream": False,
            "max_tokens": 65536,
            "options": {
                "num_ctx": 65536,
                "num_predict": -1
            }
        }

        response = None
        try:
            if not str(api_key).strip() and str(auth_mode).lower() != "none":
                self.status_update.emit("警告：未配置 API Key，鉴权接口可能返回 401。")

            self.status_update.emit(
                f"对话请求中：{api_url} (auth={effective_mode}, key={mask_secret(api_key)}, model={model_name})"
            )
            response = requests.post(api_url, headers=headers, json=payload, timeout=3000)
            response.raise_for_status()

            data = response.json()
            
            # 兼容常见聊天返回结构 (OpenAI 格式 vs Ollama 原生格式)
            content = ""
            if "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
                # OpenAI 标准格式 (如 /v1/chat/completions)
                message_obj = data["choices"][0].get("message", {})
                content = str(message_obj.get("content", "")).strip()
            elif "message" in data and isinstance(data["message"], dict):
                # Ollama 原生格式 (如 /api/chat)
                content = str(data["message"].get("content", "")).strip()
            elif "response" in data:
                # Ollama 原生单次生成格式 (如 /api/generate)
                content = str(data.get("response", "")).strip()

            if not content:
                raw_text = json.dumps(data, ensure_ascii=False, indent=2)
                err = (
                    "响应中未找到助手内容。\n"
                    f"URL: {api_url}\n"
                    f"HTTP状态: {response.status_code}\n"
                    f"认证模式: {effective_mode}\n"
                    f"服务端响应:\n{raw_text}"
                )
                self.finished.emit(False, err, raw_text)
                return

            self.finished.emit(True, content, json.dumps(data, ensure_ascii=False))
            self.status_update.emit("对话请求成功。")

        except requests.exceptions.ConnectionError as e:
            err = (
                f"连接错误: {e}\n"
                f"URL: {api_url}\n"
                f"认证模式: {effective_mode}"
            )
            self.finished.emit(False, err, "")
        except requests.exceptions.HTTPError as e:
            detail = ""
            if response is not None and hasattr(response, "text"):
                detail = response.text[:2000]
            err = (
                f"HTTP 错误: {e}\n"
                f"URL: {api_url}\n"
                f"HTTP状态: {response.status_code if response is not None else 'unknown'}\n"
                f"认证模式: {effective_mode}\n"
                f"响应详情:\n{detail}"
            )
            self.finished.emit(False, err, detail)
        except requests.exceptions.RequestException as e:
            detail = response.text[:2000] if response is not None and hasattr(response, "text") else ""
            err = (
                f"请求错误: {e}\n"
                f"URL: {api_url}\n"
                f"认证模式: {effective_mode}\n"
                f"响应详情:\n{detail}"
            )
            self.finished.emit(False, err, detail)
        except Exception as e:
            detail = response.text[:2000] if response is not None and hasattr(response, "text") else ""
            err = (
                f"未知错误: {e}\n"
                f"URL: {api_url}\n"
                f"认证模式: {effective_mode}\n"
                f"堆栈:\n{format_exc()}\n"
                f"响应详情:\n{detail}"
            )
            self.finished.emit(False, err, detail)