"""Tkinter upper-computer app for Robot SDK V2."""

from __future__ import annotations

import csv
import faulthandler
import gc
import json
import math
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional



def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def setup_runtime_logging() -> Optional[Path]:
    log_path = runtime_base_dir() / "RobotSDKV2_GUI.log"
    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        log_file.write(f"\n===== RobotSDKV2_GUI start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        try:
            faulthandler.enable(file=log_file)
        except Exception:
            pass
        if getattr(sys, "frozen", False) or sys.stdout is None:
            sys.stdout = log_file
        if getattr(sys, "frozen", False) or sys.stderr is None:
            sys.stderr = log_file
    except Exception:
        return None

    def log_exception(exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

    sys.excepthook = log_exception
    if hasattr(threading, "excepthook"):
        def log_thread_exception(args) -> None:
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=sys.stderr)

        threading.excepthook = log_thread_exception
    return log_path


RUNTIME_LOG_PATH = setup_runtime_logging()

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PythonWorkFlow.Core.Basic import ControlMode
from PythonWorkFlow.Core.RobotCore import RobotCore


DEFAULT_IP = "192.168.1.253"


@dataclass
class StartupSelection:
    ip: str
    joint_count: int


@dataclass
class CsvPoint:
    point_id: str
    joints_deg: List[float]
    info: str


def app_base_dir() -> Path:
    """Return the editable runtime directory next to the exe or source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path: str) -> str:
    """Prefer external runtime files, then fall back to PyInstaller bundled files."""
    external = app_base_dir() / relative_path
    if external.exists():
        return str(external)

    bundled_base = getattr(sys, "_MEIPASS", None)
    if bundled_base:
        bundled = Path(bundled_base) / relative_path
        if bundled.exists():
            return str(bundled)

    return str(external)


def resolve_config_reference(config_path: str, configured_path: str) -> str:
    path = Path(configured_path)
    if path.is_absolute():
        return str(path)

    app_base = Path(config_path).resolve().parent.parent
    if path.parts and path.parts[0].lower() == "config":
        return str((app_base / path).resolve())
    return str((app_base / "Config" / path).resolve())


def load_robot_config_paths() -> dict:
    config_path = resource_path("Config/RobotConfig.json")
    result = {"config_path": config_path}
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        arms = data.get("arms", {}) if isinstance(data, dict) else {}
        selected = data.get("default_arm") if isinstance(data, dict) else None
        if not selected and arms:
            selected = next(iter(arms.keys()))
        arm = arms.get(selected, {}) if isinstance(arms, dict) else {}
        if isinstance(arm, dict):
            if arm.get("address_book"):
                result["address_book_path"] = resolve_config_reference(config_path, arm["address_book"])
            if arm.get("parameter_file"):
                result["parameter_json"] = resolve_config_reference(config_path, arm["parameter_file"])
            if arm.get("joint_count") is not None:
                result["joint_count"] = int(arm["joint_count"])
    except Exception:
        pass
    return result


def default_joint_count() -> int:
    try:
        value = load_robot_config_paths().get("joint_count")
        return int(value) if value else 7
    except Exception:
        return 7


def fit(values: List[float], count: int, default: float = 0.0) -> List[float]:
    values = list(values[:count])
    if len(values) < count:
        values.extend([default] * (count - len(values)))
    return values


def format_numbers(values: List[float], digits: int = 3) -> str:
    return ", ".join(f"{v:.{digits}f}" for v in values)


class RobotWorker:
    _gc_lock = threading.Lock()
    _gc_pause_count = 0

    def __init__(self, post: Callable[[str, object], None], log: Callable[[str], None], joint_count: int) -> None:
        self._post = post
        self._log = log
        self._lock = threading.RLock()
        self.robot: Optional[RobotCore] = None
        self.configured_joint_count = joint_count
        self.stop_requested = threading.Event()

    def connected(self) -> bool:
        with self._lock:
            return bool(self.robot and self.robot.connected)

    def joint_count(self) -> int:
        with self._lock:
            return int(self.robot.joint_count) if self.robot else self.configured_joint_count

    def run_async(self, name: str, target: Callable[[], None]) -> None:
        def wrapper() -> None:
            gc_was_enabled = self._pause_gc_for_worker()
            try:
                target()
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                self._log(f"{name} 失败: {exc}")
                self._log(traceback.format_exc())
                self._post("error", str(exc))
            finally:
                self._resume_gc_after_worker(gc_was_enabled)
                self._post("collect_garbage", None)

        threading.Thread(target=wrapper, daemon=True).start()

    @classmethod
    def _pause_gc_for_worker(cls) -> bool:
        with cls._gc_lock:
            was_enabled = gc.isenabled()
            cls._gc_pause_count += 1
            if was_enabled:
                gc.disable()
            return was_enabled

    @classmethod
    def _resume_gc_after_worker(cls, enable_when_done: bool) -> None:
        with cls._gc_lock:
            cls._gc_pause_count = max(0, cls._gc_pause_count - 1)
            if enable_when_done and cls._gc_pause_count == 0:
                gc.enable()

    def connect(self, ip: str, auto_initialize: bool) -> None:
        def task() -> None:
            with self._lock:
                if self.robot:
                    self.robot.stop(disable_robot=False)
                    self.robot = None
            self._log(f"连接机器人 {ip} ...")
            robot_config = load_robot_config_paths()
            robot_config["joint_count"] = self.configured_joint_count
            robot = RobotCore(
                target_ip=ip,
                auto_initialize_robot=auto_initialize,
                **robot_config,
            )
            with self._lock:
                self.robot = robot
            if robot.connected:
                self._log(f"连接成功，关节数: {robot.joint_count}")
                self._post("connected", robot.joint_count)
            else:
                self._log("连接失败，请检查 IP、网线、PLC ModBus 服务和防火墙。")
                self._post("disconnected", None)

        self.run_async("连接", task)

    def disconnect(self, disable_robot: bool = False) -> None:
        def task() -> None:
            with self._lock:
                robot = self.robot
                self.robot = None
            if robot:
                self._log("断开连接 ...")
                robot.stop(disable_robot=disable_robot)
            self._post("disconnected", None)
            self._log("已断开")

        self.run_async("断开", task)

    def enable_and_movejoint(self) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._log("发送使能指令 ...")
            robot.RobotEnable_sync()
            time.sleep(0.8)
            self._log("切换 MoveJoint 模式 ...")
            robot.SetControlMode_sync(ControlMode.MoveJoint)
            self._log("已请求 MoveJoint 模式")

        self.run_async("使能/切模式", task)

    def stop_motion(self) -> None:
        self.stop_requested.set()

        def task() -> None:
            robot = self._require_robot()
            self._log("发送停止指令 ...")
            robot.RobotStop_sync()
            self._log("停止指令已发送")

        self.run_async("停止", task)

    def disable_robot(self) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._log("发送去使能指令...")
            robot.RobotDisable_sync()
            self._log("去使能指令已发送")

        self.run_async("去使能", task)

    def reset_robot(self) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._log("发送复位指令...")
            robot.RobotReset_sync()
            self._log("复位指令已发送")

        self.run_async("复位", task)

    def calibrate_joint_zero(self, joint_positions_rad: List[float]) -> None:
        def task() -> None:
            robot = self._require_robot()
            target = fit(joint_positions_rad, robot.joint_count)
            self._log(f"写入标定零位(rad): [{format_numbers(target, 6)}]")
            robot.SetControlMode_sync(ControlMode.Calibration)
            time.sleep(0.3)
            robot.RobotSetCalibrationJointPositions_sync(target)
            time.sleep(0.3)
            robot.RobotCalibrateJointPosition_sync()
            self._log("标定零位指令已发送")

        self.run_async("标定零位", task)

    def movej_rad(self, joints_rad: List[float]) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._require_power_on(robot)
            joints_rad_fit = fit(joints_rad, robot.joint_count)
            self.stop_requested.clear()
            self._log(f"MoveJ 目标(rad): [{format_numbers(joints_rad_fit, 6)}]")
            robot.SetControlMode_sync(ControlMode.MoveJoint)
            robot.MoveJ(joints_rad_fit)
            self._wait_until_done(timeout=60.0)
            self._log("MoveJ 完成")

        self.run_async("MoveJ", task)

    def movej_deg(self, joints_deg: List[float]) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._require_power_on(robot)
            joints_deg_fit = fit(joints_deg, robot.joint_count)
            self.stop_requested.clear()
            self._log(f"MoveJ 目标(deg): [{format_numbers(joints_deg_fit)}]")
            robot.SetControlMode_sync(ControlMode.MoveJoint)
            robot.MoveJ([math.radians(v) for v in joints_deg_fit])
            self._wait_until_done(timeout=60.0)
            self._log("MoveJ 完成")

        self.run_async("MoveJ", task)

    def execute_point(self, point: CsvPoint, index: int, total: int, dwell: float, wait_done: bool) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._require_power_on(robot)
            self.stop_requested.clear()
            robot.SetControlMode_sync(ControlMode.MoveJoint)
            target_deg = fit(point.joints_deg, robot.joint_count)
            self._post("trajectory_index", index)
            self._log(f"[{index + 1}/{total}] {point.info or point.point_id}: [{format_numbers(target_deg)}]")
            robot.MoveJ([math.radians(v) for v in target_deg])
            if wait_done:
                self._wait_until_done(timeout=60.0)
            if dwell > 0:
                time.sleep(dwell)
            self._log("CSV 单步执行完成")

        self.run_async("CSV 单步执行", task)

    def execute_points(self, points: List[CsvPoint], dwell: float, wait_done: bool) -> None:
        def task() -> None:
            robot = self._require_robot()
            self._require_power_on(robot)
            if not points:
                self._log("没有可执行的 CSV 点位")
                return
            self.stop_requested.clear()
            robot.SetControlMode_sync(ControlMode.MoveJoint)
            self._log(f"开始执行 CSV，共 {len(points)} 个点位")
            for index, point in enumerate(points, 1):
                if self.stop_requested.is_set():
                    self._log("轨迹执行已被停止")
                    break
                target_deg = fit(point.joints_deg, robot.joint_count)
                self._post("trajectory_index", index - 1)
                self._log(f"[{index}/{len(points)}] {point.info or point.point_id}: [{format_numbers(target_deg)}]")
                robot.MoveJ([math.radians(v) for v in target_deg])
                if wait_done:
                    self._wait_until_done(timeout=60.0)
                if dwell > 0:
                    time.sleep(dwell)
            self._post("trajectory_index", -1)
            self._log("CSV 执行结束")

        self.run_async("CSV 执行", task)

    def snapshot(self) -> Optional[dict]:
        with self._lock:
            robot = self.robot
        if not robot:
            return None
        status = robot.robot_status
        count = robot.joint_count
        joint_rad = fit(list(status.JointActualPosition or []), count)
        joint_deg = [math.degrees(v) for v in joint_rad]
        return {
            "connected": robot.connected,
            "init_complete": robot.init_complete,
            "joint_count": count,
            "power_on": bool(status.PowerOn),
            "moving": bool(status.Moving),
            "error": bool(status.Error),
            "error_id": status.ErrorId,
            "mode": status.ActualMovementMode,
            "joint_deg": joint_deg,
            "joint_rad": joint_rad,
            "joint_vel": fit(list(status.JointActualVelocity or []), count),
            "joint_current": fit(list(status.JointActualCurrent or []), count),
        }

    def _require_robot(self) -> RobotCore:
        with self._lock:
            robot = self.robot
        if not robot or not robot.connected:
            raise RuntimeError("机器人未连接")
        return robot

    def _require_power_on(self, robot: RobotCore) -> None:
        if not bool(robot.robot_status.PowerOn):
            self._log("未检测到上使能，已取消 MoveJ。请先点击“使能 + MoveJoint”。")
            raise RuntimeError("未检测到上使能，请先点击“使能 + MoveJoint”后再执行 MoveJ。")

    def _wait_until_done(self, timeout: float) -> None:
        robot = self._require_robot()
        start = time.monotonic()
        seen_moving = False
        while True:
            elapsed = time.monotonic() - start
            if self.stop_requested.is_set():
                try:
                    robot.RobotStop_sync()
                finally:
                    raise RuntimeError("执行已停止")
            moving = bool(robot.robot_status.Moving)
            seen_moving = seen_moving or moving
            if not seen_moving and not moving and elapsed > 0.8:
                return
            if seen_moving and not moving:
                time.sleep(0.15)
                if not robot.robot_status.Moving:
                    return
            if elapsed > timeout:
                raise TimeoutError("等待机器人运动完成超时")
            time.sleep(0.1)


class RobotApp(tk.Tk):
    def __init__(self, startup: StartupSelection) -> None:
        super().__init__()
        self.title("Robot SDK V2 上位机")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.startup = startup

        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.worker = RobotWorker(self._post, self._log_from_thread, startup.joint_count)
        self.csv_points: List[CsvPoint] = []
        self.csv_next_index = 0
        self.csv_running = False
        self.joint_vars: List[tk.StringVar] = []
        self.manual_unit_var = tk.StringVar(value="deg")
        self.calibration_deg_var = tk.StringVar(value="")
        self.status_vars = {
            "connected": tk.StringVar(value="未连接"),
            "power": tk.StringVar(value="-"),
            "moving": tk.StringVar(value="-"),
            "mode": tk.StringVar(value="-"),
            "error": tk.StringVar(value="-"),
        }

        self._build_ui()
        self._rebuild_joint_inputs(startup.joint_count)
        self.after(100, self._process_events)
        self.after(500, self._refresh_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Return>", self._enter_execute)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(root)
        top.pack(fill=tk.X)
        ttk.Label(top, text="IP").pack(side=tk.LEFT)
        self.ip_var = tk.StringVar(value=self.startup.ip)
        ttk.Entry(top, textvariable=self.ip_var, width=18).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(top, text=f"轴数: {self.startup.joint_count}").pack(side=tk.LEFT, padx=(0, 12))
        self.auto_init_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="连接时自动初始化", variable=self.auto_init_var).pack(side=tk.LEFT)
        ttk.Button(top, text="连接", command=self._connect).pack(side=tk.LEFT, padx=(12, 4))
        ttk.Button(top, text="断开", command=self._disconnect).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="使能 + MoveJoint", command=self.worker.enable_and_movejoint).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="去使能", command=self.worker.disable_robot).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="复位", command=self.worker.reset_robot).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="停止", command=self.worker.stop_motion).pack(side=tk.LEFT, padx=4)

        status = ttk.LabelFrame(root, text="状态", padding=10)
        status.pack(fill=tk.X, pady=(12, 8))
        for label, key in [
            ("连接", "connected"),
            ("PowerOn", "power"),
            ("Moving", "moving"),
            ("Mode", "mode"),
            ("Error", "error"),
        ]:
            ttk.Label(status, text=label).pack(side=tk.LEFT)
            ttk.Label(status, textvariable=self.status_vars[key], width=16).pack(side=tk.LEFT, padx=(4, 18))

        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(left, weight=1)
        paned.add(right, weight=1)

        current = ttk.LabelFrame(left, text="当前关节状态", padding=10)
        current.pack(fill=tk.X)
        self.joint_status_text = tk.Text(current, height=10, wrap=tk.NONE)
        self.joint_status_text.pack(fill=tk.X)
        self.joint_status_text.configure(state=tk.DISABLED)

        manual = ttk.LabelFrame(left, text="点对点 MoveJ", padding=10)
        manual.pack(fill=tk.X, pady=(10, 0))
        self.joint_input_frame = ttk.Frame(manual)
        self.joint_input_frame.pack(fill=tk.X)
        manual_buttons = ttk.Frame(manual)
        manual_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Radiobutton(manual_buttons, text="角度", variable=self.manual_unit_var, value="deg", command=self._fill_current_joints).pack(side=tk.LEFT)
        ttk.Radiobutton(manual_buttons, text="弧度", variable=self.manual_unit_var, value="rad", command=self._fill_current_joints).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(manual_buttons, text="填入当前关节", command=self._fill_current_joints).pack(side=tk.LEFT)
        ttk.Button(manual_buttons, text="执行 MoveJ", command=self._manual_movej).pack(side=tk.LEFT, padx=8)

        ttk.Button(manual_buttons, text="标定零位", command=self._calibrate_joint_zero).pack(side=tk.LEFT, padx=4)

        calibration_box = ttk.Frame(manual)
        calibration_box.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(calibration_box, text="标定角度").pack(side=tk.LEFT)
        ttk.Entry(calibration_box, textvariable=self.calibration_deg_var, width=48).pack(side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        ttk.Button(calibration_box, text="填入当前角度", command=self._fill_calibration_from_current).pack(side=tk.LEFT)

        csv_box = ttk.LabelFrame(right, text="CSV 点位队列", padding=10)
        csv_box.pack(fill=tk.BOTH, expand=True)

        csv_controls = ttk.Frame(csv_box)
        csv_controls.pack(fill=tk.X)
        ttk.Button(csv_controls, text="下一点(Enter)", command=self._execute_next_csv_point).pack(side=tk.LEFT)
        ttk.Button(csv_controls, text="加载 CSV", command=self._load_csv).pack(side=tk.LEFT)
        ttk.Label(csv_controls, text="停留(s)").pack(side=tk.LEFT, padx=(14, 4))
        self.dwell_var = tk.StringVar(value="0.2")
        ttk.Entry(csv_controls, textvariable=self.dwell_var, width=8).pack(side=tk.LEFT)
        self.wait_done_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(csv_controls, text="等待到位", variable=self.wait_done_var).pack(side=tk.LEFT, padx=12)
        ttk.Button(csv_controls, text="按顺序执行", command=self._execute_csv).pack(side=tk.LEFT, padx=4)

        columns = ("id", "joints", "info")
        self.csv_tree = ttk.Treeview(csv_box, columns=columns, show="headings", height=14)
        self.csv_tree.heading("id", text="ID")
        self.csv_tree.heading("joints", text="Joints(deg)")
        self.csv_tree.heading("info", text="Info")
        self.csv_tree.column("id", width=70, anchor=tk.CENTER)
        self.csv_tree.column("joints", width=360)
        self.csv_tree.column("info", width=120)
        self.csv_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        log_box = ttk.LabelFrame(root, text="日志", padding=10)
        log_box.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.log_text = tk.Text(log_box, height=9, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _rebuild_joint_inputs(self, count: int) -> None:
        for child in self.joint_input_frame.winfo_children():
            child.destroy()
        self.joint_vars = []
        for index in range(count):
            box = ttk.Frame(self.joint_input_frame)
            box.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
            ttk.Label(box, text=f"J{index + 1}").pack(side=tk.LEFT)
            var = tk.StringVar(value="0.000")
            ttk.Entry(box, textvariable=var, width=12).pack(side=tk.LEFT, padx=(4, 0))
            self.joint_vars.append(var)

    def _connect(self) -> None:
        self.worker.connect(self.ip_var.get().strip(), self.auto_init_var.get())

    def _disconnect(self) -> None:
        self.worker.disconnect(disable_robot=False)

    def _manual_values_rad(self) -> List[float]:
        values = [float(var.get()) for var in self.joint_vars]
        if self.manual_unit_var.get() == "rad":
            return values
        return [math.radians(v) for v in values]

    def _calibration_values_rad(self) -> List[float]:
        raw = self.calibration_deg_var.get().strip()
        if not raw:
            raise ValueError("请输入标定关节角度")
        parts = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
        count = self.worker.joint_count()
        if len(parts) != count:
            raise ValueError(f"需要输入 {count} 个关节角度，当前输入 {len(parts)} 个")
        return [math.radians(float(part)) for part in parts]

    def _manual_movej(self) -> None:
        try:
            joints_rad = self._manual_values_rad()
        except ValueError:
            messagebox.showerror("输入错误", "关节目标必须是数字，单位为度。")
            return
        self.worker.movej_rad(joints_rad)

    def _calibrate_joint_zero(self) -> None:
        try:
            joints_rad = self._calibration_values_rad()
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc))
            return
        if not messagebox.askyesno("确认标定零位", "将使用输入的关节角度写入 CalibrationJointPositions，并触发标定零位。是否继续？"):
            return
        self.worker.calibrate_joint_zero(joints_rad)

    def _fill_calibration_from_current(self) -> None:
        snap = self.worker.snapshot()
        if not snap:
            return
        self.calibration_deg_var.set(", ".join(f"{value:.3f}" for value in snap["joint_deg"]))

    def _fill_current_joints(self) -> None:
        snap = self.worker.snapshot()
        if not snap:
            return
        values = snap["joint_rad"] if self.manual_unit_var.get() == "rad" else snap["joint_deg"]
        if len(values) != len(self.joint_vars):
            self._rebuild_joint_inputs(len(values))
        for var, value in zip(self.joint_vars, values):
            var.set(f"{value:.3f}")

    def _load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 CSV 点位文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            points = self._read_csv_points(path)
        except Exception as exc:
            messagebox.showerror("CSV 读取失败", str(exc))
            return
        self.csv_points = points
        self.csv_next_index = 0
        self.csv_tree.delete(*self.csv_tree.get_children())
        for point in points:
            self.csv_tree.insert(
                "",
                tk.END,
                values=(point.point_id, format_numbers(point.joints_deg), point.info),
            )
        self._log(f"已加载 CSV: {path}，点位数: {len(points)}")

    def _read_csv_points(self, path: str) -> List[CsvPoint]:
        count = self.worker.joint_count()
        points: List[CsvPoint] = []
        with open(path, "r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                raise ValueError("CSV 文件为空")
            joint_columns = [i for i, name in enumerate(header) if name.strip().upper().startswith("J")]
            if not joint_columns:
                joint_columns = list(range(1, min(len(header), count + 1)))
            joint_columns = joint_columns[:count]
            if len(joint_columns) < count:
                raise ValueError(f"CSV 关节列不足，当前机器人需要 {count} 个关节列")
            info_index = next((i for i, name in enumerate(header) if name.strip().lower() == "info"), None)
            for row_num, row in enumerate(reader, start=2):
                if not row or all(not cell.strip() for cell in row):
                    continue
                try:
                    joints = [float(row[i]) for i in joint_columns]
                except (IndexError, ValueError) as exc:
                    raise ValueError(f"第 {row_num} 行关节数据无效: {row}") from exc
                point_id = row[0] if row else str(row_num)
                info = row[info_index] if info_index is not None and info_index < len(row) else point_id
                points.append(CsvPoint(point_id=point_id, joints_deg=joints, info=info))
        return points

    def _execute_csv(self) -> None:
        if self.csv_running:
            self._log("CSV 正在执行，忽略重复执行请求")
            return
        if not self.csv_points:
            self._log("没有可执行的 CSV 点位")
            return
        try:
            dwell = float(self.dwell_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "停留时间必须是数字。")
            return
        self.csv_running = True
        self.worker.execute_points(self.csv_points, dwell=max(0.0, dwell), wait_done=self.wait_done_var.get())

    def _execute_next_csv_point(self) -> None:
        if self.csv_running:
            self._log("CSV 正在按顺序执行，Enter 单步已忽略")
            return
        if not self.csv_points:
            self._manual_movej()
            return
        try:
            dwell = float(self.dwell_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "停留时间必须是数字。")
            return
        selected = self.csv_tree.selection()
        children = list(self.csv_tree.get_children())
        selected_index = None
        if selected and selected[0] in children:
            selected_index = children.index(selected[0])
        if selected_index is not None and selected_index != max(self.csv_next_index - 1, 0):
            index = selected_index
        else:
            index = self.csv_next_index
        if index >= len(self.csv_points):
            self._log("CSV 已执行到末尾，下一次将从第 1 点开始")
            self.csv_next_index = 0
            return
        self.csv_next_index = index + 1
        self.worker.execute_point(
            self.csv_points[index],
            index=index,
            total=len(self.csv_points),
            dwell=max(0.0, dwell),
            wait_done=self.wait_done_var.get(),
        )

    def _enter_execute(self, _event: object) -> str:
        self._execute_next_csv_point()
        return "break"

    def _refresh_status(self) -> None:
        snap = self.worker.snapshot()
        if snap:
            self.status_vars["connected"].set("已连接" if snap["connected"] else "未连接")
            self.status_vars["power"].set(str(snap["power_on"]))
            self.status_vars["moving"].set(str(snap["moving"]))
            self.status_vars["mode"].set(str(snap["mode"]))
            self.status_vars["error"].set(f"{snap['error']} / {snap['error_id']}")
            lines = [
                f"joint_count={snap['joint_count']} init_complete={snap['init_complete']}",
                f"关节角度(deg): [{format_numbers(snap['joint_deg'], 3)}]",
                f"关节角度(rad): [{format_numbers(snap['joint_rad'], 6)}]",
                f"关节速度(rad/s): [{format_numbers(snap['joint_vel'], 6)}]",
                f"关节电流: [{format_numbers(snap['joint_current'], 6)}]",
            ]
            self._set_status_text("\n".join(lines))
            if len(self.joint_vars) != snap["joint_count"]:
                self._rebuild_joint_inputs(snap["joint_count"])
        else:
            self.status_vars["connected"].set("未连接")
        self.after(500, self._refresh_status)

    def _set_status_text(self, text: str) -> None:
        self.joint_status_text.configure(state=tk.NORMAL)
        self.joint_status_text.delete("1.0", tk.END)
        self.joint_status_text.insert(tk.END, text)
        self.joint_status_text.configure(state=tk.DISABLED)

    def _post(self, event: str, payload: object) -> None:
        self.events.put((event, payload))

    def _process_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                self._log(str(payload))
            elif event == "connected" and isinstance(payload, int):
                self._rebuild_joint_inputs(payload)
            elif event == "trajectory_index":
                if int(payload) < 0:
                    self.csv_running = False
                self._select_csv_row(int(payload))
            elif event == "collect_garbage":
                gc.collect()
            elif event == "error":
                self.csv_running = False
                messagebox.showerror("执行失败", str(payload))
        self.after(100, self._process_events)

    def _select_csv_row(self, index: int) -> None:
        children = self.csv_tree.get_children()
        self.csv_tree.selection_remove(*children)
        if 0 <= index < len(children):
            item = children[index]
            self.csv_tree.selection_set(item)
            self.csv_tree.see(item)

    def _log_from_thread(self, message: str) -> None:
        self._post("log", message)

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def _on_close(self) -> None:
        try:
            self.worker.disconnect(disable_robot=False)
        finally:
            self.destroy()


class StartupDialog(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("启动配置")
        self.resizable(False, False)
        self.selection: Optional[StartupSelection] = None

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="连接参数").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(outer, text="机器人 IP").grid(row=1, column=0, sticky="w", pady=6)
        self.ip_var = tk.StringVar(value=DEFAULT_IP)
        ttk.Entry(outer, textvariable=self.ip_var, width=24).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(outer, text="轴数").grid(row=2, column=0, sticky="w", pady=6)
        self.joint_count_var = tk.StringVar(value=str(default_joint_count()))
        joint_box = ttk.Combobox(
            outer,
            textvariable=self.joint_count_var,
            values=[str(i) for i in range(1, 13)],
            width=21,
            state="readonly",
        )
        joint_box.grid(row=2, column=1, sticky="ew", pady=6)

        buttons = ttk.Frame(outer)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="退出", command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="进入", command=self._confirm).pack(side=tk.RIGHT, padx=(0, 8))

        outer.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda _event: self._confirm())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _release_tk_variables(self) -> None:
        self.ip_var = None
        self.joint_count_var = None
        gc.collect()

    def _confirm(self) -> None:
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showerror("输入错误", "请填写机器人 IP。")
            return
        try:
            joint_count = int(self.joint_count_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "请选择有效轴数。")
            return
        if joint_count <= 0:
            messagebox.showerror("输入错误", "轴数必须大于 0。")
            return
        self.selection = StartupSelection(ip=ip, joint_count=joint_count)
        self._release_tk_variables()
        self.destroy()

    def _cancel(self) -> None:
        self.selection = None
        self._release_tk_variables()
        self.destroy()


def ask_startup_selection() -> Optional[StartupSelection]:
    dialog = StartupDialog()
    dialog.mainloop()
    selection = dialog.selection
    dialog = None
    gc.collect()
    return selection


def main() -> None:
    startup = ask_startup_selection()
    if startup is None:
        return
    app = RobotApp(startup)
    app.mainloop()


if __name__ == "__main__":
    main()
