import numpy as np
from typing import List, Dict, Optional
import json
from enum import Enum

class RobotParameters:
    def __init__(self, json_file: str):
        """从JSON字典初始化机器人参数"""
        # 读取JSON文件
        json_data = self._load_json_file(json_file)

        # DH参数（6个关节，每个关节4个参数）
        self.DH_Parameters = json_data.get("DHParameters", [])
        self._validate_dh_parameters()  # 校验为6x4数组

        # 校准关节位置（6个关节的校准位置）
        self.CalibrationJointPositions = self._get_array_param(json_data, "CalibrationJointPositions", 6, 0.0)

        # 运动模式（整数枚举，对应ControlMode）
        self.MovementMode = int(json_data.get("MovementMode", 0))

        # 速度倍率（0-1.0，用于缩放所有运动速度）
        self.Override = float(json_data.get("Override", 1.0))

        # 关节点动速度（6个关节）
        self.JointJogVelocity = self._get_array_param(json_data, "JointJogVelocity", 6, 0.1)

        # 关节点动增量距离（6个关节）
        self.InchDistance = self._get_array_param(json_data, "InchDistance", 6, 1.0)

        # 关节目标位置（6个关节）
        self.JointTargetPosition = self._get_array_param(json_data, "JointTargetPosition", 6, 0.0)

        # 关节参考速度（6个关节）
        self.JointReferenceVelocity = self._get_array_param(json_data, "JointReferenceVelocity", 6, 3.0)

        # 关节参考加速度（6个关节）
        self.JointReferenceAcceleration = self._get_array_param(json_data, "JointReferenceAcceleration", 6, 10.0)

        # 关节参考加加速度（6个关节）
        self.JointReferenceJerk = self._get_array_param(json_data, "JointReferenceJerk", 6, 10.0)

        # MoveJ（关节空间运动）参数
        self.MoveJReferenceVelocity = float(json_data.get("MoveJReferenceVelocity", 0.1))
        self.MoveJReferenceAcceleration = float(json_data.get("MoveJReferenceAcceleration", 1.0))
        self.MoveJReferenceDeceleration = float(json_data.get("MoveJReferenceDeceleration", 1.0))

        # TCP（工具坐标系）点动参数
        # TCP点动线速度
        self.TCPJogLinearVelocity = float(json_data.get("TCPJogLinearVelocity", 3.0))
        # TCP点动角速度
        self.TCPJogAngularVelocity = float(json_data.get("TCPJogAngularVelocity", 0.1))
        # TCP点动增量距离
        self.TCPInchDistance = float(json_data.get("TCPInchDistance", 1.0))

        # TCP目标与中间点参数，TCP目标位姿（X,Y,Z,Roll,Pitch,Yaw）
        self.TCPTargetPose = self._get_array_param(json_data, "TCPTargetPose", 6, 0.0)

        # TCP中间点位姿（路径规划用）
        self.TCPMidPose = self._get_array_param(json_data, "TCPMidPose", 6, 0.0)

        # TCP相对位移（用于相对运动）
        self.TCPRelativeDistance = self._get_array_param(json_data, "TCPRelativeDistance", 6, 0.0)

        # TCP（线性运动）参考参数
        self.TCPReferenceLinearVelocity = float(json_data.get("TCPReferenceLinearVelocity", 20.0))
        self.TCPReferenceLinearAcceleration = float(json_data.get("TCPReferenceLinearAcceleration", 20.0))
        self.TCPReferenceLinearDeceleration = float(json_data.get("TCPReferenceLinearDeceleration", 20.0))
        self.TCPReferenceAngularVelocity = float(json_data.get("TCPReferenceAngularVelocity", 1.0))
        self.TCPReferenceAngularAcceleration = float(json_data.get("TCPReferenceAngularAcceleration", 10.0))
        self.TCPReferenceAngularDeceleration = float(json_data.get("TCPReferenceAngularDeceleration", 10.0))

        # TCP速度控制参数，TCP目标速度向量（vx, vy, vz, vRoll, vPitch, vYaw）
        self.TCPTargetVelocity = self._get_array_param(json_data, "TCPTargetVelocity", 6, 0.0)

        # 阻抗控制参数（M:质量, K:刚度, B:阻尼）
        self.AdmittanceControlM = self._get_array_param(json_data, "AdmittanceControlM", 6, 1.0)
        self.AdmittanceControlK = self._get_array_param(json_data, "AdmittanceControlK", 6, 1.0)
        self.AdmittanceControlB = self._get_array_param(json_data, "AdmittanceControlB", 6, 1.0)

        # 工具参数，工具尖端位姿（相对于法兰，X,Y,Z,Roll,Pitch,Yaw）
        self.Tip = self._get_array_param(json_data, "Tip", 6, 0.0)

        # 负载质量（kg）
        self.LoadMass = float(json_data.get("LoadMass", 0.0))

        # 负载质心（相对于工具尖端，X,Y,Z）
        self.LoadCOG = self._get_array_param(json_data, "LoadCOG", 3, 0.0)

    def _load_json_file(self, json_file: str) -> dict:
        """
        读取JSON文件并解析为字典
        :param json_file: JSON文件路径（相对或绝对路径）
        :return: 解析后的字典
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                return json.load(f)  # 解析JSON内容为字典
        except FileNotFoundError:
            raise FileNotFoundError(f"JSON文件不存在：{json_file}（请检查路径是否正确）")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON文件格式错误：{e}（请检查文件内容是否符合JSON规范）")
        except Exception as e:
            raise RuntimeError(f"读取JSON文件失败：{e}")

    # 辅助方法：参数校验与补全
    def _validate_dh_parameters(self):
        """校验并补全DH参数为6x4的格式"""
        valid_dh = []
        for i in range(6):  # 6个关节
            if i < len(self.DH_Parameters):
                joint_params = self.DH_Parameters[i]
                valid_joint = [float(joint_params[j]) if j < len(joint_params) else 0.0 for j in range(4)]
            else:
                valid_joint = [0.0, 0.0, 0.0, 0.0]
            valid_dh.append(valid_joint)
        self.DH_Parameters = valid_dh

    def _get_array_param(self, json_data: dict, key: str, length: int, default_val: float) -> list:
        """
        通用数组参数获取方法：确保数组长度为length，不足则补默认值
        :param json_data: JSON字典
        :param key: 字段名
        :param length: 期望长度
        :param default_val: 默认值
        :return: 补全后的数组
        """
        arr = json_data.get(key, [])
        valid_arr = []
        for i in range(length):
            if i < len(arr):
                valid_arr.append(float(arr[i]))  # 强制转为float，避免类型错误
            else:
                valid_arr.append(default_val)
        return valid_arr
    
    
class ControlMode(Enum):
    """控制模式枚举"""
    Calibration = 0
    JointJog = 1
    JointInch = 2
    JointMoveAbs = 3
    MoveJoint = 4
    MoveLinear = 5
    MoveCircle = 6
    TcpJog = 7
    TcpInch = 8


class JogMode(Enum):
    """点动模式枚举"""
    VelocityJog = 0  # 速度模式点动
    DistanceJog = 1  # 距离模式点动


class TcpMoveRelType(Enum):
    """TCP相对运动类型枚举"""
    Rotation = 0  # 旋转
    Translation = 1  # 平移


class JointStatus:
    """单个关节的状态"""
    def __init__(self, json_data: Dict):
        self.ActualPosition = float(json_data.get("ActualPosition", 0.0))  # 实际位置
        self.ActualVelocity = float(json_data.get("ActualVelocity", 0.0))  # 实际速度
        self.ActualAcceleration = float(json_data.get("ActualAcceleration", 0.0))  # 实际加速度
        self.ActualCurrent = float(json_data.get("ActualCurrent", 0.0))  # 实际电流
        self.Statusof402 = int(json_data.get("Statusof402", 1))  # 402协议状态码


class JointsStatus:
    """所有关节的状态集合"""
    def __init__(self, json_data: Dict):
        # 解析J1-J6的状态
        self.J1 = JointStatus(json_data.get("J1", {}))
        self.J2 = JointStatus(json_data.get("J2", {}))
        self.J3 = JointStatus(json_data.get("J3", {}))
        self.J4 = JointStatus(json_data.get("J4", {}))
        self.J5 = JointStatus(json_data.get("J5", {}))
        self.J6 = JointStatus(json_data.get("J6", {}))

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "J1": {"ActualPosition": self.J1.ActualPosition, "ActualVelocity": self.J1.ActualVelocity,
                   "ActualAcceleration": self.J1.ActualAcceleration, "ActualCurrent": self.J1.ActualCurrent,
                   "Statusof402": self.J1.Statusof402},
            "J2": {"ActualPosition": self.J2.ActualPosition, "ActualVelocity": self.J2.ActualVelocity,
                   "ActualAcceleration": self.J2.ActualAcceleration, "ActualCurrent": self.J2.ActualCurrent,
                   "Statusof402": self.J2.Statusof402},
            "J3": {"ActualPosition": self.J3.ActualPosition, "ActualVelocity": self.J3.ActualVelocity,
                   "ActualAcceleration": self.J3.ActualAcceleration, "ActualCurrent": self.J3.ActualCurrent,
                   "Statusof402": self.J3.Statusof402},
            "J4": {"ActualPosition": self.J4.ActualPosition, "ActualVelocity": self.J4.ActualVelocity,
                   "ActualAcceleration": self.J4.ActualAcceleration, "ActualCurrent": self.J4.ActualCurrent,
                   "Statusof402": self.J4.Statusof402},
            "J5": {"ActualPosition": self.J5.ActualPosition, "ActualVelocity": self.J5.ActualVelocity,
                   "ActualAcceleration": self.J5.ActualAcceleration, "ActualCurrent": self.J5.ActualCurrent,
                   "Statusof402": self.J5.Statusof402},
            "J6": {"ActualPosition": self.J6.ActualPosition, "ActualVelocity": self.J6.ActualVelocity,
                   "ActualAcceleration": self.J6.ActualAcceleration, "ActualCurrent": self.J6.ActualCurrent,
                   "Statusof402": self.J6.Statusof402}
        }


class PoseStatus:
    """位姿状态"""
    def __init__(self, json_data: Dict):
        self.X = float(json_data.get("X", 0.0))  # X坐标
        self.Y = float(json_data.get("Y", 0.0))  # Y坐标
        self.Z = float(json_data.get("Z", 0.0))  # Z坐标
        self.Roll = float(json_data.get("Roll", 0.0))  # 滚转角
        self.Pitch = float(json_data.get("Pitch", 0.0))  # 俯仰角
        self.Yaw = float(json_data.get("Yaw", 0.0))  # 偏航角

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "X": self.X, "Y": self.Y, "Z": self.Z,
            "Roll": self.Roll, "Pitch": self.Pitch, "Yaw": self.Yaw
        }


class ManageStatus:
    """管理状态"""
    def __init__(self, json_data: Dict):
        self.Initialized = bool(json_data.get("Initialized", False))  # 是否初始化
        self.Enabled = bool(json_data.get("Enabled", False))  # 是否使能
        self.Moving = bool(json_data.get("Moving", False))  # 是否运动中
        self.Error = bool(json_data.get("Error", False))  # 是否有错误
        self.ErrorID = json_data.get("ErrorID", False)  # 错误ID（可能是bool或int，保持原类型）
        self.Mode = int(json_data.get("Mode", 0))  # 当前模式（对应ControlMode枚举值）

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "Initialized": self.Initialized, "Enabled": self.Enabled, "Moving": self.Moving,
            "Error": self.Error, "ErrorID": self.ErrorID, "Mode": self.Mode
        }


class RobotStatus:
    """完整机器人状态"""
    def __init__(self, json_data: Dict):
        # 解析关节状态
        self.Joints = JointsStatus(json_data.get("Joints", {}))
        # 解析法兰位姿（工具安装法兰的位姿）
        self.FlangePose = PoseStatus(json_data.get("FlangePose", {}))
        # 解析TCP位姿（工具末端位姿）
        self.TcpPose = PoseStatus(json_data.get("TcpPose", {}))
        # 解析管理状态
        self.Manage = ManageStatus(json_data.get("Manage", {}))

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "Joints": self.Joints.to_dict(),
            "FlangePose": self.FlangePose.to_dict(),
            "TcpPose": self.TcpPose.to_dict(),
            "Manage": self.Manage.to_dict()
        }




class Utils:
    @staticmethod
    def caculate_joints_error(target_joints, actual_joints):
        distance = 0
        for i in range(len(target_joints)):
            distance += (target_joints[i] - actual_joints[i]) ** 2
        return distance ** 0.5
    
    @staticmethod
    def caculate_cartesian_error(target_pose, actual_pose):
        position_error = 0
        rotation_error = 0
        for i in range(0,3):
            position_error += (target_pose[i] - actual_pose[i]) ** 2

        # 旋转误差改为角轴夹角
        rotation_error = Utils.rpy_angle_between(target_pose[3:6], actual_pose[3:6])
        return (position_error ** 0.5, rotation_error)
    
    @staticmethod
    def rpy_angle_between(rpy1, rpy2):
        # 将RPY转为旋转矩阵
        T1 = Utils.pose_to_T([0, 0, 0] + list(rpy1))
        T2 = Utils.pose_to_T([0, 0, 0] + list(rpy2))
        R1 = T1[0:3, 0:3]
        R2 = T2[0:3, 0:3]
        # 计算相对旋转矩阵
        R_rel = R1.T @ R2
        # 提取角轴夹角
        trace = np.trace(R_rel)
        arg = (trace - 1.0) / 2.0
        arg = np.clip(arg, -1.0, 1.0)
        theta = np.arccos(arg)
        return theta * 180.0 / np.pi  # 返回角度

    @staticmethod
    def Calculate_Tcp_targetPose(type:TcpMoveRelType, TcpPositions, T0, start_Pose):
        if type == TcpMoveRelType.Rotation:
            vector3D = TcpPositions[3:6]
            ux,uy,uz,theta = Utils.Calculate_AxisAngle(vector3D)
            # 计算三角函数值
            cos_theta = np.cos(theta)
            sin_theta = np.sin(theta)
            one_minus_cos = 1 - cos_theta

            # 构建旋转矩阵
            R_tcp = np.zeros((3, 3))

            R_tcp[0, 0] = cos_theta + ux * ux * one_minus_cos
            R_tcp[0, 1] = ux * uy * one_minus_cos - uz * sin_theta
            R_tcp[0, 2] = ux * uz * one_minus_cos + uy * sin_theta

            R_tcp[1, 0] = uy * ux * one_minus_cos + uz * sin_theta
            R_tcp[1, 1] = cos_theta + uy * uy * one_minus_cos
            R_tcp[1, 2] = uy * uz * one_minus_cos - ux * sin_theta

            R_tcp[2, 0] = uz * ux * one_minus_cos - uy * sin_theta
            R_tcp[2, 1] = uz * uy * one_minus_cos + ux * sin_theta
            R_tcp[2, 2] = cos_theta + uz * uz * one_minus_cos

            start_R = T0[0:3,0:3]
            R_target = start_R@R_tcp
            target_Roll,target_Pitch,target_Yaw = Utils.Rotm_to_RPY(R_target)
            target_pose = [T0[0,3], T0[1,3], T0[2,3],target_Roll,target_Pitch,target_Yaw]
            return target_pose
        elif type == TcpMoveRelType.Translation:
            vector3D = TcpPositions[0:3]
            norm = np.linalg.norm(vector3D)
            for i in range(0,3):
                vector3D[i] = vector3D[i]/norm
            vector3D = np.array(vector3D).reshape(-1,1)
            start_R = T0[0:3,0:3]
            vector_base = start_R@vector3D
            target_pose = [0]*6
            target_pose[0] = start_Pose[0]+norm*vector_base[0]
            target_pose[1] = start_Pose[1]+norm*vector_base[1]
            target_pose[2] = start_Pose[2]+norm*vector_base[2]
            target_pose[3] = start_Pose[3]
            target_pose[4] = start_Pose[4]
            target_pose[5] = start_Pose[5]
            return target_pose
        else:
            print("Type Error")

    @staticmethod
    def pose_to_T(pose):
        x=pose[0]
        y=pose[1]
        z=pose[2]
        Roll=pose[3]
        Pitch=pose[4]
        Yaw=pose[5]

        # 角度转弧度
        Roll_rad = Roll * np.pi / 180.0
        Pitch_rad = Pitch * np.pi / 180.0
        Yaw_rad = Yaw * np.pi / 180.0

        # 计算三角函数值
        cosRoll = np.cos(Roll_rad)
        sinRoll = np.sin(Roll_rad)
        cosPitch = np.cos(Pitch_rad)
        sinPitch = np.sin(Pitch_rad)
        cosYaw = np.cos(Yaw_rad)
        sinYaw = np.sin(Yaw_rad)

        # 构建旋转矩阵
        R = np.zeros((3, 3))
        R[0, 0] = cosYaw * cosPitch
        R[0, 1] = cosYaw * sinPitch * sinRoll - sinYaw * cosRoll
        R[0, 2] = cosYaw * sinPitch * cosRoll + sinYaw * sinRoll

        R[1, 0] = sinYaw * cosPitch
        R[1, 1] = sinYaw * sinPitch * sinRoll + cosYaw * cosRoll
        R[1, 2] = sinYaw * sinPitch * cosRoll - cosYaw * sinRoll

        R[2, 0] = -sinPitch
        R[2, 1] = cosPitch * sinRoll
        R[2, 2] = cosPitch * cosRoll

        T = np.eye(4)
        T[0:3,0:3] = R
        T[0:3,3] = [x,y,z]
        return T

    @staticmethod
    def Calculate_AxisAngle(vector):
        # 输入角度转换为弧度
        alpha = vector[0] * np.pi / 180.0
        beta = vector[1] * np.pi / 180.0
        gamma = vector[2] * np.pi / 180.0

        # 计算绕X轴的旋转矩阵Rx
        Rx = np.array([
            [1.0, 0.0, 0.0],
            [0.0, np.cos(alpha), -np.sin(alpha)],
            [0.0, np.sin(alpha), np.cos(alpha)]
        ])

        # 计算绕Y轴的旋转矩阵Ry
        Ry = np.array([
            [np.cos(beta), 0.0, np.sin(beta)],
            [0.0, 1.0, 0.0],
            [-np.sin(beta), 0.0, np.cos(beta)]
        ])

        # 计算绕Z轴的旋转矩阵Rz
        Rz = np.array([
            [np.cos(gamma), -np.sin(gamma), 0.0],
            [np.sin(gamma), np.cos(gamma), 0.0],
            [0.0, 0.0, 1.0]
        ])

        # 计算中间矩阵 R_temp = Ry * Rx
        R_temp = np.dot(Ry, Rx)

        # 计算总旋转矩阵 R_total = Rz * R_temp
        R_total = np.dot(Rz, R_temp)

        # 计算等效转角theta
        trace = np.trace(R_total)
        arg = (trace - 1.0) / 2.0

        # 处理浮点精度溢出
        arg = np.clip(arg, -1.0, 1.0)
        theta = np.arccos(arg)

        # 计算等效旋转轴
        if (theta > 1e-6) and (theta < np.pi - 1e-6):
            vector_x = (R_total[2, 1] - R_total[1, 2]) / (2.0 * np.sin(theta))
            vector_y = (R_total[0, 2] - R_total[2, 0]) / (2.0 * np.sin(theta))
            vector_z = (R_total[1, 0] - R_total[0, 1]) / (2.0 * np.sin(theta))

            # 归一化向量
            norm = np.linalg.norm([vector_x, vector_y, vector_z])
            if norm > 0.0:
                vector_x /= norm
                vector_y /= norm
                vector_z /= norm
            else:
                vector_x, vector_y, vector_z = 0.0, 0.0, 0.0
        else:
            # 处理0或π情况
            vector_x, vector_y, vector_z = 0.0, 0.0, 0.0
        return vector_x,vector_y,vector_z,theta

    @staticmethod
    def Rotm_to_RPY(Rotm):
        # 提取旋转矩阵的元素
        r11, r12, r13 = Rotm[0, 0], Rotm[0, 1], Rotm[0, 2]
        r21, r22, r23 = Rotm[1, 0], Rotm[1, 1], Rotm[1, 2]
        r31, r32, r33 = Rotm[2, 0], Rotm[2, 1], Rotm[2, 2]

        # 计算sy
        sy = np.sqrt(r11 * r11 + r21 * r21)

        # 判断是否接近奇异点
        singular = sy < 1e-6

        if not singular:
            # 非奇异情况
            roll_rad = np.arctan2(r32, r33)
            pitch_rad = np.arctan2(-r31, sy)
            yaw_rad = np.arctan2(r21, r11)
        else:
            # 奇异情况（sy接近0，即Pitch接近±90度）
            roll_rad = np.arctan2(-r23, r22)
            pitch_rad = np.arctan2(-r31, sy)
            yaw_rad = 0.0

        # 弧度转角度
        roll_deg = roll_rad * 180.0 / np.pi
        pitch_deg = pitch_rad * 180.0 / np.pi
        yaw_deg = yaw_rad * 180.0 / np.pi

        return roll_deg,pitch_deg,yaw_deg