"""CompactEntry
    Python 版本的 CompactEntry 和 AddressBook
"""
import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Dict, Tuple, List, Optional


@dataclass
class CompactEntry:
    """描述单个变量的地址信息项"""
    typeName: str = ""
    field: str = ""
    baseType: str = ""
    area: str = ""
    bytesPerElem: int = 0
    startByteOffset: int = 0
    dims: List[int] = dc_field(default_factory=list)
    strides: List[int] = dc_field(default_factory=list)
    count: int = 0
    bitBase: Optional[int] = None
    bitStride: Optional[int] = None
    regBase: Optional[int] = None
    regStride: Optional[int] = None

class AddressBook:
    @staticmethod
    def load(path: str) -> Dict[str, CompactEntry]:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            entries: Dict[str, CompactEntry] = {}
            allowed_fields = set(CompactEntry.__dataclass_fields__.keys())
            for k, v in (data or {}).items():
                if isinstance(v, dict):
                    # 强制丢弃 note 等不需要字段
                    v = dict(v)
                    v.pop("note", None)
                    clean = {fk: fv for fk, fv in v.items() if fk in allowed_fields}
                    entries[k] = CompactEntry(**clean)
            return entries

    @staticmethod
    def _get_entry_case_insensitive(book: Dict[str, CompactEntry], key: str) -> CompactEntry:
        # 先精确匹配
        if key in book:
            return book[key]
        # 再尝试不区分大小写匹配
        low = key.lower()
        for k, v in book.items():
            if k.lower() == low:
                return v
        raise KeyError(f"未找到键: {key}")

    @staticmethod
    def address_of(book: Dict[str, CompactEntry], key: str, *indices: int) -> Tuple[str, int, int]:
        """根据键与索引计算变量的 Modbus 地址信息 (area, address, words)"""
        e = AddressBook._get_entry_case_insensitive(book, key)

        lin = AddressBook.linear_index(e, list(indices))

        if e.baseType and e.baseType.upper() == "BOOL":
            addr = (e.bitBase or 0) + (e.bitStride or 0) * lin
            return e.area, addr, 0
        else:
            addr = (e.regBase or 0) + (e.regStride or 0) * lin
            words = max(1, e.bytesPerElem // 2)
            return e.area, addr, words

    @staticmethod
    def parse_expr(expr: str) -> Tuple[str, List[int]]:
        m = re.match(r'^(?P<key>[^\[]+)(\[(?P<idx>[\d,\s]+)\])?$', expr.strip())
        if not m:
            raise ValueError(f"无效表达式: {expr}")
        key = m.group('key').strip()
        if not m.group('idx'):
            return key, []
        idx = [int(s.strip()) for s in m.group('idx').split(',')]
        return key, idx

    @staticmethod
    def linear_index(e: CompactEntry, indices: List[int]) -> int:
        if not e.dims:
            if indices:
                raise ValueError("标量不应提供索引")
            return 0
        if len(indices) != len(e.dims):
            raise ValueError(f"索引维度不匹配，应为 {len(e.dims)} 个索引")
        lin = 0
        for k, i in enumerate(indices):
            if i < 1 or i > e.dims[k]:
                raise IndexError(f"第 {k+1} 维索引越界：{i} not in [1..{e.dims[k]}]")
            lin += (i - 1) * e.strides[k]
        return lin
