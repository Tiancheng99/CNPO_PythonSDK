# Robot SDK Python V2

[中文](#中文说明) | [English](#english)

---

## 中文说明

Robot SDK Python V2 是一个基于 ModBus TCP 的机器人控制 SDK，并提供 Tkinter 上位机界面。项目既可以作为 Python SDK 用于二次开发，也可以打包成现场使用的 Windows 可执行程序。

上位机适合现场调试和基础操作，支持连接机器人 PLC、查看状态、上使能/去使能、复位、停止、点对点 MoveJ、CSV 点位执行，以及关节零位标定。

### 主要功能

- 基于 `pymodbus` 的 ModBus TCP 通信。
- `RobotCore` 高层接口，封装机器人连接、状态读取、参数写入和运动指令。
- Tkinter 上位机界面：
  - 启动时选择机器人 IP 和关节数。
  - 连接/断开机器人 PLC。
  - 上使能、去使能、复位、停止。
  - 点对点 MoveJ，支持角度/弧度切换。
  - 加载 CSV 点位，支持按 Enter 单步执行。
  - 支持 CSV 按顺序连续执行。
  - MoveJ 前自动检查是否已上使能；未上使能时会阻止运动并提示。
  - 支持输入关节角度并触发关节零位标定。
- 通过 `Config/` 下的 JSON 文件配置地址表、默认参数和关节数。
- 提供 Windows/Linux PyInstaller 打包脚本。

### 项目结构

```text
SDKPythonV2/
  apps/
    robot_gui.py                  # Tkinter 上位机入口
  Communication/
    CompactEntry.py               # 地址表解析
    ModBusCommunicator.py         # 底层 ModBus 读写
    ModBusService.py              # 异步服务和读写队列
  Config/
    RobotConfig.json              # 机器人运行配置
    DefaultRobotParameters.json   # 默认机器人参数
    modbus_address_book.*.json    # PLC 地址表
  PythonWorkFlow/
    Core/
      RobotCore.py                # SDK 主入口
      Basic.py                    # 参数、模式、状态模型
  Tests/
    moveJ.py
    calibrate_joint_zero.py
    read_joint_angles.py
  scripts/
    build_gui_windows.bat
    build_gui_linux.sh
  requirements.txt
  requirements-build.txt
  robot_gui.spec
  setup.py
```

### 环境要求

- 推荐 Python 3.10 或更新版本。
- 现场电脑需要能访问机器人 PLC 的 ModBus TCP 地址，默认端口通常为 `502`。
- 安装运行依赖：

```bash
pip install -r requirements.txt
```

如果需要打包上位机：

```bash
pip install -r requirements-build.txt
```

Windows PowerShell 如遇中文路径或编码问题，可先设置：

```powershell
$env:PYTHONUTF8=1
```

### 开发安装

在项目根目录执行：

```bash
pip install -r requirements.txt
pip install -e .
```

快速验证导入：

```bash
python -c "import Communication; import PythonWorkFlow; print('SDK import OK')"
```

### 从源码运行上位机

```bash
python apps/robot_gui.py
```

基本流程：

1. 启动后选择机器人 IP 和关节数。
2. 点击 `连接`。
3. 执行 MoveJ 前先点击 `使能 + MoveJoint`。
4. 使用点对点 MoveJ，或加载 CSV 点位。
5. 根据需要使用 `去使能`、`复位`、`停止`。

如果 `PowerOn=False`，上位机会阻止 MoveJ，并提示先上使能。

### CSV 点位格式

推荐格式：

```csv
ID,J1,J2,J3,J4,J5,J6,J7,Info
1,0,0,0,0,0,0,0,Home
2,0,0,0,0,10,0,10,Pick
```

说明：

- `J1...Jn` 会被识别为关节目标，单位为角度。
- `Info` 可选，用于显示点位说明。
- `下一点(Enter)` 每次执行一个点位。
- `按顺序执行` 会连续执行整个 CSV 队列。

### 关节零位标定

上位机提供 `标定角度` 输入框。输入逗号分隔的关节角度，例如：

```text
0, 10, -20, 0, 0, 0, 0
```

点击 `标定零位` 后，上位机会：

1. 将输入角度转换为弧度。
2. 写入 `Parameters.CalibrationJointPositions`。
3. 切换到 `Calibration` 模式。
4. 触发 `Instructions.Calibrate_Joint_Position` 上升沿。

同样的功能也可以通过脚本触发：

```bash
python Tests/calibrate_joint_zero.py --ip 192.168.1.253 --positions "0,10,-20,0,0,0,0" --degrees --yes
```

### 运行配置

`Config/RobotConfig.json` 用于选择机械臂、关节数、地址表和默认参数文件：

```json
{
  "default_arm": "arm1",
  "arms": {
    "arm1": {
      "joint_count": 7,
      "address_book": "Config/modbus_address_book.compact.json",
      "parameter_file": "Config/DefaultRobotParameters.json"
    }
  }
}
```

切换不同机械臂或关节数时，需要同步检查：

- `joint_count`
- `DefaultRobotParameters.json` 中各关节数组长度
- 地址表中关节数组相关条目的 `dims`、`count`、`strides`、`regBase`、`bitBase`

SDK 启动时会检查常用关节地址项。如果地址表缺少关键项，或数组维度小于配置关节数，会打印配置提醒。

### 打包上位机

Windows：

```bat
scripts\build_gui_windows.bat
```

Linux：

```bash
chmod +x scripts/build_gui_linux.sh
scripts/build_gui_linux.sh
```

Windows 打包输出：

```text
dist\RobotSDKV2_GUI_windows\
  RobotSDKV2_GUI.exe
  README.txt
  Config\
```

现场交付时请发送整个 `RobotSDKV2_GUI_windows` 文件夹，不要只发送单个 exe。运行时需要同级 `Config` 目录。

### 常见问题

- 出现 `ModbusClientMixin... unexpected keyword argument 'device_id'`
  - 请确认使用 `pymodbus==3.11.3`。
- 找不到模块
  - 请在项目根目录运行，或先执行 `pip install -e .`。
- GUI 已连接但 MoveJ 被阻止
  - 请先点击 `使能 + MoveJoint`，并确认状态中 `PowerOn=True`。
- 现场更换地址表或默认参数
  - 修改 exe 同级 `Config/` 目录下的 JSON 文件即可，不需要重新打包。

### 安全提示

本 SDK 会发送真实机器人运动指令。上使能和运动前，请确认目标 IP、关节数、地址表、工作空间和现场安全状态。

---

## English

Robot SDK Python V2 is a ModBus TCP based robot control SDK with a Tkinter desktop GUI. It can be used both as a Python SDK for development and as a packaged desktop tool for field operation.

The GUI supports robot PLC connection, status monitoring, enable/disable, reset, stop, point-to-point MoveJ, CSV point execution, and joint zero calibration.

### Features

- ModBus TCP communication through `pymodbus`.
- High-level `RobotCore` API for connection, status, parameters, and commands.
- Tkinter GUI:
  - Select robot IP and joint count at startup.
  - Connect/disconnect robot PLC.
  - Enable, disable, reset, and stop.
  - Run MoveJ with degree/radian input switching.
  - Load CSV points and execute one point at a time with Enter.
  - Execute a full CSV sequence.
  - Block MoveJ when the robot is not enabled.
  - Trigger joint zero calibration from degree input.
- Runtime configuration through JSON files in `Config/`.
- PyInstaller packaging scripts for Windows and Linux.

### Project Layout

```text
SDKPythonV2/
  apps/
    robot_gui.py                  # Tkinter GUI entry point
  Communication/
    CompactEntry.py               # Address book parser
    ModBusCommunicator.py         # Low-level ModBus reads/writes
    ModBusService.py              # Async service and queue
  Config/
    RobotConfig.json              # Robot selection and runtime config
    DefaultRobotParameters.json   # Default robot parameters
    modbus_address_book.*.json    # PLC address books
  PythonWorkFlow/
    Core/
      RobotCore.py                # Main SDK facade
      Basic.py                    # Parameters, modes, status models
  Tests/
    moveJ.py
    calibrate_joint_zero.py
    read_joint_angles.py
  scripts/
    build_gui_windows.bat
    build_gui_linux.sh
  requirements.txt
  requirements-build.txt
  robot_gui.spec
  setup.py
```

### Requirements

- Python 3.10 or newer is recommended.
- The robot PLC must be reachable over ModBus TCP, usually port `502`.
- Install runtime dependencies:

```bash
pip install -r requirements.txt
```

For packaging:

```bash
pip install -r requirements-build.txt
```

On Windows PowerShell, if you hit encoding issues:

```powershell
$env:PYTHONUTF8=1
```

### Development Install

From the repository root:

```bash
pip install -r requirements.txt
pip install -e .
```

Quick import check:

```bash
python -c "import Communication; import PythonWorkFlow; print('SDK import OK')"
```

### Run The GUI From Source

```bash
python apps/robot_gui.py
```

Basic workflow:

1. Select the robot IP and joint count.
2. Click `连接`.
3. Before any MoveJ command, click `使能 + MoveJoint`.
4. Use point-to-point MoveJ or load a CSV trajectory.
5. Use `去使能`, `复位`, or `停止` as needed.

MoveJ commands are blocked when `PowerOn=False`; the GUI will prompt the operator to enable the robot first.

### CSV Format

Recommended format:

```csv
ID,J1,J2,J3,J4,J5,J6,J7,Info
1,0,0,0,0,0,0,0,Home
2,0,0,0,0,10,0,10,Pick
```

Notes:

- `J1...Jn` columns are interpreted as joint targets in degrees.
- `Info` is optional and displayed in the GUI/log.
- `下一点(Enter)` executes one point at a time.
- `按顺序执行` runs the whole loaded sequence.

### Joint Zero Calibration

The GUI provides a `标定角度` input box. Enter comma-separated joint angles in degrees, for example:

```text
0, 10, -20, 0, 0, 0, 0
```

Click `标定零位` to:

1. Convert degree values to radians.
2. Write `Parameters.CalibrationJointPositions`.
3. Switch to `Calibration` mode.
4. Pulse `Instructions.Calibrate_Joint_Position`.

The same behavior is available from:

```bash
python Tests/calibrate_joint_zero.py --ip 192.168.1.253 --positions "0,10,-20,0,0,0,0" --degrees --yes
```

### Runtime Configuration

`Config/RobotConfig.json` selects the robot arm, joint count, address book, and default parameter file:

```json
{
  "default_arm": "arm1",
  "arms": {
    "arm1": {
      "joint_count": 7,
      "address_book": "Config/modbus_address_book.compact.json",
      "parameter_file": "Config/DefaultRobotParameters.json"
    }
  }
}
```

When changing robot type, keep these in sync:

- `joint_count`
- `DefaultRobotParameters.json` array lengths
- address-book entries for joint arrays, including `dims`, `count`, `strides`, `regBase`, and `bitBase`

The SDK prints configuration warnings at startup if common joint entries are missing or shorter than the configured joint count.

### Package The GUI

Windows:

```bat
scripts\build_gui_windows.bat
```

Linux:

```bash
chmod +x scripts/build_gui_linux.sh
scripts/build_gui_linux.sh
```

Windows output:

```text
dist\RobotSDKV2_GUI_windows\
  RobotSDKV2_GUI.exe
  README.txt
  Config\
```

Send the whole output folder to field users. Do not send only the executable; the sibling `Config` directory is required for runtime configuration.

### Common Troubleshooting

- `ModbusClientMixin... unexpected keyword argument 'device_id'`
  - Use `pymodbus==3.11.3`.
- Module import fails
  - Run commands from the repository root or install with `pip install -e .`.
- GUI connects but MoveJ is blocked
  - Click `使能 + MoveJoint` first and confirm `PowerOn=True`.
- Field configuration changes
  - Edit JSON files under the exe sibling `Config/` directory. Repackaging is not required for address-book or parameter changes.

### Safety Notes

This SDK sends real robot motion commands. Confirm network target, joint count, address book, workspace, and field safety before enabling or moving the robot.
