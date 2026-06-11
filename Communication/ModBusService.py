"""
异步 ModBusService
功能：
- 串行化 I/O 队列
- 动态地址解析（基于 AddressBook）
- 分包读取以绕过 Modbus 125 寄存器限制
- 容错重连机制
"""

import asyncio
from typing import Dict, Callable, Optional, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from Communication.ModBusCommunicator import ModBusCommunicator
from Communication.CompactEntry import CompactEntry, AddressBook
from Communication.ModBusUtils import registers_to_float, registers_to_dword

@dataclass
class RobotStatus:
    """机器人状态信息类"""
    joint_count: int = 6
    TimestampUtc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    Initialized: bool = False
    PowerOn: bool = False
    Moving: bool = False
    Error: bool = False
    TcpJogInchCoord: bool = False
    ErrorId: int = 0
    ActualMovementMode: int = 0
    JointError: List[bool] = field(default_factory=list)
    JointMoving: List[bool] = field(default_factory=list)
    JointErrorId: List[int] = field(default_factory=list)
    JointState: List[int] = field(default_factory=list)
    JointActualPosition: List[float] = field(default_factory=list)
    JointActualVelocity: List[float] = field(default_factory=list)
    JointActualCurrent: List[float] = field(default_factory=list)
    JointActualTorque: List[float] = field(default_factory=list)
    FlangePose: List[float] = field(default_factory=lambda: [0.0]*6)
    TcpPose: List[float] = field(default_factory=lambda: [0.0]*6)

    def __post_init__(self):
        self.JointError = _fit_list(self.JointError, self.joint_count, False)
        self.JointMoving = _fit_list(self.JointMoving, self.joint_count, False)
        self.JointErrorId = _fit_list(self.JointErrorId, self.joint_count, 0)
        self.JointState = _fit_list(self.JointState, self.joint_count, 0)
        self.JointActualPosition = _fit_list(self.JointActualPosition, self.joint_count, 0.0)
        self.JointActualVelocity = _fit_list(self.JointActualVelocity, self.joint_count, 0.0)
        self.JointActualCurrent = _fit_list(self.JointActualCurrent, self.joint_count, 0.0)
        self.JointActualTorque = _fit_list(self.JointActualTorque, self.joint_count, 0.0)

@dataclass
class RobotParameters:
    """机器人参数类 (对应 Holding Registers)"""
    joint_count: int = 6
    DHParameters: List[List[float]] = field(default_factory=list)
    CalibrationJointPositions: List[float] = field(default_factory=list)
    OverrideRatio: float = 1.0
    JointJogVelocity: List[float] = field(default_factory=list)
    InchDistance: List[float] = field(default_factory=list)
    JointTargetPosition: List[float] = field(default_factory=list)
    JointReferenceVelocity: List[float] = field(default_factory=list)
    JointReferenceAcceleration: List[float] = field(default_factory=list)
    JointReferenceJerk: List[float] = field(default_factory=list)
    MoveJReferenceVelocity: float = 0.0
    MoveJReferenceAcceleration: float = 0.0
    MoveJReferenceDeceleration: float = 0.0
    TCPJogLinearVelocity: float = 0.0
    TCPJogAngularVelocity: float = 0.0
    TCPInchDistance: float = 0.0
    TCPInchAngularDistance: float = 0.0
    TCPTargetPose: List[float] = field(default_factory=lambda: [0.0]*6)
    TCPMidPose: List[float] = field(default_factory=lambda: [0.0]*6)
    TCPReferenceLinearVelocity: float = 0.0
    TCPReferenceLinearAcceleration: float = 0.0
    TCPReferenceLinearDeceleration: float = 0.0
    TCPReferenceAngularVelocity: float = 0.0
    TCPReferenceAngularAcceleration: float = 0.0
    TCPReferenceAngularDeceleration: float = 0.0
    TCPTargetVelocity: List[float] = field(default_factory=lambda: [0.0]*6)
    AdmittanceControlM: List[float] = field(default_factory=lambda: [0.0]*6)
    AdmittanceControlK: List[float] = field(default_factory=lambda: [0.0]*6)
    AdmittanceControlB: List[float] = field(default_factory=lambda: [0.0]*6)
    Tip: List[float] = field(default_factory=lambda: [0.0]*6)
    LoadMass: float = 0.0
    LoadCOG: List[float] = field(default_factory=lambda: [0.0]*3)
    LoadInertia6: List[float] = field(default_factory=lambda: [0.0]*6)
    LevelingDirction: List[float] = field(default_factory=lambda: [0.0]*3)
    Axis: int = 0

    def __post_init__(self):
        self.DHParameters = self.DHParameters or [[0.0]*4 for _ in range(self.joint_count)]
        self.CalibrationJointPositions = _fit_list(self.CalibrationJointPositions, self.joint_count, 0.0)
        self.JointJogVelocity = _fit_list(self.JointJogVelocity, self.joint_count, 0.0)
        self.InchDistance = _fit_list(self.InchDistance, self.joint_count, 0.0)
        self.JointTargetPosition = _fit_list(self.JointTargetPosition, self.joint_count, 0.0)
        self.JointReferenceVelocity = _fit_list(self.JointReferenceVelocity, self.joint_count, 0.0)
        self.JointReferenceAcceleration = _fit_list(self.JointReferenceAcceleration, self.joint_count, 0.0)
        self.JointReferenceJerk = _fit_list(self.JointReferenceJerk, self.joint_count, 0.0)


def _fit_list(values: List[Any], length: int, default: Any) -> List[Any]:
    fitted = list(values[:length]) if values else []
    if len(fitted) < length:
        fitted.extend([default] * (length - len(fitted)))
    return fitted


class ModBusService:
    def __init__(self, communicator: ModBusCommunicator, address_book: Dict[str, CompactEntry], poll_interval: float = 0.1, joint_count: int = 6):
        self._com = communicator
        self._book = address_book
        self._poll_interval = poll_interval
        self.joint_count = max(1, int(joint_count or 6))

        self._pulse_locks: Dict[str, asyncio.Lock] = {}
        self._queue: Optional[asyncio.Queue] = None
        self._consumer_task: Optional[asyncio.Task] = None
        self._poller_task: Optional[asyncio.Task] = None
        self._running = False

        self.snapshot_updated: Optional[Callable[[RobotStatus], Any]] = None
        self._poll_work_pending = False
        
        self._consecutive_failures = 0
        self._reconnect_backoff_min = 2.0 
        self._reconnect_backoff_max = 30.0 
        self._reconnect_backoff = self._reconnect_backoff_min
        self._last_reconnect_attempt = datetime.min.replace(tzinfo=timezone.utc)
        
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._consumer_task is not None and not self._consumer_task.done()

    async def start(self) -> bool:
        if self.is_running: return False
        self._loop = asyncio.get_running_loop()
        
        connected = self._com.is_connected
        if not connected:
            try:
                connected = await self._loop.run_in_executor(None, self._com.connect)
            except Exception as e:
                print(f"启动时连接异常: {e}")

        self._queue = asyncio.Queue()
        self._running = True
        self._poll_work_pending = False
        self._consecutive_failures = 0
        self._consumer_task = asyncio.create_task(self._consume_loop())
        self._poller_task = asyncio.create_task(self._poll_loop())
        return True

    async def stop(self):
        self._running = False
        if self._poller_task:
            self._poller_task.cancel()
        if self._queue:
            await self._queue.put(None)
        if self._consumer_task:
            try: await asyncio.wait_for(self._consumer_task, timeout=3.0)
            except: pass
        try:
            if self._loop: await self._loop.run_in_executor(None, self._com.disconnect)
        except: pass

    # --- ModBusService类 通用 写操作 ---
    async def write_bool(self, key: str, value: bool, *idx: int):
        return await self._enqueue(lambda: self._com.write_bool(self._book, key, value, *idx))

    async def write_uint(self, key: str, value: int, *idx: int):
        return await self._enqueue(lambda: self._com.write_uint(self._book, key, value, *idx))

    async def write_real(self, key: str, value: float, *idx: int):
        return await self._enqueue(lambda: self._com.write_real(self._book, key, value, *idx))
    
    async def write_dword(self, key: str, value: int, *idx: int):
        return await self._enqueue(lambda: self._com.write_dword(self._book, key, value, *idx))
    
    # --- ModBusService类 通用 读操作 ---
    async def read_bool(self, key: str, *idx: int) -> bool:
        return await self._enqueue(lambda: self._com.read_bool(self._book, key, *idx))
    
    async def read_uint(self, key: str, *idx: int) -> int:
        return await self._enqueue(lambda: self._com.read_uint(self._book, key, *idx))
    
    async def read_real(self, key: str, *idx: int) -> float:
        return await self._enqueue(lambda: self._com.read_real(self._book, key, *idx))
    
    async def read_dword(self, key: str, *idx: int) -> int:
        return await self._enqueue(lambda: self._com.read_dword(self._book, key, *idx))

    async def pulse_bool(self, key: str, milliseconds: int, *idx: int):
        lock = self._pulse_locks.setdefault(key, asyncio.Lock())
        async with lock:
            try:
                await self.write_bool(key, True, *idx)
                await asyncio.sleep(milliseconds / 1000.0)
            finally:
                try: await self.write_bool(key, False, *idx)
                except: pass

    async def read_snapshot(self) -> Optional[RobotStatus]:
        return await self._enqueue(self._poll_once_safe)

    async def read_parameters(self) -> Optional[RobotParameters]:
        return await self._enqueue(self._read_parameters_once_safe)

    # --- 核心队列逻辑 ---
    async def _enqueue(self, func: Callable[[], Any]) -> Any:
        if self._queue is None: raise RuntimeError("ModBusService 未启动")
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async def work_item():
            try:
                result = await loop.run_in_executor(None, func)
                if not future.done(): future.set_result(result)
            except Exception as ex:
                if not future.done(): future.set_exception(ex)
                # 只有真正的 IO/连接错误才向上抛，触发 _consume_loop 的重连逻辑
                # 业务逻辑错误（如地址簿缺 key）不应导致 0.5s 全局队列阻塞
                if "10053" in str(ex) or "Aborted" in str(ex) or isinstance(ex, (ConnectionError, OSError)):
                    raise ex

        await self._queue.put(work_item)
        return await future

    async def _consume_loop(self):
        while self._running:
            try:
                work_item = await self._queue.get()
                if work_item is None: break
                try:
                    await work_item()
                    self._consecutive_failures = 0
                    self._reconnect_backoff = self._reconnect_backoff_min
                except Exception as ex:
                    self._consecutive_failures += 1
                    # 处理连接中止
                    if "10053" in str(ex) or "Aborted" in str(ex):
                        self._com.is_connected = False
                    
                    if self._running:
                        now = datetime.now(timezone.utc)
                        if self._consecutive_failures >= 3 and (now - self._last_reconnect_attempt).total_seconds() >= self._reconnect_backoff:
                            print(f"检测到通讯异常，尝试重连... (失败次数: {self._consecutive_failures})")
                            await self._try_reconnect()
                            self._last_reconnect_attempt = datetime.now(timezone.utc)
                            self._reconnect_backoff = min(self._reconnect_backoff * 2, self._reconnect_backoff_max)
                        await asyncio.sleep(0.5)
            except asyncio.CancelledError: break

    async def _try_reconnect(self):
        loop = asyncio.get_running_loop()
        try: await loop.run_in_executor(None, self._com.disconnect)
        except: pass
        try: await loop.run_in_executor(None, self._com.connect)
        except: pass

    async def _poll_loop(self):
        while self._running:
            await asyncio.sleep(self._poll_interval)
            if self._poll_work_pending: continue
            self._poll_work_pending = True
            
            async def poll_work():
                try:
                    snap = await asyncio.get_running_loop().run_in_executor(None, self._poll_once_safe)
                    if snap and self.snapshot_updated:
                        res = self.snapshot_updated(snap)
                        if asyncio.iscoroutine(res): await res
                except: pass
                finally: self._poll_work_pending = False

            await self._queue.put(poll_work)

    # --- 状态读取逻辑 ---
    def _poll_once_safe(self) -> Optional[RobotStatus]:
        try:
            # 辅助：从地址簿获取真实地址
            def get_addr(key: str, *idx: int) -> int:
                return AddressBook.address_of(self._book, key, *idx)[1]

            # 1. 自动搜索各区域的最小地址（无需硬编码）
            def find_area_start(area_type: str, is_bool: bool = False) -> int:
                """搜索指定区域的最小地址"""
                min_addr = float('inf')
                for key, entry in self._book.items():
                    # 筛选区域和类型匹配的条目
                    if entry.area == area_type:
                        is_entry_bool = entry.baseType and entry.baseType.upper() == "BOOL"
                        if is_entry_bool == is_bool:
                            addr_key = entry.bitBase if is_bool else entry.regBase
                            if addr_key is not None and addr_key < min_addr:
                                min_addr = addr_key
                return int(min_addr) if min_addr != float('inf') else 0

            # Flags 区域（布尔类型，Discrete Inputs）
            flags_start = find_area_start("InputStatus", is_bool=True)

            # Status 区域（数值类型，Input Registers）
            status_start = find_area_start("InputRegisters", is_bool=False)

            # 2. 批量读取数据 (分块处理)
            # Discrete Inputs (Flags)
            flags_count = self._area_bit_count("InputStatus", flags_start)
            byte_flags = self._com.read_discrete_inputs_block(flags_start, flags_count)
            
            status_count = self._area_register_count("InputRegisters", status_start)
            all_regs = self._com.read_input_registers_block(status_start, status_count)

            if not byte_flags or not all_regs: return None

            # 3. 解析到对象
            s = RobotStatus(joint_count=self.joint_count)
            
            s.Initialized = self._get_bit(byte_flags, flags_start, get_addr("Flags.Initialized"))
            s.PowerOn     = self._get_bit(byte_flags, flags_start, get_addr("Flags.PowerOn"))
            s.Moving      = self._get_bit(byte_flags, flags_start, get_addr("Flags.Moving"))
            s.Error       = self._get_bit(byte_flags, flags_start, get_addr("Flags.Error"))

            s.ErrorId     = self._get_dword(all_regs, status_start, get_addr("Status.Error_ID"))
            s.ActualMovementMode = self._get_dword(all_regs, status_start, get_addr("Status.Actual_Movement_Mode"))

            for i in range(self.joint_count):
                s.JointError[i]  = self._get_bit(byte_flags, flags_start, get_addr("Flags.Joint_Error", i+1))
                s.JointMoving[i] = self._get_bit(byte_flags, flags_start, get_addr("Flags.Joint_Moving", i+1))
                s.JointErrorId[i] = self._get_dword(all_regs, status_start, get_addr("Status.Joint_Error_ID", i+1))
                s.JointState[i] = self._get_dword(all_regs, status_start, get_addr("Status.Joint_State", i+1))
                
                s.JointActualPosition[i] = self._get_f32(all_regs, status_start, get_addr("Status.Joint_Actual_Position", i+1))
                s.JointActualVelocity[i] = self._get_f32(all_regs, status_start, get_addr("Status.Joint_Actual_Velocity", i+1))
                s.JointActualCurrent[i]  = self._get_f32(all_regs, status_start, get_addr("Status.Joint_Actual_Current", i+1))
                s.JointActualTorque[i]   = self._get_f32(all_regs, status_start, get_addr("Status.Joint_Actual_Torque", i+1))
            
            # 读取法兰位姿，固定为 XYZRPY 6 维
            for i in range(6):
                s.FlangePose[i] = self._get_f32(all_regs, status_start, get_addr("Status.Flange_Pose", i+1))
            
            # 读取 TCP 实际位置，固定为 XYZRPY 6 维
            for i in range(6):
                s.TcpPose[i] = self._get_f32(all_regs, status_start, get_addr("Status.TCP_Pose", i+1))

            return s

        except Exception as e:
            if "10053" in str(e):
                self._com.is_connected = False
                print("检测到网络断开连接 (10053)")
            return None

    def _read_parameters_once_safe(self) -> Optional[RobotParameters]:
        """批量读取所有机器人参数（同样使用分包逻辑）"""
        try:
            # 获取 HoldingRegisters 的起始地址
            def find_holding_registers_start() -> int:
                """搜索 HoldingRegisters 区域的最小地址"""
                min_addr = float('inf')
                for entry in self._book.values():
                    if entry.area == "HoldingRegisters" and entry.regBase is not None and entry.regBase < min_addr:
                        min_addr = entry.regBase
                return int(min_addr) if min_addr != float('inf') else 0

            p_start = find_holding_registers_start()
            
            register_count = self._area_register_count("HoldingRegisters", p_start)
            all_regs = self._com.read_holding_registers_block(p_start, register_count)
            
            if not all_regs: return None

            def get_addr(key: str, *idx: int) -> int:
                return AddressBook.address_of(self._book, key, *idx)[1]

            p = RobotParameters(joint_count=self.joint_count)
            
            # 1. DH 参数 (6x4)
            for i in range(self.joint_count):
                for j in range(4):
                    addr = get_addr("Parameters.DH_Parameters", i+1, j+1)
                    p.DHParameters[i][j] = self._get_f32(all_regs, p_start, addr)
            
            # 2. 校准位置 (6个 REAL)
            for i in range(self.joint_count):
                addr = get_addr("Parameters.CalibrationJointPositions", i+1)
                p.CalibrationJointPositions[i] = self._get_f32(all_regs, p_start, addr)
            
            # 3. 覆盖率
            p.OverrideRatio = self._get_f32(all_regs, p_start, get_addr("Parameters.Override"))
            
            # 4. 关节 Jog 速度 (6个 REAL)
            for i in range(self.joint_count):
                addr = get_addr("Parameters.Joint_Jog_Velocity", i+1)
                p.JointJogVelocity[i] = self._get_f32(all_regs, p_start, addr)
            
            # 5. 英寸距离 (6个 REAL)
            for i in range(self.joint_count):
                addr = get_addr("Parameters.Inch_Distance", i+1)
                p.InchDistance[i] = self._get_f32(all_regs, p_start, addr)
            
            # 6. 关节目标位置 (6个 REAL)
            for i in range(self.joint_count):
                addr = get_addr("Parameters.Joint_Target_Position", i+1)
                p.JointTargetPosition[i] = self._get_f32(all_regs, p_start, addr)
            
            # 7. 关节参考速度/加速度/Jerk (各6个 REAL)
            for i in range(self.joint_count):
                p.JointReferenceVelocity[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.Joint_Refference_Velocity", i+1))
                p.JointReferenceAcceleration[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.Joint_Refference_Acceleration", i+1))
                p.JointReferenceJerk[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.Joint_Refference_Jerk", i+1))
            
            # 8. MoveJ 参数 (3个 REAL)
            p.MoveJReferenceVelocity = self._get_f32(all_regs, p_start, get_addr("Parameters.MoveJ_Refference_Velocity"))
            p.MoveJReferenceAcceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.MoveJ_Refference_Acceleration"))
            p.MoveJReferenceDeceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.MoveJ_Refference_Deceleration"))
            
            # 9. TCP Jog 参数
            p.TCPJogLinearVelocity = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Jog_Linear_Velocity"))
            p.TCPJogAngularVelocity = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Jog_Angular_Velocity"))
            
            # 10. TCP Inch 参数
            p.TCPInchDistance = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Inch_Linear_Distance"))
            p.TCPInchAngularDistance = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Inch_Angular_Distance"))
            
            # 11. TCP 目标/中间位姿 (各6个 REAL)
            for i in range(6):
                p.TCPTargetPose[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Target_Pose", i+1))
                p.TCPMidPose[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Mid_Pose", i+1))
            
            # 12. TCP 参考速度/加速度/减速度 (线性/角速度各3个)
            p.TCPReferenceLinearVelocity = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Linear_Velocity"))
            p.TCPReferenceLinearAcceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Linear_Acceleration"))
            p.TCPReferenceLinearDeceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Linear_Deceleration"))
            p.TCPReferenceAngularVelocity = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Angular_Velocity"))
            p.TCPReferenceAngularAcceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Angular_Acceleration"))
            p.TCPReferenceAngularDeceleration = self._get_f32(all_regs, p_start, get_addr("Parameters.TCP_Refference_Angular_Deceleration"))
            
            # 13. 末端负载参数
            p.LoadMass = self._get_f32(all_regs, p_start, get_addr("Parameters.LoadMass"))
            for i in range(3):
                p.LoadCOG[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.LoadCOG", i+1))
            
            # 14. Tip (末端偏移，6个 REAL)
            for i in range(6):
                p.Tip[i] = self._get_f32(all_regs, p_start, get_addr("Parameters.Tip", i+1))
            
            print("✅ 所有参数读取成功")
            return p
            
        except Exception as e:
            print(f"❌ 读取参数失败: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _area_register_count(self, area: str, start: int) -> int:
        max_end = start
        for entry in self._book.values():
            if entry.area != area or entry.regBase is None:
                continue
            words = max(1, entry.bytesPerElem // 2)
            count = entry.count or 1
            last = entry.regBase + (max(0, count - 1) * (entry.regStride or words)) + words
            max_end = max(max_end, last)
        return max(1, max_end - start)

    def _area_bit_count(self, area: str, start: int) -> int:
        max_end = start
        for entry in self._book.values():
            if entry.area != area or entry.bitBase is None:
                continue
            count = entry.count or 1
            last = entry.bitBase + (max(0, count - 1) * (entry.bitStride or 1)) + 1
            max_end = max(max_end, last)
        return max(1, max_end - start)

    # --- 辅助解析函数 (对齐偏移量) ---
    @staticmethod
    def _get_bit(packed_bits: bytes, block_start: int, absolute_addr: int) -> bool:
        offset = absolute_addr - block_start
        if offset < 0: return False
        byte_idx, bit_idx = divmod(offset, 8)
        if byte_idx >= len(packed_bits): return False
        return (packed_bits[byte_idx] & (1 << bit_idx)) != 0

    def _get_dword(self, regs: List[int], block_start: int, absolute_addr: int) -> int:
        offset = absolute_addr - block_start
        if offset < 0 or offset + 1 >= len(regs): return 0
        return registers_to_dword(regs[offset], regs[offset+1], swap_words=self._com.swap_words, swap_bytes_in_word=self._com.swap_bytes_in_word)

    def _get_f32(self, regs: List[int], block_start: int, absolute_addr: int) -> float:
        offset = absolute_addr - block_start
        if offset < 0 or offset + 1 >= len(regs): return 0.0
        return registers_to_float(regs[offset], regs[offset+1])