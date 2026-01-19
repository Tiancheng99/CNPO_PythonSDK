
import json
from datetime import datetime

def get_joint_index(joint_name:str):
    return int(joint_name[1:])

def obj_to_dict(obj):
    # 如果对象有 to_dict 方法，直接调用
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    # 如果是字典，递归处理每个键值对
    elif isinstance(obj, dict):
        return {k: obj_to_dict(v) for k, v in obj.items()}
    # 如果是列表或元组，递归处理每个元素
    elif isinstance(obj, (list, tuple)):
        return [obj_to_dict(item) for item in obj]
    # 如果是自定义对象，获取其属性并递归处理
    elif hasattr(obj, "__dict__"):
        return {k: obj_to_dict(v) for k, v in vars(obj).items()}
    # 如果是基本类型（如字符串、数字），直接返回
    else:
        return obj
    



def print_object(obj, indent=0):
    # 如果是基本类型（如字符串、数字），直接打印
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        print(" " * indent + str(obj))
    # 如果是字典，遍历键值对
    elif isinstance(obj, dict):
        for key, value in obj.items():
            print(" " * indent + f"{key}:")
            print_object(value, indent + 4)
    # 如果是列表或元组，遍历元素
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            print_object(item, indent + 4)
    # 如果是对象，遍历其属性
    else:
        for attr in dir(obj):
            # 过滤掉特殊方法
            if not attr.startswith("__"):
                try:
                    value = getattr(obj, attr)
                    print(" " * indent + f"{attr}:")
                    print_object(value, indent + 4)
                except Exception as e:
                    print(" " * indent + f"{attr}: <无法获取值>")



def transform_json(input_json):
    # 提取 jointPositions
    joint_positions = {
        "J1": input_json["Joints"]["J1"]["ActualPosition"],
        "J2": input_json["Joints"]["J2"]["ActualPosition"],
        "J3": input_json["Joints"]["J3"]["ActualPosition"],
        "J4": input_json["Joints"]["J4"]["ActualPosition"],
        "J5": input_json["Joints"]["J5"]["ActualPosition"],
        "J6": input_json["Joints"]["J6"]["ActualPosition"],
    }

    pose = {
        "x": input_json["TcpPose"]["X"],
        "y": input_json["TcpPose"]["Y"],
        "z": input_json["TcpPose"]["Z"],
        "roll": input_json["TcpPose"]["Roll"],
        "pitch": input_json["TcpPose"]["Pitch"],
        "yaw": input_json["TcpPose"]["Yaw"],
    }

    # 提取 isEnabled 和 isMoving
    is_enabled = input_json["Manage"]["Enabled"]
    is_moving = input_json["Manage"]["Moving"]
    
    airlock = input_json["AirLock"]

    # 添加 timestamp
    timestamp = datetime.now().isoformat()

    # 构建目标 JSON
    output_json = {
        "jointPositions": joint_positions,
        "pose": pose,
        "isEnabled": is_enabled,
        "isMoving": is_moving,
        "timestamp": timestamp,
        "airlock": airlock
    }

    return output_json
