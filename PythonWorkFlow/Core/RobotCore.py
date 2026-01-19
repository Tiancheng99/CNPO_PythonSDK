import sys
import os
import time
import threading
import asyncio
import json
from time import sleep
from typing import Optional, List, Union
from threading import Timer
from pprint import pprint

from PythonWorkFlow.Core.Basic import *
from Communication.ModBusService import ModBusService, RobotStatus
from Communication.ModBusService import RobotParameters as ModBusRobotParameters
from Communication.ModBusCommunicator import ModBusCommunicator
from Communication.CompactEntry import AddressBook
from ..Util import *

class RobotCore:
    def __init__(self, target_ip: str):
        # 创建底层同步 communicator
        # 注意：swap_words=True 用于处理 Modbus TCP 32位数据的字序问题
        self.communicator = ModBusCommunicator(target_ip, 502, unit_id=1, swap_words=True)

        # 加载地址簿
        self._address_book = self._load_address_book()
        if not self._address_book:
            print("警告：未找到地址簿配置文件，部分功能可能无法使用。")

        # 默认参数文件路径
        self.default_parameter_json = "Config/DefaultRobotParameters.json"

        # 创建 ModBusService（async 管理 I/O 队列）
        self._service = ModBusService(self.communicator, self._address_book or {})

        # 事件循环与后台线程
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread = None

        # 机器人状态与参数
        # 尝试加载默认参数，如果文件不存在则使用默认值
        try:
            self.robot_parameter = RobotParameters(json_file=self.default_parameter_json)
        except Exception as e:
            print(f"加载默认参数失败: {e}，将使用空参数初始化")
            # 使用 ModBusRobotParameters 的空初始化
            self.robot_parameter = None

        self.robot_status = RobotStatus()
        
        # 定时器用于周期性读取状态
        self.timer = Timer(0.05, self.ReadRobotStatus)
        self.timer.daemon = True

        # 连接状态标记
        self.connected = False

        # 尝试连接并初始化
        self._initialize_connection()

    def _load_address_book(self) -> Optional[dict]:
        """加载地址簿的工具方法"""
        try_paths = [
            'Config/modbus_address_book.compact_win.json',
            'Config/modbus_address_book.compact.json' # 兼容 C# 路径习惯
        ]
        for path in try_paths:
            if os.path.exists(path):
                try:
                    return AddressBook.load(path)
                except Exception as e:
                    print(f"加载地址簿失败（路径：{path}）：{e}")
        print("未找到地址簿文件")
        return None

    def _run_async(self, coro, timeout: float = 5.0):
        """在后台事件循环中运行协程并等待结果（跨线程安全）"""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("事件循环未运行")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def _initialize_connection(self) -> None:
        """初始化连接并启动服务"""
        try:
            # 这里的 connect 是同步阻塞的
            self.connected = self.communicator.connect()
        except Exception as e:
            print(f"连接机器人失败：{e}")
            self.connected = False

        if self.connected:
            print("连接成功！启动 ModBusService...")
            self._start_service_loop()
            self.timer.start()
            self._initialize_robot()
        else:
            print("连接失败！")

    def _start_service_loop(self) -> None:
        """启动事件循环线程"""
        self._loop = asyncio.new_event_loop()
        loop = self._loop
        
        self._loop_thread = threading.Thread(
            target=loop.run_forever,
            daemon=True
        )
        self._loop_thread.start()

        # 在后台线程启动 ModBusService
        try:
            fut = asyncio.run_coroutine_threadsafe(self._service.start(), loop)
            try:
                fut.result(timeout=2.0)
            except Exception:
                print("ModBusService.start() 响应超时，但可能已在后台运行")
        except Exception as e:
            print(f"启动 ModBusService 失败: {e}")

    def _initialize_robot(self) -> None:
        """初始化机器人控制器状态（同步触发异步操作）"""
        async def init_tasks():
            try:
                # 1. 读取设备当前参数（可选，用于同步上位机数据）
                device_params = await self._service.read_parameters()
                if device_params:
                    print("已从设备读取参数")
                
                # 2. 使能、重置
                await self.RobotEnable()
                await asyncio.sleep(0.5) # 等待上电稳定
                await self.RobotReset()
                
                # 3. 设置默认控制模式
                await self.SetControlMode(ControlMode.Calibration) # 或 Idel
                
                # 4. 下发默认参数 (如果需要覆盖设备参数)
                await self.RobotSetParameters(self.robot_parameter)
                
                print("机器人逻辑初始化完成！")
            except Exception as e:
                print(f"初始化机器人逻辑失败：{e}")

        if self._loop:
            asyncio.run_coroutine_threadsafe(init_tasks(), self._loop)

    # ------------------------------
    # 核心控制方法 
    # ------------------------------

    async def RobotReset(self) -> None:
        """重置机器人 (Pulse)"""
        if not self.connected: return
        try:
            await self._service.pulse_bool('Instructions.Reset_Execute', 30)
            print("机器人重置指令发送成功")
        except Exception as e:
            print(f"发送重置指令失败：{e}")
            raise

    async def RobotEnable(self) -> None:
        """使能机器人 (Pulse)"""
        if not self.connected: return
        try:
            await self._service.pulse_bool('Instructions.Power_On', 50)
            print("机器人使能指令发送成功")
        except Exception as e:
            print(f"发送使能指令失败：{e}")
            raise
    
    async def RobotDisable(self) -> None:
        """失能机器人 (Pulse)"""
        if not self.connected: return
        try:
            await self._service.pulse_bool('Instructions.Power_Off', 50)
            print("机器人失能指令发送成功")
        except Exception as e:
            print(f"发送失能指令失败：{e}")
            raise

    async def RobotStop(self) -> None:
        """停止机器人所有运动 (Pulse)"""
        if not self.connected: return
        try:
            await self._service.pulse_bool('Instructions.Stop_Execute', 30)
            print("机器人已停止所有运动")
        except Exception as e:
            print(f"机器人停止失败：{e}")
            raise

    async def SetControlMode(self, mode: ControlMode) -> None:
        """设置机器人控制模式 (Pulse 对应的 Switch 信号)"""
        if not self.connected: return
        
        mode_key_map = {
            ControlMode.Calibration: "Instructions.Switch_To_Idel_Mode",
            ControlMode.JointJog: "Instructions.Switch_To_JointJog_Mode",
            ControlMode.JointInch: "Instructions.Switch_To_JointInch_Mode",
            ControlMode.JointMoveAbs: "Instructions.Switch_To_JointMoveAbs_Mode",
            ControlMode.MoveJoint: "Instructions.Switch_To_MoveJoint_Mode",
            ControlMode.MoveLinear: "Instructions.Switch_To_MoveLinear_Mode",
            ControlMode.MoveCircle: "Instructions.Switch_To_MoveCircle_Mode",
            ControlMode.TcpJog: "Instructions.Switch_To_TcpJog_Mode",
            ControlMode.TcpInch: "Instructions.Switch_To_TcpInch_Mode",
        }

        key = mode_key_map.get(mode)
        if key:
            try:
                await self._service.pulse_bool(key, 30)
                print(f"发送切换模式指令: {mode.name}")
            except Exception as e:
                print(f"设置控制模式失败：{e}")
                raise
        else:
            # 如果找不到对应的 Pulse Key，尝试回退到旧的写寄存器方式
            try:
                await self._service.write_uint('Parameters.Movement_Mode', int(mode.value))
            except Exception as e:
                print(f"写入模式寄存器失败: {e}")

    # ------------------------------
    # 同步包装方法（供外部直接调用）
    # ------------------------------
    
    def RobotEnable_sync(self) -> None:
        """使能机器人 (同步方法)"""
        if not self.connected: return
        try:
            self._run_async(self.RobotEnable())
        except Exception as e:
            print(f"发送使能指令失败：{e}")
            raise
    
    def RobotReset_sync(self) -> None:
        """重置机器人 (同步方法)"""
        if not self.connected: return
        try:
            self._run_async(self.RobotReset())
        except Exception as e:
            print(f"发送重置指令失败：{e}")
            raise
    
    def SetControlMode_sync(self, mode: ControlMode) -> None:
        """设置控制模式 (同步方法)"""
        if not self.connected: return
        try:
            self._run_async(self.SetControlMode(mode))
        except Exception as e:
            print(f"设置控制模式失败：{e}")
            raise

    # ------------------------------
    # 参数读写
    # ------------------------------

    async def get_device_parameters(self) -> Optional[RobotParameters]:
        """从设备读取全部参数"""
        if not self.connected: return None
        return await self._service.read_parameters()

    async def RobotSetParameters(self, parameters: RobotParameters) -> None:
        """
        向设备写入全部参数
        参考 C# SetAllParametersAsync
        """
        if not self.connected:
            raise RuntimeError("机器人未连接")
        
        s = self._service

        try:
            print("开始写入所有参数...")
            
            # 1. DH 参数
            key_dh = "Parameters.DH_Parameters"
            for i in range(6):
                for j in range(4):
                    val = parameters.DH_Parameters[i][j]
                    # i+1, j+1 为 1-based index
                    await s.write_real(key_dh, float(val), i+1, j+1)

            # 2. 校准位置
            for i, val in enumerate(parameters.CalibrationJointPositions):
                await s.write_real("Parameters.CalibrationJointPositions", float(val), i+1)

            # 3. 基础参数
            await s.write_real("Parameters.Override", float(parameters.Override))

            # 4. 关节运动参数 (Jog/Inch/Ref)
            # 假设所有数组长度均为6
            keys_map = [
                ("Parameters.Joint_Jog_Velocity", parameters.JointJogVelocity),
                ("Parameters.Inch_Distance", parameters.InchDistance),
                ("Parameters.Joint_Target_Position", parameters.JointTargetPosition),
                ("Parameters.Joint_Refference_Velocity", parameters.JointReferenceVelocity),
                ("Parameters.Joint_Refference_Acceleration", parameters.JointReferenceAcceleration),
                ("Parameters.Joint_Refference_Jerk", parameters.JointReferenceJerk),
            ]

            for key, arr in keys_map:
                for i, val in enumerate(arr):
                    await s.write_real(key, float(val), i+1)

            # 5. MoveJ 参数
            await s.write_real("Parameters.MoveJ_Refference_Velocity", parameters.MoveJReferenceVelocity)
            await s.write_real("Parameters.MoveJ_Refference_Acceleration", parameters.MoveJReferenceAcceleration)
            await s.write_real("Parameters.MoveJ_Refference_Deceleration", parameters.MoveJReferenceDeceleration)

            # 6. TCP 运动参数
            await s.write_real("Parameters.TCP_Jog_Linear_Velocity", parameters.TCPJogLinearVelocity)
            await s.write_real("Parameters.TCP_Jog_Angular_Velocity", parameters.TCPJogAngularVelocity)
            await s.write_real("Parameters.TCP_Inch_Linear_Distance", parameters.TCPInchDistance)
            
            # TODO C# 还有 TCPInchAngularDistance，Python Basic.py 里似乎没定义，如果地址簿有需补充

            # TCP Target / Mid Pose
            for i, val in enumerate(parameters.TCPTargetPose):
                await s.write_real("Parameters.TCP_Target_Pose", float(val), i+1)
            for i, val in enumerate(parameters.TCPMidPose):
                await s.write_real("Parameters.TCP_Mid_Pose", float(val), i+1)

            # TCP Reference
            await s.write_real("Parameters.TCP_Refference_Linear_Velocity", parameters.TCPReferenceLinearVelocity)
            await s.write_real("Parameters.TCP_Refference_Linear_Acceleration", parameters.TCPReferenceLinearAcceleration)
            await s.write_real("Parameters.TCP_Refference_Linear_Deceleration", parameters.TCPReferenceLinearDeceleration)
            await s.write_real("Parameters.TCP_Refference_Angular_Velocity", parameters.TCPReferenceAngularVelocity)
            await s.write_real("Parameters.TCP_Refference_Angular_Acceleration", parameters.TCPReferenceAngularAcceleration)
            await s.write_real("Parameters.TCP_Refference_Angular_Deceleration", parameters.TCPReferenceAngularDeceleration)

            # 7. 负载与导纳
            await s.write_real("Parameters.LoadMass", parameters.LoadMass)
            for i, val in enumerate(parameters.LoadCOG):
                await s.write_real("Parameters.LoadCOG", float(val), i+1)
            
            # Tip
            for i, val in enumerate(parameters.Tip):
                await s.write_real("Parameters.Tip", float(val), i+1)

            print("参数写入完成！")

        except Exception as e:
            print(f"参数设置失败：{e}")
            raise

    # ------------------------------
    # 状态读取
    # ------------------------------

    def ReadRobotStatus(self) -> None:
        """周期性读取机器人状态（定时器回调）"""
        if self.connected and self._loop:
            async def async_read_status():
                try:
                    # 使用 Service 的 snapshot 机制
                    new_status = await self._service.read_snapshot()
                    if new_status:
                        self.robot_status = new_status
                except Exception as e:
                    pass

            asyncio.run_coroutine_threadsafe(async_read_status(), self._loop)
        
        # 维持定时器
        self.timer = Timer(0.05, self.ReadRobotStatus)
        self.timer.daemon = True
        self.timer.start()

    async def getRobotStatus(self) -> str:
        """获取当前机器人状态并转换为JSON"""
        if not self.connected:
            raise RuntimeError("机器人未连接，无法获取状态")
        
        try:
            # 1. 主动读取最新状态快照
            latest_status = await self._service.read_snapshot()
            if latest_status:
                self.robot_status = latest_status 

            s = self.robot_status # 简写引用

            # 2. 数据结构适配：将扁平的 Dataclass 转换为 transform_json 需要的嵌套字典
            
            # --- 构建 Joints 部分 ---
            joints_data = {}
            for i in range(6):
                joint_name = f"J{i+1}"
                # 安全获取列表数据，防止索引越界
                def get_val(arr, idx):
                    return float(arr[idx]) if arr and len(arr) > idx else 0.0

                joints_data[joint_name] = {
                    "ActualPosition": get_val(s.JointActualPosition, i),
                    "ActualVelocity": get_val(s.JointActualVelocity, i),
                    "ActualAcceleration": 0.0, # ModBusService 中暂无此字段，给默认值
                    "ActualCurrent": get_val(s.JointActualCurrent, i),
                    "ActualTorque": get_val(s.JointActualTorque, i),
                    "Statusof402": 1 # 默认值
                }

            # --- 构建 TcpPose 部分 ---
            # ModBusService 中 TcpPose 是列表 [X, Y, Z, Rx, Ry, Rz]
            tcp_list = s.TcpPose if s.TcpPose and len(s.TcpPose) >= 6 else [0.0]*6
            tcp_data = {
                "X": float(tcp_list[0]),
                "Y": float(tcp_list[1]),
                "Z": float(tcp_list[2]),
                "Roll": float(tcp_list[3]),
                "Pitch": float(tcp_list[4]),
                "Yaw": float(tcp_list[5])
            }

            # --- 构建 Manage 部分 ---
            manage_data = {
                "Initialized": bool(s.Initialized),
                "Enabled": bool(s.PowerOn),   # 对应 PowerOn
                "Moving": bool(s.Moving),
                "Error": bool(s.Error),
                "ErrorID": int(s.ErrorId),
                "Mode": 0 # ModBusService暂未解析Mode，给默认值或需补充读取
            }

            # --- 构建 AirLock 部分 ---
            airlock_data = {
                "locked": False,
                "pressure": 0.0
            }

            # 3. 组装成中间字典 (符合 Basic.py 旧结构)
            status_dict_legacy = {
                "Joints": joints_data,
                "TcpPose": tcp_data,
                "Manage": manage_data,
                "AirLock": airlock_data,
                "FlangePose": tcp_data # 暂时用法兰代替，或者给全0
            }

            # 4. 调用 Util.transform_json 进行最终前端格式转换
            # transform_json 会提取 jointPositions, pose, isEnabled 等字段
            transformed = transform_json(status_dict_legacy)

            return json.dumps(transformed, indent=4)
        
        except Exception as e:
            print(f"获取机器人状态JSON失败：{e}")
            # 返回一个符合前端结构的空JSON，避免前端崩溃
            return json.dumps({
                "jointPositions": {}, "pose": {}, 
                "isEnabled": False, "isMoving": False, 
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })

    # ------------------------------
    # 运动指令 (MoveJ, MoveL, Jog, Inch)
    # ------------------------------

    async def JogForward(self, index: int, value: bool) -> None:
        """关节正向连续点动"""
        if not self.connected: return
        # C# 逻辑：WriteBool "Instructions.Joint_Jog_Forward"
        await self._service.write_bool('Instructions.Joint_Jog_Forward', value, index)

    async def JogBackward(self, index: int, value: bool) -> None:
        if not self.connected: return
        await self._service.write_bool('Instructions.Joint_Jog_Backward', value, index)

    async def InchForward(self, index: int, value: bool) -> None:
        """关节正向增量点动"""
        if not self.connected: return
        await self._service.write_bool('Instructions.Joint_Inch_Forward', value, index)

    async def InchBackward(self, index: int, value: bool) -> None:
        if not self.connected: return
        await self._service.write_bool('Instructions.Joint_Inch_Backward', value, index)

    def MoveJ(self, joint_positions: List[float]) -> None:
        """关节空间运动"""
        if not self.connected: return
        
        async def _move_j_async():
            # 1. 写目标 - 使用地址簿API（1-based索引1-6）
            # 底层的ModBusCommunicator会自动处理硬件地址偏移
            for i, val in enumerate(joint_positions):
                await self._service.write_real('Parameters.Joint_Target_Position', float(val), i+1)
            # 2. Pulse Execute
            await self._service.pulse_bool('Instructions.TCP_Move_Joint_Execute', 30)
        
        self._run_async(_move_j_async())

    def MoveL(self, pose: List[float]) -> None:
        """笛卡尔空间直线运动"""
        if not self.connected: return
        
        async def _move_l_async():
            for i, val in enumerate(pose):
                await self._service.write_real('Parameters.TCP_Target_Pose', float(val), i+1)
            await self._service.pulse_bool('Instructions.TCP_Move_Linear_Execute', 30)
        
        self._run_async(_move_l_async())

    def MoveAbs(self, joint_index: int, target_position: float) -> None:
        """单关节绝对运动"""
        if not self.connected: return
        
        async def _move_abs_async():
            await self._service.write_real('Parameters.Joint_Target_Position', float(target_position), joint_index)
            await self._service.pulse_bool('Instructions.Joint_MoveAbs_Execute', 30, joint_index) # 注意这里可能有index
        
        self._run_async(_move_abs_async())

    # ------------------------------
    # 辅助功能
    # ------------------------------
    
    def stop(self) -> None:
        """停止服务"""
        if not self.connected: return
        try:
            if self.timer: self.timer.cancel()
            
            if self._service and self._loop:
                # 尝试发送失能
                asyncio.run_coroutine_threadsafe(self.RobotDisable(), self._loop)
                # 停止服务
                asyncio.run_coroutine_threadsafe(self._service.stop(), self._loop)
            
            # 停止循环
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            
            if self._loop_thread:
                self._loop_thread.join(timeout=1.0)
            
            self.connected = False
            print("服务已停止")
        except Exception as e:
            print(f"停止服务出错: {e}")

    # ------------------------------
    # 末端负载参数 (End-Effector & Load Parameters)
    # ------------------------------
    
    # 设置末端工具参数 (Tip)
    async def SetTip(self, tip: List[float]) -> None:
        """
        设置末端工具参数
        :param tip: 工具参数数组 (通常为 XYZRPY 或 XYZ)
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法设置末端参数")
        if not tip:
            return
            
        try:
            for i, val in enumerate(tip):
                await self._service.write_real('Parameters.Tip', float(val), i + 1)
            
            print(f"末端参数(Tip)已设置: {tip}")
        except Exception as e:
            print(f"设置末端参数(Tip)失败: {e}")
            raise

    # 设置负载质量 (Mass)
    async def SetLoadMass(self, mass: float) -> None:
        """
        设置负载质量
        :param mass: 质量值 (kg)
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法设置负载质量")
        
        try:
            await self._service.write_real('Parameters.LoadMass', float(mass))
            print(f"负载质量(LoadMass)已设置: {mass}")
        except Exception as e:
            print(f"设置负载质量失败: {e}")
            raise

    # 设置负载重心 (COG)
    async def SetLoadCog(self, cog: List[float]) -> None:
        """
        设置负载重心
        :param cog: 重心坐标数组 [X, Y, Z]
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法设置负载重心")
        if not cog:
            return

        try:
            for i, val in enumerate(cog):
                await self._service.write_real('Parameters.LoadCOG', float(val), i + 1)
            print(f"负载重心(LoadCOG)已设置: {cog}")
        except Exception as e:
            print(f"设置负载重心(LoadCOG)失败: {e}")
            raise

    # 设置负载惯量 (Inertia)
    async def SetLoadInertia6(self, inertia: List[float]) -> None:
        """
        设置负载惯量
        :param inertia: 惯量数组 (通常包含 6 个分量)
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法设置负载惯量")
        if not inertia:
            return

        try:
            for i, val in enumerate(inertia):
                await self._service.write_real('Parameters.LoadInertia6', float(val), i + 1)
            print(f"负载惯量(LoadInertia6)已设置: {inertia}")
        except Exception as e:
            print(f"设置负载惯量(LoadInertia6)失败: {e}")
            raise

    # ------------------------------
    # 夹爪控制功能
    # ------------------------------
    async def SetGrip1(self, grip_action: int) -> None:
        """
        设置夹爪1动作 (控制数字输出 5 和 6)
        :param grip_action: 0=Release(松开), 1=Hold(保持), 2=Grip(夹紧)
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法执行 SetGrip1")

        try:
            val_5 = False
            val_6 = False
            
            # 逻辑映射: 
            # Release(0): 5=False, 6=True
            # Hold(1):    5=False, 6=False
            # Grip(2):    5=True,  6=False
            if grip_action == 0:   # Release
                val_5 = False
                val_6 = True
            elif grip_action == 1: # Hold
                val_5 = False
                val_6 = False
            elif grip_action == 2: # Grip
                val_5 = True
                val_6 = False
            else: # Default
                val_5 = False
                val_6 = False

            key = "Instructions.Digital_Output"
            
            await self._service.write_bool(key, val_5, 5)
            await self._service.write_bool(key, val_6, 6)
            
            action_name = ["Release", "Hold", "Grip"][grip_action] if 0 <= grip_action <= 2 else "Unknown"
            print(f"SetGrip1 执行完成: {action_name} (DO5={val_5}, DO6={val_6})")
            
        except Exception as e:
            print(f"SetGrip1 执行失败: {e}")
            raise

    async def SetGrip2(self, grip_action: int) -> None:
        """
        设置夹爪2动作 (控制数字输出 7 和 8)
        :param grip_action: 0=Release(松开), 1=Hold(保持), 2=Grip(夹紧)
        """
        if not self.connected:
            raise RuntimeError("机器人未连接，无法执行 SetGrip2")

        try:
            val_7 = False
            val_8 = False
            
            # 逻辑映射 (注意与Grip1不同): 
            # Release(0): 7=True,  8=False
            # Hold(1):    7=False, 8=False
            # Grip(2):    7=False, 8=True
            if grip_action == 0:   # Release
                val_7 = True
                val_8 = False
            elif grip_action == 1: # Hold
                val_7 = False
                val_8 = False
            elif grip_action == 2: # Grip
                val_7 = False
                val_8 = True
            else: # Default
                val_7 = False
                val_8 = False

            key = "Instructions.Digital_Output"
            
            await self._service.write_bool(key, val_7, 7)
            await self._service.write_bool(key, val_8, 8)
            
            action_name = ["Release", "Hold", "Grip"][grip_action] if 0 <= grip_action <= 2 else "Unknown"
            print(f"SetGrip2 执行完成: {action_name} (DO7={val_7}, DO8={val_8})")
            
        except Exception as e:
            print(f"SetGrip2 执行失败: {e}")
            raise

    # 机器人全局控制
    async def RobotStop(self) -> None:
        """停止机器人所有运动"""
        if not self.connected:
            raise RuntimeError("机器人未连接，无法执行停止操作")
        
        try:
            await self._service.write_bool('Instructions.Stop_Execute', True)
            await asyncio.sleep(0.1)
            await self._service.write_bool('Instructions.Stop_Execute', False)
            print("机器人已停止所有运动")
        except Exception as e:
            print(f"机器人停止失败：{e}")
            raise

    # 控制模式激活
    async def activateJointMoveAbs(self) -> None:
        """激活关节绝对运动模式"""
        await self.SetControlMode(ControlMode.JointMoveAbs)

    async def activateMoveLinear(self) -> None:
        """激活线性运动模式"""
        await self.SetControlMode(ControlMode.MoveLinear)

    async def activateMoveJoint(self) -> None:
        """激活关节运动模式"""
        await self.SetControlMode(ControlMode.MoveJoint)

    async def activateJointJog(self) -> None:
        """激活关节点动模式"""
        await self.SetControlMode(ControlMode.JointJog)

    def stop(self) -> None:
        """停止机器人服务、事件循环及相关资源"""
        if not self.connected:
            print("机器人未连接，无需停止服务")
            return
        try:
            # 1. 取消状态读取定时器
            if self.timer:
                self.timer.cancel()
                print("已取消状态读取定时器")

            # === 关键新增步骤：发送安全失能指令 ===
            if self._service and self._loop:
                print("正在发送机器人失能指令...")
                try:
                    # 将异步的 RobotDisable 提交给后台事件循环执行
                    disable_fut = asyncio.run_coroutine_threadsafe(self.RobotDisable(), self._loop)
                    # TODO 等待失能指令执行完成，确保安全操作优先
                    disable_fut.result(timeout=3.0) 
                    print("机器人已成功失能 (Power_On=False)")
                except asyncio.TimeoutError:
                    # 即使超时，也继续执行下一步，尝试关闭通信
                    print("发送失能指令超时，继续停止服务...")
                except Exception as e:
                    print(f"发送失能指令时发生错误: {e}，继续停止服务...")
            # ========================================

            # 2. 停止ModBusService
            if self._service and self._loop:
                try:
                    # 提交停止服务的异步任务并等待完成
                    stop_fut = asyncio.run_coroutine_threadsafe(self._service.stop(), self._loop)
                    stop_fut.result(timeout=5.0) 
                    print("ModBusService已停止")
                except asyncio.TimeoutError:
                    print("停止ModBusService超时")
                except Exception as e:
                    print(f"停止ModBusService时发生错误: {e}")

            # 3. 停止事件循环并等待线程结束
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
                print("已请求事件循环停止")

            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=2.0)
                if self._loop_thread.is_alive():
                    print("事件循环线程未能正常退出")
                else:
                    print("事件循环线程已退出")

            # 4. 标记连接状态为断开
            self.connected = False
            print("机器人服务已成功停止")

        except Exception as e:
            print(f"停止机器人服务时发生未预期错误: {e}")
