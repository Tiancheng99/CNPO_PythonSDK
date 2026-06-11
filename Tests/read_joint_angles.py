'''
只读取当前关节角度，不下发使能、模式切换或运动指令。
适配版本：RobotCoreV2
'''

import argparse
import asyncio
import math
import sys
from typing import List

from PythonWorkFlow.Core.RobotCore import RobotCore
from PythonWorkFlow.Core.Basic import ControlMode


CODESYS_CONFIG = {
    "target_ip": "192.168.1.253",  # TODO: 修改为实际 PLC IP
    "port": 502,
    "unit_id": 1,
}


def format_values(values: List[float], digits: int = 3) -> str:
    return "[" + ", ".join(f"{v:.{digits}f}" for v in values) + "]"


def radians_to_degrees(values: List[float]) -> List[float]:
    return [math.degrees(v) for v in values]


async def wait_for_connection(rc: RobotCore, timeout: float = 10.0) -> bool:
    print("等待 ModBus 连接和状态读取线程启动...", end="", flush=True)
    loops = max(1, int(timeout / 0.1))
    for _ in range(loops):
        if rc.connected and rc.init_complete:
            print("完成")
            return True
        print(".", end="", flush=True)
        await asyncio.sleep(0.1)
    print("超时")
    return False


def print_joint_status(rc: RobotCore) -> None:
    status = rc.robot_status
    joint_rad = list(status.JointActualPosition or [])
    joint_vel = list(status.JointActualVelocity or [])
    joint_current = list(status.JointActualCurrent or [])
    joint_torque = list(status.JointActualTorque or [])
    joint_state = list(status.JointState or [])
    joint_error = list(status.JointError or [])
    joint_error_id = list(status.JointErrorId or [])

    if len(joint_rad) < rc.joint_count:
        joint_rad.extend([0.0] * (rc.joint_count - len(joint_rad)))
    if len(joint_vel) < rc.joint_count:
        joint_vel.extend([0.0] * (rc.joint_count - len(joint_vel)))
    if len(joint_current) < rc.joint_count:
        joint_current.extend([0.0] * (rc.joint_count - len(joint_current)))
    if len(joint_torque) < rc.joint_count:
        joint_torque.extend([0.0] * (rc.joint_count - len(joint_torque)))
    if len(joint_state) < rc.joint_count:
        joint_state.extend([0] * (rc.joint_count - len(joint_state)))
    if len(joint_error) < rc.joint_count:
        joint_error.extend([False] * (rc.joint_count - len(joint_error)))
    if len(joint_error_id) < rc.joint_count:
        joint_error_id.extend([0] * (rc.joint_count - len(joint_error_id)))

    joint_rad = joint_rad[:rc.joint_count]
    joint_vel = joint_vel[:rc.joint_count]
    joint_current = joint_current[:rc.joint_count]
    joint_torque = joint_torque[:rc.joint_count]
    joint_state = joint_state[:rc.joint_count]
    joint_error = joint_error[:rc.joint_count]
    joint_error_id = joint_error_id[:rc.joint_count]
    joint_deg = radians_to_degrees(joint_rad)

    print("-" * 72)
    print(f"connected={rc.connected} init_complete={rc.init_complete} joint_count={rc.joint_count}")
    print(f"PowerOn={status.PowerOn} Moving={status.Moving} Error={status.Error} ErrorId={status.ErrorId}")
    print(f"ActualMovementMode={status.ActualMovementMode}")
    print(f"关节状态码: {joint_state}")
    print(f"关节错误标志: {joint_error}")
    print(f"关节错误码: {joint_error_id}")
    print(f"关节角度(rad): {format_values(joint_rad, 6)}")
    print(f"关节角度(deg): {format_values(joint_deg, 3)}")
    print(f"关节速度(rad/s): {format_values(joint_vel, 6)}")
    print(f"关节电流: {format_values(joint_current, 6)}")
    print(f"关节扭矩: {format_values(joint_torque, 6)}")


async def main_task(rc: RobotCore, interval: float, once: bool, enable: bool, movejoint: bool) -> None:
    if not await wait_for_connection(rc):
        print("错误：无法连接到机器人，请检查 IP、网线、PLC ModBus 服务和地址簿配置。")
        return

    if enable:
        print("发送机器人使能指令...")
        rc.RobotEnable_sync()
        await asyncio.sleep(2.0)

    if movejoint:
        print("切换到 MoveJoint 模式...")
        rc.SetControlMode_sync(ControlMode.MoveJoint)
        await asyncio.sleep(1.0)

    # 给后台轮询一次状态刷新的时间。
    await asyncio.sleep(0.5)

    while True:
        print_joint_status(rc)
        if once:
            return
        await asyncio.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读取机器人当前关节角度，不执行运动。")
    parser.add_argument("--ip", default=CODESYS_CONFIG["target_ip"], help="PLC/机器人 ModBus TCP IP")
    parser.add_argument("--interval", type=float, default=1.0, help="循环读取间隔，单位秒")
    parser.add_argument("--once", action="store_true", help="只读取并打印一次")
    parser.add_argument("--enable", action="store_true", help="读取前先发送机器人使能指令")
    parser.add_argument("--movejoint", action="store_true", help="读取前切换到 MoveJoint 模式")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("正在初始化 RobotCore（只读模式，不自动使能/写参数/切模式）...")
    try:
        rc = RobotCore(target_ip=args.ip, auto_initialize_robot=False)
    except Exception as e:
        print(f"RobotCore 初始化失败: {e}")
        return

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(main_task(rc, args.interval, args.once, args.enable, args.movejoint))
    except KeyboardInterrupt:
        print("\n用户中断读取。")
    finally:
        print("正在停止服务...")
        rc.stop(disable_robot=False)
        print("退出。")


if __name__ == "__main__":
    main()
