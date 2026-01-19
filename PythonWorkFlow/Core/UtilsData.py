from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

class UtilsData:
    def get_double_value_from_bytes(self,byte_list,address):
        target_registers = byte_list[address:address + 4]
        result = BinaryPayloadDecoder.fromRegisters(target_registers, byteorder=Endian.BIG, wordorder=Endian.LITTLE).decode_64bit_float()
        return result

    def get_short_value_from_bytes(self, byte_list,address):
        target_registers = byte_list[address:address + 1]
        result = BinaryPayloadDecoder.fromRegisters(target_registers, byteorder=Endian.BIG, wordorder=Endian.LITTLE).decode_16bit_int()
        return result

    # 读取bool变量
    def get_bit_value_from_bytes(self, byte_list,address):
        return byte_list[address]
