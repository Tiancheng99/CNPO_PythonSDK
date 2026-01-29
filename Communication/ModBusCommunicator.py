"""ModBusCommunicator

Python 版本的 ModBusCommunicator，仅使用 pymodbus 作为 TCP 客户端实现
"""

from typing import Dict, Tuple, List, Optional

from Communication.CompactEntry import CompactEntry, AddressBook
from Communication.ModBusUtils import (
    registers_to_float, registers_to_uint16, registers_to_dword,
    uint16_to_register, dword_to_registers, float_to_registers
)

from pymodbus.client import ModbusTcpClient as _PymodbusTcpClient  # type: ignore
_HAS_PYMODBUS = True


# 检测 pymodbus 版本支持的参数名
import inspect
_UNIT_PARAM_NAME = None
try:
    # 创建临时客户端实例检测参数名
    _temp_client = _PymodbusTcpClient("localhost", port=502)
    sig = inspect.signature(_temp_client.read_holding_registers)
    
    if 'device_id' in sig.parameters:
        _UNIT_PARAM_NAME = 'device_id'
    elif 'slave' in sig.parameters:
        _UNIT_PARAM_NAME = 'slave'
    elif 'unit' in sig.parameters:
        _UNIT_PARAM_NAME = 'unit'
    else:
        # 默认使用 device_id (pymodbus 3.x 最新版本)
        _UNIT_PARAM_NAME = 'device_id'
except Exception as e:
    # 如果检测失败，默认使用 device_id
    _UNIT_PARAM_NAME = 'device_id'
    print(f"[警告] pymodbus 参数检测失败: {e}，使用默认值: device_id")

print(f"[ModBusCommunicator] 检测到 pymodbus 使用参数名: {_UNIT_PARAM_NAME}")


class ModBusCommunicator:
    AREA_COILS = "Coils"
    AREA_INPUTSTATUS = "InputStatus"
    AREA_HOLDING = "HoldingRegisters"
    AREA_INPUT = "InputRegisters"

    # 地址簿与硬件地址偏移映射表
    ADDRESS_OFFSET_MAP = {}

    def __init__(self, host: str, port: int, unit_id: int = 1,
                 swap_words: bool = False, swap_bytes_in_word: bool = False):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.client: Optional[_PymodbusTcpClient] = None 
        self.is_connected = False
        
        # 寄存器编码/解码的字节序标志
        self.swap_words = bool(swap_words)
        self.swap_bytes_in_word = bool(swap_bytes_in_word)
    
    def _apply_address_offset(self, key: str, addr: int) -> int:
        """应用地址偏移，适配硬件与地址簿的差异"""
        offset = self.ADDRESS_OFFSET_MAP.get(key, 0)
        return addr + offset
    
    def _get_unit_kwargs(self) -> dict:
        """获取 unit_id 参数的字典，自动适配不同 pymodbus 版本"""
        return {_UNIT_PARAM_NAME: self.unit_id}

    def _create_client(self) -> _PymodbusTcpClient:
        """创建 pymodbus TCP 客户端"""
        if not _HAS_PYMODBUS or _PymodbusTcpClient is None:
            raise RuntimeError("pymodbus 未安装，请先安装 pymodbus")
        return _PymodbusTcpClient(self.host, port=self.port)

    def connect(self) -> bool:
        """建立 ModBus 连接"""
        try:
            if self.client is None:
                self.client = self._create_client()
            
            client = self.client
            assert client is not None
            connect_result = client.connect()
            self.client = client
            
            self.is_connected = connect_result
            if self.is_connected:
                print("ModBus 已连接")
            else:
                print("ModBus 连接失败（服务器拒绝）")
            return self.is_connected
        except Exception as ex:
            print(f"ModBus 连接异常：{ex}")
            self.is_connected = False
            return False

    def disconnect(self) -> bool:
        """断开 ModBus 连接"""
        try:
            if self.client is not None:
                self.client.close()
            self.is_connected = False
            print("ModBus 已断开连接")
            return True
        except Exception as ex:
            print(f"ModBus 断开连接异常：{ex}")
            return False

    def dispose(self) -> None:
        """释放 ModBus 资源"""
        try:
            if self.client is not None:
                if hasattr(self.client, 'close'):
                    getattr(self.client, 'close')()
            self.is_connected = False
        except Exception:
            print("ModBus 释放异常")

    # --- Bool 读写 ---
    def read_bool(self, book: Dict[str, CompactEntry], key: str, *idx: int) -> bool:
        area, addr, _ = self._resolve_address(book, key, list(idx))
        if area.lower() == self.AREA_COILS.lower():
            vals = self._read_coils(addr, 1)
            return bool(vals[0])
        if area.lower() == self.AREA_INPUTSTATUS.lower():
            vals = self._read_discrete_inputs(addr, 1)
            return bool(vals[0])
        raise ValueError(f"不支持的位区域: {area}")

    def write_bool(self, book: Dict[str, CompactEntry], key: str, value: bool, *idx: int) -> None:
        area, addr, _ = self._resolve_address(book, key, list(idx))
        if area.lower() != self.AREA_COILS.lower():
            raise ValueError("仅 Coils 区域支持写入")
        self._write_single_coil(addr, value)

    # --- UInt16 读写 ---
    def read_uint(self, book: Dict[str, CompactEntry], key: str, *idx: int) -> int:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if words != 1:
            raise ValueError("目标不是 1-寄存器类型")
        regs = self._read_registers(area, addr, 1)
        return registers_to_uint16(regs[0], swap_bytes_in_word=self.swap_bytes_in_word)

    def write_uint(self, book: Dict[str, CompactEntry], key: str, value: int, *idx: int) -> None:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if area.lower() not in (self.AREA_HOLDING.lower(), self.AREA_INPUT.lower()):
            raise ValueError("仅支持向 HoldingRegisters 或 InputRegisters 写入")
        if words != 1:
            raise ValueError("目标不是 1-寄存器类型")
        reg = uint16_to_register(value, swap_bytes_in_word=self.swap_bytes_in_word)
        self._write_single_register(addr, reg)

    # --- Real/Float 读写 ---
    def read_real(self, book: Dict[str, CompactEntry], key: str, *idx: int) -> float:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if words != 2:
            raise ValueError("目标不是 2-寄存器类型")
        # 应用地址偏移（与 write_real 保持一致）
        addr = self._apply_address_offset(key, addr)
        regs = self._read_registers(area, addr, 2)
        return registers_to_float(regs[0], regs[1], swap_words=self.swap_words,
                                   swap_bytes_in_word=self.swap_bytes_in_word)

    def write_real(self, book: Dict[str, CompactEntry], key: str, value: float, *idx: int) -> None:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if area.lower() != self.AREA_HOLDING.lower():
            raise ValueError("仅支持向 HoldingRegisters 写入")
        if words != 2:
            raise ValueError("目标不是 2-寄存器类型")
        # 应用地址偏移
        addr = self._apply_address_offset(key, addr)
        hi, lo = float_to_registers(value, swap_words=self.swap_words,
                                     swap_bytes_in_word=self.swap_bytes_in_word)
        self._write_multiple_registers(addr, [hi, lo])

    # --- Dword 读写 ---
    def read_dword(self, book: Dict[str, CompactEntry], key: str, *idx: int) -> int:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if words != 2:
            raise ValueError("目标不是 2-寄存器类型")
        # 应用地址偏移（与 write_dword 保持一致）
        addr = self._apply_address_offset(key, addr)
        regs = self._read_registers(area, addr, 2)
        return registers_to_dword(regs[0], regs[1], swap_words=self.swap_words,
                                  swap_bytes_in_word=self.swap_bytes_in_word)

    def write_dword(self, book: Dict[str, CompactEntry], key: str, value: int, *idx: int) -> None:
        area, addr, words = self._resolve_address(book, key, list(idx))
        if area.lower() != self.AREA_HOLDING.lower():
            raise ValueError("仅支持向 HoldingRegisters 写入")
        if words != 2:
            raise ValueError("目标不是 2-寄存器类型")
        hi, lo = dword_to_registers(value, swap_words=self.swap_words,
                                     swap_bytes_in_word=self.swap_bytes_in_word)
        self._write_multiple_registers(addr, [hi, lo])

    # --- 批量读操作 ---
    def read_discrete_inputs_block(self, start: int, quantity: int) -> bytes:
        '''批量读取离散操作
        输入：起始地址，位数量
        输出：字节数组，按位打包（每字节低位在前）
        '''
        if not self.is_connected:
            raise RuntimeError("未连接")
        
        if quantity <= 0:
            return b'' 
        result = bytearray((quantity + 7) // 8)
        remaining = quantity
        addr = start
        dst = 0
        while remaining > 0:
            to_read = min(remaining, 2000)
            chunk = self._read_discrete_inputs(addr, to_read)
            chunk_bytes = bytearray((to_read + 7) // 8)
            for i, bit in enumerate(chunk):
                if bit:
                    byte_index = i // 8
                    bit_index = i % 8
                    chunk_bytes[byte_index] |= (1 << bit_index)
            copy = min(len(chunk_bytes), len(result) - dst)
            result[dst:dst+copy] = chunk_bytes[:copy]
            addr += to_read
            remaining -= to_read
            dst += copy
        return bytes(result)

    def read_input_registers_block(self, start: int, count: int) -> List[int]:
        """批量读取输入寄存器 (Input Registers)
        输入：起始地址，寄存器数量
        输出：寄存器值列表
        """
        if not self.is_connected:
            raise RuntimeError("未连接")
        
        if count <= 0:
            return []
        result: List[int] = []
        remaining = count
        addr = start
        while remaining > 0:
            # Modbus 协议单次通常限制 125 个寄存器，这里设置安全值 120
            to_read = min(remaining, 120)
            regs = self._read_input_registers(addr, to_read)
            result.extend(regs)
            addr += to_read
            remaining -= to_read
        return result

    def read_holding_registers_block(self, start: int, count: int) -> List[int]:
        """批量读取保持寄存器 (Holding Registers) [新增方法]
        输入：起始地址，寄存器数量
        输出：寄存器值列表
        """
        if not self.is_connected:
            raise RuntimeError("未连接")
        
        if count <= 0:
            return []
        result: List[int] = []
        remaining = count
        addr = start
        while remaining > 0:
            # Modbus 协议单次通常限制 125 个寄存器，这里设置安全值 120
            to_read = min(remaining, 120)
            # 调用底层的 read_holding_registers
            rr = self.client.read_holding_registers(
                address=addr,
                count=to_read,
                **self._get_unit_kwargs()
            )
            if hasattr(rr, 'registers'):
                result.extend(rr.registers)
            elif hasattr(rr, 'isError') and rr.isError():
                raise RuntimeError(f"读取保持寄存器失败: {rr}")
            else:
                # 兼容部分 pymodbus 版本可能的返回行为
                result.extend(list(rr))

            addr += to_read
            remaining -= to_read
        return result
   
    def _resolve_address(self, book: Dict[str, CompactEntry], key: str, idx: Optional[List[int]] = None) -> Tuple[str, int, int]:
        """解析地址"""
        if idx is None:
            idx = []
        return AddressBook.address_of(book, key, *idx)

    # --- 低级读操作 ---
    def _read_coils(self, addr: int, count: int):
        if not self.is_connected or self.client is None:
            raise ConnectionError("Not connected")
        
        try:
            rr = self.client.read_coils(
                address=addr, 
                count=count,
                **self._get_unit_kwargs()
            )
            
            if hasattr(rr, 'bits'):
                return list(rr.bits)
            else:
                raise RuntimeError(f"响应格式错误，无 bits 属性：{rr}")
        
        except Exception as e:
            print(f"read_coils 调用失败：{type(e)} - {e}")
            raise
    
    def _read_discrete_inputs(self, addr: int, count: int) -> List[bool]:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Not connected")
        
        try:
            response = self.client.read_discrete_inputs(
                address=addr, 
                count=count,
                **self._get_unit_kwargs()
            )
            
            if hasattr(response, 'isError') and response.isError():
                print(f"Modbus错误响应：{response}")
                raise RuntimeError(f"读取离散输入失败：地址={addr}, 数量={count}")
            
            if not hasattr(response, 'bits'):
                raise RuntimeError(f"无效的响应格式：没有bits属性，响应={response}")
            
            return list(response.bits)
        
        except Exception as e:
            print(f"_read_discrete_inputs执行失败：{type(e)} - {e}")
            raise

    def _read_registers(self, area: str, addr: int, count: int) -> List[int]:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Not connected")
        
        try:
            if area.lower() == self.AREA_HOLDING.lower():
                rr = self.client.read_holding_registers(
                    address=addr,  
                    count=count,
                    **self._get_unit_kwargs()
                )
            elif area.lower() == self.AREA_INPUT.lower():
                rr = self.client.read_input_registers(
                    address=addr,
                    count=count,
                    **self._get_unit_kwargs()
                )
            else:
                raise ValueError(f"不支持的寄存器区域: {area}")

            if hasattr(rr, 'registers'):
                return list(rr.registers)
            return list(rr)
    
        except Exception as e:
            print(f"读取寄存器失败（区域={area}, 地址={addr}, 数量={count}）：{type(e)} - {e}")
            raise
    
    def _read_input_registers(self, addr: int, count: int) -> List[int]:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Not connected")
        
        try:
            rr = self.client.read_input_registers(
                address=addr,  
                count=count,
                **self._get_unit_kwargs()
            )
            
            if hasattr(rr, 'registers'):
                return list(rr.registers)
            else:
                raise RuntimeError(f"响应格式错误，无registers属性：{rr}")
        
        except Exception as e:
            print(f"read_input_registers调用失败：{type(e)} - {e}")
            raise

    # --- 低级写操作 ---
    def _write_single_coil(self, addr: int, value: bool) -> None:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Not connected")
        
        try:
            if hasattr(self.client, 'write_coil'):
               
                result = self.client.write_coil(addr, value, **self._get_unit_kwargs())
            
                return

        except Exception as ex:
            print(f"[ERROR] 写入单个线圈失败: {ex}")
            raise RuntimeError(f"写入单个线圈失败：{ex}") from ex
        
        raise RuntimeError("客户端不支持写单个线圈的方法")
    
    def _write_single_register(self, addr: int, value: int) -> None:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Modbus 未连接")
        
        try:
           
            response = self.client.write_register(
                address=addr,       
                value=value,
                **self._get_unit_kwargs()
            )
            
            if response.isError():
                print(f"[ERROR] 写入失败: 地址={addr}, 值={value}, 错误码={response.exception_code}")
                raise RuntimeError(
                    f"写入失败：地址={addr}, 值={value}, "
                    f"错误码={response.exception_code}"
                )
           
            
        except Exception as ex:
            raise RuntimeError( f"写入异常（地址={addr}）：{str(ex)}") from ex

    def _write_multiple_registers(self, addr: int, values: List[int]) -> None:
        if not self.is_connected or self.client is None:
            raise ConnectionError("Modbus 未连接")
        
        if not values:
            raise ValueError("写入的值列表不能为空")
        
        try:
            
            response = self.client.write_registers(
                address=addr,       
                values=values,
                **self._get_unit_kwargs()
            )
            
            if response.isError():
                print(f"[ERROR] 写入失败: 地址={addr}, 数量={len(values)}, 错误码={response.exception_code}")
                raise RuntimeError(
                    f"写入失败：地址={addr}, 数量={len(values)}, "
                    f"错误码={response.exception_code}"
                )
            
        except Exception as ex:
            print(f"[ERROR] 写入异常: {ex}")
            raise RuntimeError( f"写入异常（地址={addr}）：{str(ex)}" ) from ex

__all__ = ['ModBusCommunicator']