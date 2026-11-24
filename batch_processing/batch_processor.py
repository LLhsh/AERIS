import os
from PySide2.QtCore import QObject, QTimer, Signal
from workers.api_worker import OllamaApiWorker
from utils.xml_utils import clean_xml_output, convert_simple_xml_to_xmi, save_xmi_file, parse_xmi_to_tree_data

class BatchProcessor(QObject):
    """批量处理器：管理分段和顺序处理"""
    
    progress_update = Signal(int, int)  # current_chunk, total_chunks
    status_update = Signal(str)         # status message
    chunk_completed = Signal(int, str)  # chunk_num, file_path
    chunk_result_ready = Signal(int, str, str, list)  # chunk_num, cleaned_xml, xmi_output, tree_data
    chunk_error = Signal(int, str)      # chunk_num, error_message
    finished = Signal()                 # finished signal
    error_occurred = Signal(str)        # fatal error message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chunks = []
        self.save_dir = ""
        self.system_prompt = ""
        self.model_name = ""
        self.current_index = 0
        self.chunk_retry_count = 0
        self.is_running = False
        self.api_worker = None
        
    def start(self, chunks, save_dir, system_prompt, model_name):
        """开始批量处理"""
        if self.is_running:
            return
            
        self.chunks = chunks
        self.save_dir = save_dir
        self.system_prompt = system_prompt
        self.model_name = model_name
        self.current_index = 0
        self.chunk_retry_count = 0
        self.is_running = True
        
        self.status_update.emit(f"开始批量处理，共 {len(chunks)} 段")
        self.process_next()
        
    def process_next(self):
        """处理下一个段落"""
        if not self.is_running:
            return
            
        if self.current_index >= len(self.chunks):
            self.finish()
            return
            
        chunk = self.chunks[self.current_index]
        chunk_num = self.current_index + 1
        
        self.progress_update.emit(chunk_num, len(self.chunks))
        self.status_update.emit(f"正在处理第 {chunk_num}/{len(self.chunks)} 段...")
        
        # 构造用户请求内容
        user_content_for_api = f"## 文档内容分段 (第 {chunk_num} 段):\n{chunk.strip()}\n\n## 指令:\n请根据系统角色和用户附加指令处理上述文档内容。"
        
        # 创建工作线程并启动
        if self.api_worker is not None:
            try:
                self.api_worker.wait()
            except Exception:
                pass
            self.api_worker = None
            
        self.api_worker = OllamaApiWorker(self.system_prompt, user_content_for_api, self.model_name)
        self.api_worker.finished.connect(self.on_chunk_complete)
        self.api_worker.status_update.connect(lambda text: self.status_update.emit(f"第 {chunk_num} 段 - {text}"))
        self.api_worker.start()
        
    def on_chunk_complete(self, cleaned_output, raw_model_text):
        """单个段落处理完成"""
        if not self.is_running:
            return
            
        chunk_num = self.current_index + 1
        
        # 1. 检查是否为 API 错误消息 (例如网络连接断开、HTTP 错误等)
        is_api_error = False
        if (cleaned_output.startswith("错误：") or 
            cleaned_output.startswith("连接错误") or 
            cleaned_output.startswith("HTTP 错误") or 
            cleaned_output.startswith("请求错误") or 
            cleaned_output.startswith("发生未知错误")):
            is_api_error = True
            
        if is_api_error:
            # 如果是 API/网络 错误，保存错误日志文件，并跳过继续执行下一段
            error_file_name = f"ASA_chunk_{chunk_num:03d}_api_error.txt"
            error_file_path = os.path.join(self.save_dir, error_file_name)
            try:
                with open(error_file_path, "w", encoding="utf-8") as f:
                    f.write(f"API 调用发生错误：\n{cleaned_output}\n\n原始大模型响应:\n{raw_model_text}")
            except Exception as e:
                print(f"写入API错误日志失败: {e}")
                
            # 发出信号告知界面有此分段错误
            self.chunk_error.emit(chunk_num, f"API 调用错误：{cleaned_output}")
            self.status_update.emit(f"第 {chunk_num} 段 API 错误已跳过，记录至 {error_file_name}")
            
            # 继续下一段
            self._proceed_to_next()
            return
            
        try:
            # 清理XML并转换为XMI格式
            cleaned_xml = clean_xml_output(cleaned_output)
            xmi_output = convert_simple_xml_to_xmi(cleaned_xml)
            tree_data = parse_xmi_to_tree_data(xmi_output)
            
            # 自动生成文件名并保存到指定文件夹
            file_name = f"ASA_chunk_{chunk_num:03d}.xml"
            file_path = os.path.join(self.save_dir, file_name)
            
            success = save_xmi_file(xmi_output, file_path)
            if not success:
                raise IOError(f"保存文件到路径 {file_path} 失败，请检查写入权限。")
                
            self.chunk_completed.emit(chunk_num, file_path)
            self.chunk_result_ready.emit(chunk_num, cleaned_xml, xmi_output, tree_data)
            self.status_update.emit(f"第 {chunk_num} 段已成功保存为: {file_name}")
            
            # 继续下一段
            self._proceed_to_next()
            
        except Exception as e:
            # 2. 如果是解析错误（例如 XML 格式不正确），检查是否可以重试
            if self.chunk_retry_count < 1:
                self.chunk_retry_count += 1
                self.status_update.emit(
                    f"第 {chunk_num} 段 XML 解析错误 ({str(e)})，正在尝试重新生成 (第 {self.chunk_retry_count} 次重试)..."
                )
                if self.api_worker:
                    try:
                        self.api_worker.finished.disconnect()
                        self.api_worker.status_update.disconnect()
                    except Exception:
                        pass
                    try:
                        self.api_worker.wait()
                    except Exception:
                        pass
                    self.api_worker = None
                QTimer.singleShot(500, self.process_next)
                return

            import traceback
            error_detail = traceback.format_exc()
            
            error_file_name = f"ASA_chunk_{chunk_num:03d}_parse_error.txt"
            error_file_path = os.path.join(self.save_dir, error_file_name)
            
            try:
                with open(error_file_path, "w", encoding="utf-8") as f:
                    f.write(f"解析/格式化错误: {str(e)}\n\n"
                            f"Python 报错详情:\n{error_detail}\n\n"
                            f"=== 原始大模型输出候选 ===\n{cleaned_output}\n\n"
                            f"=== 完整大模型原始响应 ===\n{raw_model_text}")
            except Exception as write_err:
                print(f"写入解析错误日志失败: {write_err}")
                
            # 发出非致命段错误信号，通知界面展示错误信息，但不中断批量处理
            self.chunk_error.emit(chunk_num, f"XML格式或解析错误: {str(e)}")
            
            # 在界面上展示解析前的输出，方便用户在页面审查是何种格式问题
            self.chunk_result_ready.emit(chunk_num, cleaned_output, raw_model_text, [])
            self.status_update.emit(f"第 {chunk_num} 段解析错误，已保存原始输出至 {error_file_name}")
            
            # 继续下一段
            self._proceed_to_next()
            
    def _proceed_to_next(self):
        """开始处理下一段"""
        self.current_index += 1
        self.chunk_retry_count = 0
        # 延迟 500ms 处理下一段，避免 API 限流
        QTimer.singleShot(500, self.process_next)
            
    def stop(self):
        """停止批量处理"""
        self.is_running = False
        if self.api_worker and self.api_worker.isRunning():
            try:
                self.api_worker.terminate()
                self.api_worker.wait(1000)
            except Exception as e:
                print(f"停止工作线程时出错: {e}")
        self.api_worker = None
        self.status_update.emit("批量处理已终止。")
        
    def finish(self):
        """批量处理全部完成"""
        self.is_running = False
        self.api_worker = None
        self.status_update.emit(f"批量处理全部完成！共处理了 {len(self.chunks)} 个文件。")
        self.finished.emit()
