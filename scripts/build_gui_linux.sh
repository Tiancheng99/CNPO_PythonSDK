#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

MTC_PYTHON="/home/robot/.local/share/mamba/envs/mtc/bin/python"
if [ -n "${PYTHON_BIN:-}" ]; then
    BUILD_PYTHON="$PYTHON_BIN"
elif [ -x "$MTC_PYTHON" ]; then
    BUILD_PYTHON="$MTC_PYTHON"
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
    BUILD_PYTHON="$CONDA_PREFIX/bin/python"
else
    BUILD_PYTHON="python3"
fi

echo "Using Python: $BUILD_PYTHON"
"$BUILD_PYTHON" -m pip install -r requirements.txt
"$BUILD_PYTHON" -m pip install -r requirements-build.txt
"$BUILD_PYTHON" -m PyInstaller --clean --noconfirm robot_gui.spec

PACKAGE_DIR="dist/RobotSDKV2_GUI_linux"
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"
cp -a dist/RobotSDKV2_GUI "$PACKAGE_DIR/RobotSDKV2_GUI"
cp -a Config "$PACKAGE_DIR/Config"
cat > "$PACKAGE_DIR/README.txt" <<'EOF'
RobotSDKV2_GUI Linux 运行说明

1. 保持本文件夹结构不变，不要把 RobotSDKV2_GUI 单独拿出去运行。
2. 运行方式：双击 RobotSDKV2_GUI，或在终端执行 ./RobotSDKV2_GUI。
3. 打开后先选择机器人 IP 和轴数，再进入主界面。
4. 现场需要改地址表或参数时，修改 Config 目录中的 JSON 文件即可，不需要重新打包。
5. 现场电脑需要能访问机器人 PLC 的 ModBus TCP IP 和 502 端口。
6. 如果程序异常退出，请查看同目录 RobotSDKV2_GUI.log。
EOF
chmod +x "$PACKAGE_DIR/RobotSDKV2_GUI"
echo "Build finished: $PACKAGE_DIR"
echo "Send this folder to the user: $PACKAGE_DIR"
