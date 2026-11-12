import json
import os

configs = {}
configs_path = {}
configs_schema = {}


def read(path, schema, call_name=None):
    path = str(path)

    default_data = _generate_default(schema)
    if not os.path.exists(path):
        dir_path = os.path.dirname(path)
        os.makedirs(dir_path, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(default_data, file, indent=4, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"默认文件写入失败：{e}")

    data = read_json(path, schema)

    if call_name is not None:
        global configs, configs_path, configs_schema
        configs[call_name] = data
        configs_path[call_name] = path
        configs_schema[call_name] = schema

    return data


def save(call_name):
    path = configs_path[call_name]
    schema = configs_schema[call_name]
    content = configs[call_name]

    try:
        _validate_json(content, schema)
    except Exception as e:
        raise Exception(f"保存数据格式错误：{e}")

    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(content, file, indent=4, ensure_ascii=False)
    except Exception as e:
        raise Exception(f"JSON 文件写入失败：{e}")


def read_default(path, schema, call_name=None):
    data = _generate_default(schema)

    if call_name is not None:
        global configs, configs_path, configs_schema
        configs[call_name] = data
        configs_path[call_name] = path
        configs_schema[call_name] = schema

    return data


def read_json(json_path, schema):
    json_path = str(json_path)

    try:
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as e:
        raise Exception(f"JSON 文件读取错误：{e}")

    try:
        _validate_json(data, schema)
    except Exception as e:
        raise Exception(f"JSON 文件格式错误：{e}")

    return data


def _generate_default(schema):
    schema_type = schema["type"]
    if schema_type == list:
        return schema.get("default", [])
    if schema_type != dict:
        return schema["default"]

    schema_required = schema["required"]
    schema_properties = schema["properties"]
    obj = {}
    for required in schema_required:
        obj[required] = _generate_default(schema_properties[required])

    return obj


def _validate_json(value, schema, path="root"):
    expected_type = schema["type"]

    if not isinstance(value, expected_type):
        raise Exception(f"{path} 类型错误：应为 {expected_type.__name__}，实际是 {type(value).__name__}")

    if expected_type == dict:
        properties = schema["properties"]
        required = schema["required"]

        for key in required:
            if key not in value:
                raise Exception(f"{path} 缺少必填字段：{key}")

        for key, sub_schema in properties.items():
            if key in value:
                _validate_json(value[key], sub_schema, path=f"{path}.{key}")

    elif expected_type == list:
        length = schema.get("length", None)
        min_length = schema.get("min_length", None)
        max_length = schema.get("max_length", None)
        list_length = len(value)
        if length is not None:
            if list_length != length:
                raise Exception(f"{path} 列表长度不符合要求：要求长度为 {length}，实际是 {list_length}")
        else:
            if min_length is not None and list_length < min_length:
                raise Exception(f"{path} 列表长度不符合要求：最小长度为 {min_length}，实际是 {list_length}")
            if max_length is not None and list_length > max_length:
                raise Exception(f"{path} 列表长度不符合要求：最大长度为 {max_length}，实际是 {list_length}")

        items_schema = schema["items"]
        if items_schema:
            for i, item in enumerate(value):
                _validate_json(item, items_schema, path=f"{path}[{i}]")

    elif expected_type == str:
        allowed_value = schema.get("allowed_value", None)
        length = schema.get("length", None)
        min_length = schema.get("min_length", None)
        max_length = schema.get("max_length", None)
        str_length = len(value)
        if allowed_value is not None:
            if value not in allowed_value:
                value_display = "、".join(allowed_value)
                raise Exception(f"{path} 字符串仅允许 {value_display}，实际是 {value}")
        elif length is not None:
            if str_length != length:
                raise Exception(f"{path} 字符串长度不符合要求：要求长度为 {length}，实际是 {str_length}")
        else:
            if min_length is not None and str_length < min_length:
                raise Exception(f"{path} 字符串长度不符合要求：最小长度为 {min_length}，实际是 {str_length}")
            if max_length is not None and str_length > max_length:
                raise Exception(f"{path} 字符串长度不符合要求：最大长度为 {max_length}，实际是 {str_length}")

    elif expected_type == int:
        min_value = schema.get("min_value", None)
        max_value = schema.get("max_value", None)
        if min_value is not None and value < min_value:
            raise Exception(f"{path} 整数值不符合要求：最小值为 {min_value}，实际是 {value}")
        if max_value is not None and value > max_value:
            raise Exception(f"{path} 整数值不符合要求：最大值为 {max_value}，实际是 {value}")

    validator = schema.get("validator", None)
    if validator:
        try:
            validator(value)
        except Exception as e:
            raise Exception(f"{path} 不符合要求：{e}")
