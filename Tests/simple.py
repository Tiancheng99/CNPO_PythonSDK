'''
机器人基本功能使用示例
展示 MoveL、MoveJ、夹爪控制的基本用法
'''

import asyncio
import sys
from time import time
from PythonWorkFlow.Core.RobotCore import RobotCore

ROBOT_CONFIG = {
    "target_ip": "192.168.1.253",  # TODO: 修改为实际机器人IP
}


# ==============================================================================
# 辅助函数
# ==============================================================================

async def wait_for_arrival(core: RobotCore, timeout: float = 60) -> bool:
    """
    等待机器人运动到位
    
    Args:
        core: RobotCore 实例
        timeout: 超时时间（秒）
    
    Returns:
        bool: True-成功到达, False-超时
    """
    start_time = time()
    await asyncio.sleep(0.2)  # 等待运动开始
    
    print("  等待到位", end="", flush=True)
    while True:
        is_moving = core.robot_status.Moving
        
        if not is_moving:
            await asyncio.sleep(0.1)
            if not core.robot_status.Moving:
                print(" ✓")
                return True
        
        if time() - start_time > timeout:
            print(" ✗ 超时")
            return False
        
        print(".", end="", flush=True)
        await asyncio.sleep(0.2)


async def initialize_robot(core: RobotCore) -> bool:
    """初始化机器人"""
    print("\n[1/3] 等待连接...", end=" ", flush=True)
    for _ in range(30):
        if core.connected and core.robot_status.Initialized:
            print("✓")
            break
        await asyncio.sleep(0.1)
    else:
        print("✗")
        return False
    
    print("[2/3] 使能机器人...", end=" ", flush=True)
    core.RobotEnable_sync()  # 使用同步版本
    await asyncio.sleep(1.0)
    print("✓" if core.robot_status.PowerOn else "✗")
    
    print("[3/3] 切换到 MoveJoint 模式...", end=" ", flush=True)
    from PythonWorkFlow.Core.Basic import ControlMode
    core.SetControlMode_sync(ControlMode.MoveJoint)
    await asyncio.sleep(0.5)
    print("✓")
    
    # 额外步骤：等待状态同步
    print("[4/4] 同步机器人状态...", end=" ", flush=True)
    await asyncio.sleep(0.5)  # 给状态读取线程时间更新数据
    print("✓\n")
    
    return True


# ==============================================================================
# 功能演示（moveJ、moveL、夹爪控制、读取关节角度）
# ==============================================================================

async def demo_basic_functions(core: RobotCore):
    """演示基本功能使用方法"""
    
    print("="*60)
    print("  机器人基本功能演示")
    print("="*60)
    
    import math
    
    # ========== 1. MoveJ ==========
    print("\n【1】MoveJ - 关节运动 (位置1)")
    print("-" * 60)
    print("用法: core.MoveJ(joint_angles)")
    print("      await wait_for_arrival(core)")
    print("说明: joint_angles = [J1, J2, J3, J4, J5, J6] (弧度)")
    
    target_j = [0.0, math.radians(-90), math.radians(90), 0.0, 0.0, 0.0]
    print(f"\n执行: core.MoveJ([0, -90°, 90°, 0, 0, 0])")
    input("  按 Enter 开始运动...") 
    
    core.MoveJ(target_j)
    await wait_for_arrival(core)
    
    # 显示当前关节角度
    actual_rad = core.robot_status.JointActualPosition
    if actual_rad:
        actual_deg = [math.degrees(r) for r in actual_rad]
        print(f"  到达位置(度): {[round(v, 2) for v in actual_deg]}")
    
    print("✓ 运动完成")
    await asyncio.sleep(1)
    
    # ========== 2. 获取关节角度 ==========
    print("\n【2】GetJointAngles - 获取关节角度")
    print("-" * 60)
    print("用法: core.GetJointAngles(in_degrees=True/False)")
    print("说明: 获取当前6个关节的角度")
    
    angles_rad = core.GetJointAngles(in_degrees=False)
    angles_deg = core.GetJointAngles(in_degrees=True)
    print(f"\n当前关节角度(弧度): {[round(v, 4) for v in angles_rad]}")
    print(f"当前关节角度(度数): {[round(v, 2) for v in angles_deg]}")
    
    # ========== 3. 获取TCP位姿 ==========
    print("\n【3】GetTcpPose - 获取TCP位姿")
    print("-" * 60)
    print("用法: core.GetTcpPose()")
    print("说明: 获取当前TCP位姿 [X, Y, Z, Roll, Pitch, Yaw]")
    print("      X/Y/Z单位:mm, Roll/Pitch/Yaw单位:弧度")
    
    tcp_pose = core.GetTcpPose()
    print(f"\n当前TCP位姿: {[round(v, 3) for v in tcp_pose]}")
    if tcp_pose:
        print(f"  位置(mm): X={tcp_pose[0]:.2f}, Y={tcp_pose[1]:.2f}, Z={tcp_pose[2]:.2f}")
        print(f"  姿态(rad): Roll={tcp_pose[3]:.4f}, Pitch={tcp_pose[4]:.4f}, Yaw={tcp_pose[5]:.4f}")
    
    # ========== 4. 设置工具坐标 ==========
    print("\n【4】SetTip - 设置工具坐标")
    print("-" * 60)
    print("用法: core.SetTip_sync([X, Y, Z, Rx, Ry, Rz])")
    print("      X/Y/Z单位:mm, Rx/Ry/Rz单位:弧度")
    print("说明: 设置工具中心点相对于法兰的偏移")
    
    tip = [0, 145, 46, 0, 0, 0]
    print(f"\n执行: core.SetTip_sync({tip})")
    core.SetTip_sync(tip)
    await asyncio.sleep(0.5)
    print("✓ 工具坐标已设置")
    
    # ========== 5. 大夹爪控制 ==========
    print("\n【5】SetGrip1 - 大夹爪控制")
    print("-" * 60)
    print("用法: core.SetGrip1_sync(state)")
    print("说明: state = 0 (松开) | 1 (保持) | 2 (夹紧)")
    
    print("\n执行: core.SetGrip1_sync(0)  # 松开")
    core.SetGrip1_sync(0)
    await asyncio.sleep(0.5)
    print("✓ 大夹爪已松开")
    
    await asyncio.sleep(1)
    
    print("\n执行: core.SetGrip1_sync(2)  # 夹紧")
    core.SetGrip1_sync(2)
    await asyncio.sleep(0.5)
    print("✓ 大夹爪已夹紧")
    
    # ========== 6. 小夹爪控制 ==========
    print("\n【6】SetGrip2 - 小夹爪控制")
    print("-" * 60)
    print("用法: core.SetGrip2_sync(state)")
    print("说明: state = 0 (松开) | 1 (保持) | 2 (夹紧)")
    
    print("\n执行: core.SetGrip2_sync(0)  # 松开")
    core.SetGrip2_sync(0)
    await asyncio.sleep(0.5)
    print("✓ 小夹爪已松开")
    
    await asyncio.sleep(1)
    
    print("\n执行: core.SetGrip2_sync(2)  # 夹紧")
    core.SetGrip2_sync(2)
    await asyncio.sleep(0.5)
    print("✓ 小夹爪已夹紧")
    
    # ========== 7. MoveL 演示==========
    print("\n【7】MoveL - 笛卡尔直线运动")
    print("-" * 60)
    print("用法: core.MoveL(pose)")
    print("      await wait_for_arrival(core)")
    print("说明: pose = [X, Y, Z, Roll, Pitch, Yaw]")
    print("      X/Y/Z单位:mm, Roll/Pitch/Yaw单位:弧度")
    print("\n注意: 需要先切换到 MoveLinear 模式且机器人已使能")
    
    # 确保机器人已使能
    if not core.robot_status.PowerOn:
        print("使能机器人...")
        core.RobotEnable_sync()
        await asyncio.sleep(0.5)
    
    print("切换到 MoveLinear 模式...")
    core.activateMoveLinear_sync()
    await asyncio.sleep(0.5)
    
    target_l = [-280, -190.388, 327.169, 1.57, 0, 0.00]
    print(f"\n执行: core.MoveL({target_l})")
    print(f"运动前 - Moving: {core.robot_status.Moving}, TCP: {core.GetTCPPose()}")
    input("  按 Enter 开始运动...")
    
    core.MoveL(target_l)
    await asyncio.sleep(0.3)  # 给运动指令时间生效
    print(f"运动后立即 - Moving: {core.robot_status.Moving}")
    
    await wait_for_arrival(core, timeout=30)
    print("✓ 运动完成")
    
    # 读取实际TCP位置验证
    await asyncio.sleep(0.3)
    actual_pose = core.GetTCPPose()
    print(f"\n目标位置: {target_l}")
    print(f"实际位置: {[f'{v:.2f}' for v in actual_pose]}")
    
    # 计算误差
    errors = [abs(a - t) for a, t in zip(actual_pose, target_l)]
    dist_error = (sum(e**2 for e in errors[:3]) ** 0.5)
    print(f"距离误差: {dist_error:.2f}mm")
    
    if dist_error < 10:
        print("✓ 运动成功")
    else:
        print(f"⚠️  误差较大")


# ==============================================================================
# 主函数
# ==============================================================================

async def main_task(core: RobotCore):
    """主任务"""
    if not core.connected:
        print("错误：无法连接到机器人，请检查IP配置")
        return
    
    if not await initialize_robot(core):
        print("错误：机器人初始化失败")
        return
    
    # 演示基本功能
    await demo_basic_functions(core)


def main():
    """程序入口"""

    # ============ 首先先初始化RobotCore（固定写法） ==============
    print("\n初始化中...\n")
    
    try:
        core = RobotCore(target_ip=ROBOT_CONFIG["target_ip"])
    except Exception as e:
        print(f"RobotCore 初始化失败: {e}")
        return
    

    # ============ 运行自定义任务 ==============
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        asyncio.run(main_task(core))



    # ============ 清理退出（固定写法） ==============
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n正在停止服务...")
        core.stop()
        print("已退出\n")


if __name__ == '__main__':
    main()
