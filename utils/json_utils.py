import json
import re

def clean_model_output(raw_output):
    """
    清理模型输出，移除思考过程，只保留JSON结果，并修复常见的JSON格式问题
    """
    print(f"\n=== JSON清理过程调试 ===")
    print(f"原始输出长度: {len(raw_output)}")

    cleaned = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # 兼容畸形思考标签，如 <\think>、</ think>
    cleaned = re.sub(r'<\s*\\\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\s*/\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\s*(think|thinking)\s*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'思考过程：.*?(?=\[|\{)', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'分析：.*?(?=\[|\{)', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()

    # Remove markdown code block delimiters if present around the JSON
    cleaned = re.sub(r'^```(?:json|xml)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)

    # Check if it looks like XML
    if cleaned.startswith('<') and '>' in cleaned:
        print("检测到XML内容，跳过JSON修复")
        return cleaned

    json_patterns = [r'\[.*\]', r'\{.*\}']
    for pattern in json_patterns:
        match = re.search(pattern, cleaned, flags=re.DOTALL)
        if match:
            potential_json = match.group().strip()
            print(f"找到潜在JSON，长度: {len(potential_json)}")

            # 检查原始JSON的第一个对象的字段顺序
            try:
                original_data = json.loads(potential_json)
                if isinstance(original_data, list) and len(original_data) > 0:
                    print(f"原始JSON第一项键顺序: {list(original_data[0].keys())}")
            except:
                print("原始JSON解析失败，需要修复")

            # Try to fix common issues before returning
            fixed_json = fix_json_format(potential_json)

            # 检查修复后JSON的第一个对象的字段顺序
            try:
                fixed_data = json.loads(fixed_json)
                if isinstance(fixed_data, list) and len(fixed_data) > 0:
                    print(f"修复后JSON第一项键顺序: {list(fixed_data[0].keys())}")
            except:
                print("修复后JSON解析失败")

            try:
                json.loads(fixed_json) # Test if it's valid JSON
                print("返回修复后的JSON")
                return fixed_json # Return the fixed version if it parses
            except json.JSONDecodeError:
                try:
                    json.loads(potential_json) # Test original potential JSON
                    print("返回原始JSON")
                    return potential_json # Return original if it parses and fix failed or was not needed
                except json.JSONDecodeError:
                    # If both fail, continue to see if other patterns match or return the cleaned non-JSON
                    continue
    print("使用通用修复")
    return fix_json_format(cleaned) # Return the generally cleaned and fixed string if no clear JSON block was parsed by json.loads

def fix_json_format(json_str):
    """修复常见的JSON格式问题"""
    print(f"开始修复JSON格式，输入长度: {len(json_str)}")

    # 检查修复前的字段顺序
    try:
        original_data = json.loads(json_str)
        if isinstance(original_data, list) and len(original_data) > 0:
            print(f"修复前第一项键顺序: {list(original_data[0].keys())}")
    except:
        print("修复前JSON无法解析，需要修复")

    fixes = [
        (r'(\d+(?:\.\d+)?)亿欧元', r'"\1亿欧元"'), (r'(\d+(?:\.\d+)?)万欧元', r'"\1万欧元"'),
        (r'(\d+(?:\.\d+)?)亿美元', r'"\1亿美元"'), (r'(\d+(?:\.\d+)?)万美元', r'"\1万美元"'),
        (r'(\d+(?:\.\d+)?)亿元', r'"\1亿元"'), (r'(\d+(?:\.\d+)?)万元', r'"\1万元"'),
        (r'(\d+(?:\.\d+)?)%', r'"\1%"'),
        (r'(\d+(?:\.\d+)?)万台', r'"\1万台"'), (r'(\d+(?:\.\d+)?)万件', r'"\1万件"'),
        (r'(\d+(?:\.\d+)?)万人', r'"\1万人"'), (r'(\d+(?:\.\d+)?)万吨', r'"\1万吨"'),
        (r'(\d+(?:\.\d+)?)万公里', r'"\1万公里"'), (r'(\d+(?:\.\d+)?)万平方米', r'"\1万平方米"'),
        (r'([{,]\s*)([^"{\[\],}\s]+)(\s*:)', r'\1"\2"\3'), # Add quotes to unquoted keys
        (r'"(\d+(?:\.\d+)?)%"', r'\1%')
    ]
    result = json_str
    for i, (pattern, replacement) in enumerate(fixes):
        old_result = result
        result = re.sub(pattern, replacement, result)
        if old_result != result:
            print(f"应用修复规则 {i+1}: {pattern[:30]}...")

    # Attempt to fix trailing commas before closing bracket/brace
    old_result = result
    result = re.sub(r',(\s*[}\]])', r'\1', result)
    if old_result != result:
        print("移除了尾随逗号")

    # Attempt to fix unquoted string values if they look simple (no spaces, not objects/arrays)
    # This is more risky, be careful: ': value' -> ': "value"'
    old_result = result
    result = re.sub(r':\s*([^"\[\{\s][^",}\]]*[^",}\]\s])\s*([,}\]])', r': "\1"\2', result)
    if old_result != result:
        print("为未加引号的值添加了引号")

    # 检查修复后的字段顺序
    try:
        fixed_data = json.loads(result)
        if isinstance(fixed_data, list) and len(fixed_data) > 0:
            print(f"修复后第一项键顺序: {list(fixed_data[0].keys())}")
    except:
        print("修复后JSON仍无法解析")

    print("JSON格式修复完成")
    return result