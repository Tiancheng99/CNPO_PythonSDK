'''
测试用例：MoveJ 关节运动（基于 CSV 文件的手动步进执行）
适配版本：RobotCoreV2
'''

import asyncio
import csv
import math
import os
import sys
from time import time
from typing import Dict, List

from PythonWorkFlow.Core.RobotCore import RobotCore
from PythonWorkFlow.Core.Basic import ControlMode 


# ==============================================================================
# 配置区域
# ==============================================================================
CODESYS_CONFIG = {
    "target_ip": "192.168.1.253", # TODO: 修改为实际 PLC IP
    # "target_ip": "192.168.0.155",
    "port": 502,
    "unit_id": 1
}

CSV_FILE_PATH = "Tests/output.csv"

# ==============================================================================
# 辅助函数
# ==============================================================================

def deg_to_rad(degrees: List[float]) -> List[float]:
    """角度转弧度"""
    return [math.radians(d) for d in degrees]

async def wait_for_user_input(prompt: str = "按 Enter 键继续...") -> None:
    """异步等待用户输入（防止阻塞事件循环）"""
    print(f"\n{'-'*30}\n{prompt}\n{'-'*30}")
    await asyncio.to_thread(input, "")

def load_csv_data(file_path: str, joint_count: int) -> List[Dict]:
    """
    读取 CSV 文件并解析关节角度数据。
    CSV 格式要求: ID,J1,...,Jn,Info
    """
    commands = []
    min_columns = joint_count + 1
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        return []

    try:
        with open(file_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                print("错误: CSV 文件为空")
                return []

            if len(header) < min_columns:
                print(f"错误: CSV表头列数不足，期望至少 {min_columns} 列，实际 {len(header)} 列")
                return []

            for row in reader:
                if len(row) < min_columns:
                    print(f"跳过列数不足的数据行: {row}")
                    continue
                try:
                    joint_angles_deg = [float(angle) for angle in row[1:1 + joint_count]]
                    commands.append({
                        "id": row[0],
                        "joint_angles_deg": joint_angles_deg,
                        "location": row[1 + joint_count] if len(row) > 1 + joint_count else f"ID {row[0]}"
                    })
                except ValueError:
                    print(f"跳过无效数据行: {row}")
    except Exception as e:
        print(f"读取CSV文件错误: {e}")
        raise

    return commands

# ==============================================================================
# 测试任务
# ==============================================================================

async def check_initialization(rc: RobotCore):
    """检查初始化状态"""
    print("\n[1/4] 检查初始化状态...")

    # 等待 SDK 完整初始化（含 RobotEnable），最多 10 秒
    for _ in range(100):
        if rc.connected and rc.init_complete:
            break
        await asyncio.sleep(0.1)

    if not rc.init_complete:
        raise RuntimeError("SDK 初始化超时，请检查网络连接")

    if not rc.robot_status.PowerOn:
        raise RuntimeError("机器人未上电 (PowerOn=False)，请检查急停按钮或安全联锁！")

    print("状态检查: 机器人已上电")

async def test_robot_enable(rc: RobotCore):
    """测试使能"""
    print("\n[2/4] 执行 RobotEnable...")
    rc.RobotEnable_sync()
    await asyncio.sleep(2.0)

    if rc.robot_status.PowerOn:
        print("机器人使能成功！")
    else:
        raise RuntimeError("使能失败：指令已发送，但 PowerOn 仍为 False，请检查驱动器状态或错误码")

async def test_set_mode(rc: RobotCore):
    """设置 MoveJoint 模式"""
    print("\n[3/4] 设置控制模式为 MoveJoint...")
    rc.SetControlMode_sync(ControlMode.MoveJoint)  # 使用 _sync 版本
    await asyncio.sleep(0.5)

async def test_csv_trajectory(rc: RobotCore, csv_path: str):
    """执行 CSV 轨迹"""
    print(f"\n[4/4] 加载并执行轨迹: {csv_path}")

    commands = load_csv_data(csv_path, rc.joint_count)
    if not commands:
        print("未加载到有效指令，测试结束。")
        return

    print(f"共加载 {len(commands)} 个点位，每个点位 {rc.joint_count} 个关节。")

    for idx, cmd in enumerate(commands, 1):
        loc_name = cmd["location"]
        deg_vals = cmd["joint_angles_deg"]
        rad_vals = deg_to_rad(deg_vals)

        print(f"\n--- 步骤 {idx}/{len(commands)}: {loc_name} ---")
        print(f"目标(deg): {[round(v, 2) for v in deg_vals]}")

        await wait_for_user_input(f">>> 按 Enter 执行 MoveJ -> {loc_name}")

        print("发送 MoveJ 指令...")
        rc.MoveJ(rad_vals)

        await asyncio.sleep(0.2)

        print("等待机器人运动到位...", end="", flush=True)
        start_wait = time()
        while True:
            if not rc.robot_status.Moving:
                await asyncio.sleep(0.1)
                if not rc.robot_status.Moving:
                    break

            if time() - start_wait > 60:
                print("\n错误：运动等待超时！")
                break

            print(".", end="", flush=True)
            await asyncio.sleep(0.2)

        print("\n到位。")
        actual_rad = rc.robot_status.JointActualPosition
        actual_deg = [math.degrees(r) for r in actual_rad]
        print(f"当前(deg): {[round(v, 2) for v in actual_deg]}")

# ==============================================================================
# 主入口
# ==============================================================================

async def main_task(rc: RobotCore):
    """异步主任务"""
    # 1. 检查连接
    if not rc.connected:
        print("错误：无法连接到机器人，请检查 IP 配置。")
        return

    # 2. 执行测试流程
    try:
        await check_initialization(rc)
        await test_robot_enable(rc)
        await test_set_mode(rc)
        await test_csv_trajectory(rc, CSV_FILE_PATH)
        
    except Exception as e:
        print(f"\n测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("正在初始化 RobotCore...")
    # 初始化 Core (会自动启动后台线程连接 PLC)
    try:
        rc = RobotCore(target_ip=CODESYS_CONFIG["target_ip"])
    except Exception as e:
        print(f"RobotCore 初始化失败: {e}")
        return

    # 运行异步测试主循环
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
        asyncio.run(main_task(rc))
        
    except KeyboardInterrupt:
        print("\n用户中断测试。")
    finally:
        print("正在停止服务...")
        rc.stop()
        print("退出。")

if __name__ == '__main__':
    main()
