"""ModBusUtils

Python 版本的 ModBusUtils

提供一组工具函数，将 Modbus 寄存器（16-bit）与常见类型之间互相转换。

注意：
- 寄存器为 16-bit（1 寄存器 = 2 字节），两个寄存器组合为 32-bit 值或 IEEE754 float。
- 字节/字的顺序可能不同：
  - swap_words: 是否交换两个寄存器的位置（即寄存器对调，word order swap，C# 中的 CD AB 场景）。
  - swap_bytes_in_word: 是否在每个寄存器内部交换两个字节（byte swap in word，C# 中的 BA 场景）。

"""

from typing import Tuple
import struct


def _swap_bytes_in_word(value: int) -> int:
    """在 16-bit 寄存器内部交换高字节和低字节。

    例如：0xABCD -> 0xCDAB
    """
    hi = (value >> 8) & 0xFF
    lo = value & 0xFF
    return (lo << 8) | hi


def registers_to_float(hi: int, lo: int, *, swap_words: bool = True, swap_bytes_in_word: bool = False) -> float:
    """将两个 16-bit 寄存器解码为 float。

    参数:
      hi, lo: 两个寄存器值（0..0xFFFF）。通常 hi 表示第一个寄存器，lo 表示第二个。
      swap_words: 如果 True，表示寄存器顺序要交换（hi<->lo）。
      swap_bytes_in_word: 如果 True，表示每个寄存器内部字节需对换。

    返回 IEEE-754 单精度浮点数。
    """
    # 限定为 16-bit
    hi &= 0xFFFF
    lo &= 0xFFFF

    if swap_words:
        hi, lo = lo, hi

    if swap_bytes_in_word:
        hi = _swap_bytes_in_word(hi)
        lo = _swap_bytes_in_word(lo)

    # 组合为大端字节序 [b0,b1,b2,b3]，其中 b0 是 hi 的高字节
    b0 = (hi >> 8) & 0xFF
    b1 = hi & 0xFF
    b2 = (lo >> 8) & 0xFF
    b3 = lo & 0xFF

    # 按大端排列构造 bytes，然后根据系统端序使用 struct.unpack
    raw = bytes([b0, b1, b2, b3])
    # struct.unpack 使用本机端序的格式，如果要明确大端，用 >f
    # 因为 raw 已是大端顺序，直接用 '>f' 得到正确结果
    return struct.unpack('>f', raw)[0]


def registers_to_uint16(reg: int, *, swap_bytes_in_word: bool = False) -> int:
    """将单个 16-bit 寄存器按配置返回 uint16（0..65535）。
    如果 swap_bytes_in_word 为 True，则在返回前交换寄存器内字节。
    """
    reg &= 0xFFFF
    if swap_bytes_in_word:
        reg = _swap_bytes_in_word(reg)
    return reg


def registers_to_dword(hi: int, lo: int, *, swap_words: bool = False, swap_bytes_in_word: bool = False) -> int:
    """从两个寄存器构造一个 32-bit 无符号整数（返回 Python int）。"""
    hi &= 0xFFFF
    lo &= 0xFFFF
    if swap_words:
        hi, lo = lo, hi
    if swap_bytes_in_word:
        hi = _swap_bytes_in_word(hi)
        lo = _swap_bytes_in_word(lo)
    # hi 为高 16-bit, lo 为低 16-bit
    return (hi << 16) | lo


def uint16_to_register(value: int, *, swap_bytes_in_word: bool = False) -> int:
    """将 16-bit 值转换为寄存器表示（考虑寄存器内字节对调）"""
    reg = int(value) & 0xFFFF
    if swap_bytes_in_word:
        reg = _swap_bytes_in_word(reg)
    return reg


def dword_to_registers(value: int, *, swap_words: bool = False, swap_bytes_in_word: bool = False) -> Tuple[int, int]:
    """将 32-bit 无符号整数分解为两个寄存器（返回 (hi, lo)），可选对字/字节进行交换。

    说明：返回的 hi 对应要写入的第一个寄存器，lo 对应第二个寄存器（默认大端 hi 在前）。
    """
    value &= 0xFFFFFFFF
    hi = (value >> 16) & 0xFFFF
    lo = value & 0xFFFF

    if swap_bytes_in_word:
        hi = _swap_bytes_in_word(hi)
        lo = _swap_bytes_in_word(lo)

    if swap_words:
        hi, lo = lo, hi

    return hi, lo


def float_to_registers(value: float, *, swap_words: bool = False, swap_bytes_in_word: bool = False) -> Tuple[int, int]:
    """将 float 编码为两个寄存器（hi, lo），支持字与字节对调配置。

    过程：将 float 转为大端字节序 [A,B,C,D]，可对每寄存器内部做字节对调（BA），
    并根据 swap_words 决定寄存器顺序。
    """
    # 生成大端字节序表示
    raw = struct.pack('>f', float(value))  # big-endian float -> 4 bytes
    b0, b1, b2, b3 = raw[0], raw[1], raw[2], raw[3]

    if swap_bytes_in_word:
        b0, b1 = b1, b0
        b2, b3 = b3, b2

    hi = ((b0 & 0xFF) << 8) | (b1 & 0xFF)
    lo = ((b2 & 0xFF) << 8) | (b3 & 0xFF)

    if swap_words:
        hi, lo = lo, hi

    return hi, lo


__all__ = [
    'registers_to_float', 'registers_to_uint16', 'registers_to_dword',
    'uint16_to_register', 'dword_to_registers', 'float_to_registers'
]
