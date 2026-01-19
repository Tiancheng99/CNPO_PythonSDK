# Robot SDK - Python V2

机器人控制 SDK，基于 ModBus 通信协议。

## 快速开始

### 安装
详细安装说明请查看 [INSTALL.md](INSTALL.md)

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 SDK（Windows PowerShell）
$env:PYTHONUTF8=1; pip install -e .
```

### 运行示例

1. **moveJ 读取 CSV 并逐个发送**  
   运行前先确保 TODO 的内容（CSV 文件和 IP）修改正确
   ```bash
   python Tests\moveJ_test.py
   ```

2. **moveJ 手动输入任意角度**  
   运行前确保 TP 配置正确
   ```bash
   python Tests\moveJ_test_1.py
   ```

---

## 重要修改说明

### DH Parameters 配置
`Parameters.DH_Parameters` 中的 `strides` 由 `[1,6]` 改为 `[4,1]`：

```json
"Parameters.DH_Parameters": {
    "typeName": "Parameters",
    "field": "DH_Parameters",
    "baseType": "REAL",
    "area": "HoldingRegisters",
    "bytesPerElem": 4,
    "startByteOffset": 0,
    "dims": [6, 4],
    "strides": [4, 1],
    "count": 24,
    "regBase": 0,
    "regStride": 2
}
```

---

## 项目结构

```
SDKPythonV2/
├── Communication/          # ModBus 通信模块
│   ├── ModBusService.py
│   ├── ModBusCommunicator.py
│   └── ...
├── PythonWorkFlow/        # 工作流核心模块
│   └── Core/
│       ├── RobotCore.py
│       └── ...
├── Tests/                 # 测试示例
├── requirements.txt       # 依赖列表
└── setup.py              # 安装配置
```