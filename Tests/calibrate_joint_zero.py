'''
触发 Codesys 关节零位标定。

对应 PLC 逻辑：
- 写 Parameters.CalibrationJointPositions 作为标定目标关节位置（单位 rad）
- 脉冲 Instructions.Calibrate_Joint_Position
- PLC 内部执行 Joints_Calibration[1..7]
'''

import argparse
import asyncio
import math
import sys
from typing import List

from PythonWorkFlow.Core.RobotCore import RobotCore
from PythonWorkFlow.Core.Basic import ControlMode


DEFAULT_IP = "192.168.1.253"


def parse_joint_values(raw: str, joint_count: int, degrees: bool) -> List[float]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != joint_count:
        raise ValueError(f"需要 {joint_count} 个关节值，实际收到 {len(parts)} 个")
    values = [float(p) for p in parts]
    if degrees:
        values = [math.radians(v) for v in values]
    return values


async def wait_for_connection(rc: RobotCore, timeout: float = 10.0) -> None:
    print("等待 ModBus 连接和状态读取线程启动...", end="", flush=True)
    loops = max(1, int(timeout / 0.1))
    for _ in range(loops):
        if rc.connected and rc.init_complete:
            print("完成")
            return
        print(".", end="", flush=True)
        await asyncio.sleep(0.1)
    print("超时")
    raise RuntimeError("无法连接到机器人，请检查 IP、网线、PLC ModBus 服务和地址簿配置")


def print_status(rc: RobotCore, label: str) -> None:
    s = rc.robot_status
    print(f"\n[{label}]")
    print(f"PowerOn={s.PowerOn} Moving={s.Moving} Error={s.Error} ErrorId={s.ErrorId} ActualMovementMode={s.ActualMovementMode}")
    print(f"JointState={list(s.JointState or [])}")
    print(f"JointError={list(s.JointError or [])}")
    print(f"JointErrorId={list(s.JointErrorId or [])}")
    deg = [math.degrees(v) for v in list(s.JointActualPosition or [])]
    print("JointActualPosition(deg)=[" + ", ".join(f"{v:.3f}" for v in deg) + "]")


async def main_task(args: argparse.Namespace) -> None:
    rc = RobotCore(target_ip=args.ip, auto_initialize_robot=False)
    try:
        await wait_for_connection(rc)
        await asyncio.sleep(0.5)
        print_status(rc, "触发前")

        if args.enable:
            print("\n发送机器人使能指令...")
            rc.RobotEnable_sync()
            await asyncio.sleep(args.enable_wait)
            print_status(rc, "使能后")

        if args.idle_mode:
            print("\n切换到 Idle/Calibration 模式...")
            rc.SetControlMode_sync(ControlMode.Calibration)
            await asyncio.sleep(0.5)

        if args.positions is not None:
            positions = parse_joint_values(args.positions, rc.joint_count, args.degrees)
            print("\n写入 CalibrationJointPositions(rad): " + str([round(v, 6) for v in positions]))
            rc.RobotSetCalibrationJointPositions_sync(positions)
            await asyncio.sleep(0.3)
        else:
            print("\n未写入 CalibrationJointPositions，使用 PLC/参数区当前值。")

        if not args.yes:
            confirm = await asyncio.to_thread(input, "确认触发关节零位标定？输入 YES 继续: ")
            if confirm.strip() != "YES":
                print("已取消。")
                return

        print("\n触发 Calibrate_Joint_Position...")
        rc.RobotCalibrateJointPosition_sync()

        end_time = asyncio.get_running_loop().time() + args.wait
        while asyncio.get_running_loop().time() < end_time:
            await asyncio.sleep(args.interval)
            print_status(rc, "标定后状态")
            if rc.robot_status.Error or any(rc.robot_status.JointError or []):
                print("检测到错误，停止等待。")
                break

    finally:
        print("\n正在停止服务（不发送失能）...")
        rc.stop(disable_robot=False)
        print("退出。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="触发 Codesys 关节零位标定。")
    parser.add_argument("--ip", default=DEFAULT_IP, help="PLC/机器人 ModBus TCP IP")
    parser.add_argument("--positions", help="标定关节位置，逗号分隔。默认不写入，使用 PLC 当前参数")
    parser.add_argument("--degrees", action="store_true", help="--positions 使用角度输入，脚本自动转弧度")
    parser.add_argument("--enable", action="store_true", help="触发标定前先发送机器人使能")
    parser.add_argument("--enable-wait", type=float, default=2.0, help="使能后等待秒数")
    parser.add_argument("--idle-mode", action="store_true", help="触发前切换到 Idle/Calibration 模式")
    parser.add_argument("--wait", type=float, default=5.0, help="触发后观察状态秒数")
    parser.add_argument("--interval", type=float, default=0.5, help="状态打印间隔秒数")
    parser.add_argument("--yes", action="store_true", help="跳过 YES 确认")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(main_task(args))
    except KeyboardInterrupt:
        print("\n用户中断。")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
