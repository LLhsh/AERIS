"""XML工具模块 - 处理XMI格式转换和解析

功能：
1. 清理模型输出的简单XML
2. 将简单XML转换为XMI标准格式
3. 解析XMI为树状数据结构
4. 加载和保存XMI文件
"""

import xml.etree.ElementTree as ET
import re
import os
from xml.dom import minidom

# XMI生成配置
XMI_MODEL_NAME = "ConvertedRequirementsModel"
XMI_PACKAGE_NAME = "需求"
XMI_EXPORTER_VERSION = "1.0"
XMI_EXPORTER_NAME = "MagicDraw Clean XMI Exporter"
SYSML_PROFILE_URL = "http://www.omg.org/spec/SysML/20181001/SysML.xmi#SysML"

def clean_xml_output(raw_output):
    """
    清理模型输出，移除思考过程，只保留XML结果
    """
    # 移除思考标签
    cleaned = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<\s*\\\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\s*/\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)

    # 移除markdown代码块标记
    cleaned = re.sub(r'^```(?:xml|json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)
    
    # 提取XML内容
    xml_pattern = r'<\?xml.*?</requirements>'
    match = re.search(xml_pattern, cleaned, flags=re.DOTALL)
    if match:
        return match.group().strip()
    
    # 如果没有XML声明，尝试查找requirements标签
    req_pattern = r'<requirements>.*?</requirements>'
    match = re.search(req_pattern, cleaned, flags=re.DOTALL)
    if match:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + match.group().strip()
    
    return cleaned.strip()

def convert_simple_xml_to_xmi(simple_xml_string):
    """
    将简单XML格式转换为完整XMI格式
    
    参数：
        simple_xml_string: 简单XML字符串（<requirements>格式）
    
    返回：
        XMI格式的XML字符串
    """
    try:
        root = ET.fromstring(simple_xml_string)
    except ET.ParseError as e:
        raise ValueError(f"XML解析错误: {e}")
    
    # 检查是否已经是XMI格式
    if root.tag.endswith('XMI'):
        return simple_xml_string
    
    # XML转义处理
    def escape_xml(text):
        if not text:
            return ""
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&apos;')
        return text
    
    # 递归构建UML类结构
    def build_uml_class(req_element, indent_level=3):
        req_id = req_element.get('id', '')
        req_name = escape_xml(req_element.get('name', ''))
        indent = '   ' * indent_level
        
        children = [child for child in req_element if child.tag in ('requirement', 'metric')]
        
        if not children:
            # 叶子节点
            return f'{indent}<nestedClassifier xmi:type="uml:Class" xmi:id="class_{req_id}" name="{req_name}"/>\n'
        else:
            # 有子节点的节点
            result = f'{indent}<nestedClassifier xmi:type="uml:Class" xmi:id="class_{req_id}" name="{req_name}">\n'
            for child in children:
                result += build_uml_class(child, indent_level + 1)
            result += f'{indent}</nestedClassifier>\n'
            return result
     
    # 递归构建顶级包元素
    def build_packaged_element(req_element, indent_level=2):
        req_id = req_element.get('id', '')
        req_name = escape_xml(req_element.get('name', ''))
        indent = '   ' * indent_level
        
        children = [child for child in req_element if child.tag in ('requirement', 'metric')]
        
        if not children:
            # 叶子节点
            return f'{indent}<packagedElement xmi:type="uml:Class" xmi:id="class_{req_id}" name="{req_name}"/>\n'
        else:
            # 有子节点的节点
            result = f'{indent}<packagedElement xmi:type="uml:Class" xmi:id="class_{req_id}" name="{req_name}">\n'
            for child in children:
                result += build_uml_class(child, indent_level + 1)
            result += f'{indent}</packagedElement>\n'
            return result
     
    # 递归收集所有需求信息
    def collect_requirements(req_element, req_list):
        req_id = req_element.get('id', '')
        req_text = escape_xml(req_element.get('text', ''))
        req_list.append((req_id, req_text))
        
        for child in [c for c in req_element if c.tag in ('requirement', 'metric')]:
            collect_requirements(child, req_list)
     
    # 构建UML类结构部分
    uml_classes = ""
    for req in [c for c in root if c.tag in ('requirement', 'metric')]:
        uml_classes += build_packaged_element(req)
     
    # 收集所有需求
    all_requirements = []
    for req in [c for c in root if c.tag in ('requirement', 'metric')]:
        collect_requirements(req, all_requirements)
    
    # 构建SysML需求部分
    sysml_requirements = ""
    for req_id, req_text in all_requirements:
        sysml_requirements += f'   <sysml:Requirement xmi:id="req_{req_id}" base_Class="class_{req_id}" Id="{req_id}" Text="{req_text}"/>\n'
    
    # 组装完整XMI文档
    xmi_output = f'''<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmlns:MD_Customization_for_Requirements__additional_stereotypes="http://www.magicdraw.com/spec/Customization/180/Requirements"
          xmlns:MD_Customization_for_SysML__additional_stereotypes="http://www.magicdraw.com/spec/Customization/180/SysML"
          xmlns:StandardProfile="http://www.omg.org/spec/UML/20131001/StandardProfile"
          xmlns:sysml="http://www.omg.org/spec/SysML/20181001/SysML"
          xmlns:uml="http://www.omg.org/spec/UML/20131001"
          xmlns:xmi="http://www.omg.org/spec/XMI/20131001">
   <xmi:documentation xmi:type="xmi:Documentation">
      <xmi:exporter>{XMI_EXPORTER_NAME}</xmi:exporter>
      <xmi:exporterVersion>{XMI_EXPORTER_VERSION}</xmi:exporterVersion>
   </xmi:documentation>
   <uml:Model xmi:type="uml:Model" xmi:id="model_root_element" name="{XMI_MODEL_NAME}">
      <packagedElement xmi:type="uml:Package" xmi:id="package_main_requirements" name="{XMI_PACKAGE_NAME}">
{uml_classes.rstrip()}      </packagedElement>
      <profileApplication xmi:type="uml:ProfileApplication" xmi:id="profile_application_sysml">
         <appliedProfile href="{SYSML_PROFILE_URL}"/>
      </profileApplication>
   </uml:Model>
   
{sysml_requirements.rstrip()}
</xmi:XMI>
'''
    
    return xmi_output


def convert_xmi_to_simple_xml(xmi_string):
    """
    将XMI格式转换为简单XML格式
    
    参数：
        xmi_string: XMI格式的XML字符串
    
    返回：
        简单XML格式字符串（<requirements>格式）
    """
    try:
        root = ET.fromstring(xmi_string)
    except ET.ParseError as e:
        raise ValueError(f"XMI解析错误: {e}")
    
    # 定义命名空间
    namespaces = {
        'xmi': 'http://www.omg.org/spec/XMI/20131001',
        'uml': 'http://www.omg.org/spec/UML/20131001',
        'sysml': 'http://www.omg.org/spec/SysML/20181001/SysML'
    }
    
    # XML反转义函数
    def unescape_xml(text):
        if not text:
            return ""
        text = str(text)
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&apos;', "'")
        return text

    # XML转义函数
    def escape_xml(text):
        if not text:
            return ""
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&apos;')
        return text
    
    # 提取所有SysML需求映射
    requirements_map = {}
    for req in root.findall('.//sysml:Requirement', namespaces):
        base_class = req.get('base_Class', '')
        req_id = req.get('Id', '')
        req_text = req.get('Text', '')
        requirements_map[base_class] = {'id': req_id, 'text': unescape_xml(req_text)}
    
    # 递归构建requirement XML
    def build_requirement_xml(class_elem, indent_level=1):
        class_id = class_elem.get('{http://www.omg.org/spec/XMI/20131001}id', '')
        class_name = unescape_xml(class_elem.get('name', ''))
        
        # 从requirements_map获取需求信息
        req_info = requirements_map.get(class_id, {'id': '', 'text': ''})
        req_id = req_info['id']
        req_text = req_info['text']
        
        indent = '    ' * indent_level
        
        # 查找嵌套分类器
        nested_classifiers = class_elem.findall('nestedClassifier', namespaces)
        nested_class_items = [nc for nc in nested_classifiers 
                              if nc.get('{http://www.omg.org/spec/XMI/20131001}type') == 'uml:Class']
        
        escaped_id = escape_xml(req_id)
        escaped_name = escape_xml(class_name)
        escaped_text = escape_xml(req_text)

        if not nested_class_items:
            # 叶子节点
            return f'{indent}<requirement id="{escaped_id}" name="{escaped_name}" text="{escaped_text}" />\n'
        else:
            # 有子节点的节点
            result = f'{indent}<requirement id="{escaped_id}" name="{escaped_name}" text="{escaped_text}">\n'
            for nested in nested_class_items:
                result += build_requirement_xml(nested, indent_level + 1)
            result += f'{indent}</requirement>\n'
            return result
    
    # 查找主包中的所有顶级类
    simple_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<requirements>\n'
    
    model = root.find('.//uml:Model', namespaces)
    if model is not None:
        package = model.find('.//packagedElement[@{http://www.omg.org/spec/XMI/20131001}type="uml:Package"]', namespaces)
        if package is not None:
            for packaged_elem in package.findall('packagedElement', namespaces):
                if packaged_elem.get('{http://www.omg.org/spec/XMI/20131001}type') == 'uml:Class':
                    simple_xml += build_requirement_xml(packaged_elem)
    
    simple_xml += '</requirements>'
    
    return simple_xml


def parse_xmi_to_tree_data(xmi_string):
    """
    从XMI格式解析为树状数据结构
    
    参数：
        xmi_string: XMI格式的XML字符串
    
    返回：
        树状数据列表：[{'id': '', 'name': '', 'text': '', 'children': [...]}]
    """
    try:
        root = ET.fromstring(xmi_string)
    except ET.ParseError as e:
        raise ValueError(f"XMI解析错误: {e}")
    
    # 定义命名空间
    namespaces = {
        'xmi': 'http://www.omg.org/spec/XMI/20131001',
        'uml': 'http://www.omg.org/spec/UML/20131001',
        'sysml': 'http://www.omg.org/spec/SysML/20181001/SysML'
    }
    
    # 提取所有SysML需求信息
    requirements_map = {}
    for req in root.findall('.//sysml:Requirement', namespaces):
        base_class = req.get('base_Class', '')
        req_id = req.get('Id', '')
        req_text = req.get('Text', '')
        requirements_map[base_class] = {'id': req_id, 'text': req_text}
    
    # 递归解析UML类结构
    def parse_uml_class(class_element):
        class_id = class_element.get('{http://www.omg.org/spec/XMI/20131001}id', '')
        class_name = class_element.get('name', '')
        
        # 从requirements_map获取需求信息
        req_info = requirements_map.get(class_id, {'id': '', 'text': ''})
        
        node = {
            'id': req_info['id'],
            'name': class_name,
            'text': req_info['text'],
            'children': []
        }
        
        # 递归处理嵌套分类器
        for nested in class_element.findall('nestedClassifier', namespaces):
            if nested.get('{http://www.omg.org/spec/XMI/20131001}type') == 'uml:Class':
                node['children'].append(parse_uml_class(nested))
        
        return node
    
    # 查找主包中的所有顶级类
    tree_data = []
    model = root.find('.//uml:Model', namespaces)
    if model is not None:
        package = model.find('.//packagedElement[@{http://www.omg.org/spec/XMI/20131001}type="uml:Package"]', namespaces)
        if package is not None:
            for packaged_elem in package.findall('packagedElement', namespaces):
                if packaged_elem.get('{http://www.omg.org/spec/XMI/20131001}type') == 'uml:Class':
                    tree_data.append(parse_uml_class(packaged_elem))
    
    return tree_data


def load_xml_file(file_path):
    """
    从文件加载XML内容
    
    参数：
        file_path: XML文件路径
    
    返回：
        XML字符串或错误信息
    """
    try:
        if not os.path.exists(file_path):
            return f"错误: 文件不存在: {file_path}"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content
    except Exception as e:
        return f"错误: 读取文件失败: {e}"


def save_xmi_file(xmi_string, file_path):
    """
    保存XMI字符串到文件
    
    参数：
        xmi_string: XMI格式的XML字符串
        file_path: 目标文件路径
    
    返回：
        bool: 成功返回True，失败返回False
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(xmi_string)
        return True
    except Exception as e:
        print(f"保存XMI文件失败: {e}")
        return False


def smart_chunk_text(text, max_chunk_size):
    """
    智能文本分段：避免在关键地方（如句子中间、数字/小数点中间）截断。
    优先在段落/换行、句号、问号、叹号等标点处切分。
    """
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]
        
    chunks = []
    start = 0
    total_len = len(text)
    
    # 优先使用的分隔符列表，按照优先级从高到低排序
    delimiters = ['。', '\n\n', '\n', '.', '？', '?', '！', '!', '；', ';']
    
    while start < total_len:
        # 如果剩下部分不足以构成一个最大分段，则直接作为最后一段
        if start + max_chunk_size >= total_len:
            chunks.append(text[start:])
            break
            
        target = start + max_chunk_size
        
        # 寻找切分点。我们在 target 的前后寻找最合适的分隔符。
        # 搜索范围限制为 target 前后不超过 max_chunk_size // 4，最小为 50 个字符。
        search_back = max(50, max_chunk_size // 4)
        search_forward = max(50, max_chunk_size // 4)
        
        min_idx = max(start + 1, target - search_back)
        max_idx = min(total_len - 1, target + search_forward)
        
        split_idx = -1
        found = False
        
        # 遍历分隔符，按优先级进行匹配
        for delim in delimiters:
            best_pos = -1
            min_dist = float('inf')
            
            # 在可能包含该分隔符的区域内搜索
            sub_start = max(start, min_idx - len(delim))
            sub_end = min(total_len, max_idx + len(delim))
            sub_text = text[sub_start:sub_end]
            
            pos = sub_text.find(delim)
            while pos != -1:
                actual_pos = sub_start + pos
                candidate_split = actual_pos + len(delim)
                
                # 检查切分点是否在允许的窗口内
                if min_idx <= candidate_split <= max_idx:
                    # 避免在小数点/数字中切分 (例如 "3.14")
                    is_valid = True
                    if delim == '.' or delim == '。':
                        if actual_pos > 0 and actual_pos < total_len - 1:
                            if text[actual_pos - 1].isdigit() and text[actual_pos + 1].isdigit():
                                is_valid = False
                                
                    if is_valid:
                        # 倾向于靠近 target 的位置
                        dist = abs(candidate_split - target)
                        if dist < min_dist:
                            min_dist = dist
                            best_pos = candidate_split
                            
                pos = sub_text.find(delim, pos + 1)
                
            if best_pos != -1:
                split_idx = best_pos
                found = True
                break
                
        # 如果没有找到高优先级的分隔符，则寻找空格
        if not found:
            best_pos = -1
            min_dist = float('inf')
            sub_start = max(start, min_idx - 1)
            sub_end = min(total_len, max_idx + 1)
            sub_text = text[sub_start:sub_end]
            
            pos = sub_text.find(' ')
            while pos != -1:
                actual_pos = sub_start + pos
                candidate_split = actual_pos + 1
                if min_idx <= candidate_split <= max_idx:
                    dist = abs(candidate_split - target)
                    if dist < min_dist:
                        min_dist = dist
                        best_pos = candidate_split
                pos = sub_text.find(' ', pos + 1)
                
            if best_pos != -1:
                split_idx = best_pos
            else:
                # 实在找不到，就在 target 处强行切分
                split_idx = target
                
        # 截取该分段并去除首尾空白
        chunk = text[start:split_idx].strip()
        if chunk:
            chunks.append(chunk)
        start = split_idx
        
    return chunks

