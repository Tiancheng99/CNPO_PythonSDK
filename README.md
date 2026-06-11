# Robot SDK Python V2

Robot SDK Python V2 is a ModBus TCP based robot control SDK with a Tkinter desktop GUI. It provides connection management, robot status monitoring, enabling/disabling, reset, point-to-point MoveJ, CSV trajectory execution, and joint zero calibration.

The project is intended for both development/debugging and field deployment. For field use, the GUI can be packaged into a standalone Windows executable with an editable `Config` directory next to the exe.

## Features

- ModBus TCP communication through `pymodbus`.
- High-level `RobotCore` API for robot commands and status access.
- Tkinter GUI for operators:
  - Connect/disconnect robot PLC.
  - Select IP and joint count at startup.
  - Enable, disable, reset, and stop.
  - Run MoveJ with degree/radian input switching.
  - Load CSV points and execute one point at a time with Enter.
  - Execute a full CSV sequence.
  - Guard MoveJ execution when the robot is not enabled.
  - Trigger joint zero calibration from degree input.
- Runtime configuration through JSON files in `Config/`.
- PyInstaller packaging scripts for Windows and Linux.

## Project Layout

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

## Requirements

- Python 3.10 or newer is recommended.
- Robot PLC reachable over ModBus TCP, usually port `502`.
- Python packages:

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

## Development Install

From the repository root:

```bash
pip install -r requirements.txt
pip install -e .
```

Quick import check:

```bash
python -c "import Communication; import PythonWorkFlow; print('SDK import OK')"
```

## Run The GUI From Source

```bash
python apps/robot_gui.py
```

Workflow:

1. Select the robot IP and joint count.
2. Click `连接`.
3. Before any MoveJ command, click `使能 + MoveJoint`.
4. Use point-to-point MoveJ or load a CSV trajectory.
5. Use `去使能`, `复位`, or `停止` as needed.

MoveJ commands are blocked when `PowerOn` is false, and the GUI will prompt the operator to enable the robot first.

## CSV Format

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

## Joint Zero Calibration

The GUI provides a `标定角度` input box. Enter comma-separated joint angles in degrees, for example:

```text
0, 10, -20, 0, 0, 0, 0
```

Click `标定零位` to:

1. Convert the degree values to radians.
2. Write `Parameters.CalibrationJointPositions`.
3. Switch to `Calibration` mode.
4. Pulse `Instructions.Calibrate_Joint_Position`.

The same behavior is available from:

```bash
python Tests/calibrate_joint_zero.py --ip 192.168.1.253 --positions "0,10,-20,0,0,0,0" --degrees --yes
```

## Runtime Configuration

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

## Package The GUI

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

## Common Troubleshooting

- `ModbusClientMixin... unexpected keyword argument 'device_id'`
  - Use `pymodbus==3.11.3`.
- Module import fails
  - Run commands from the repository root or install with `pip install -e .`.
- GUI connects but MoveJ is blocked
  - Click `使能 + MoveJoint` first and confirm `PowerOn=True`.
- Field configuration changes
  - Edit JSON files under the exe sibling `Config/` directory. Repackaging is not required for address-book or parameter changes.

## Safety Notes

This SDK sends real robot motion commands. Confirm network target, joint count, address book, and workspace safety before enabling or moving the robot.
