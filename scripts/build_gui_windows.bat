@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONUTF8=1
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --noconfirm robot_gui.spec

set PACKAGE_DIR=dist\RobotSDKV2_GUI_windows
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"
copy /y dist\RobotSDKV2_GUI.exe "%PACKAGE_DIR%\RobotSDKV2_GUI.exe" >nul
xcopy /e /i /y Config "%PACKAGE_DIR%\Config" >nul
(
  echo RobotSDKV2_GUI Windows Runtime Notes
  echo.
  echo 1. Keep this folder structure unchanged. Do not run RobotSDKV2_GUI.exe outside this folder.
  echo 2. Double-click RobotSDKV2_GUI.exe to start.
  echo 3. Select robot IP and joint count before entering the main window.
  echo 4. To change address book or default parameters, edit JSON files in the Config folder. Repackaging is not required.
  echo 5. The target PC must be able to reach the robot PLC ModBus TCP IP and port 502.
  echo 6. If the program exits unexpectedly, check RobotSDKV2_GUI.log in this folder.
) > "%PACKAGE_DIR%\README.txt"
echo.
echo Build finished: %PACKAGE_DIR%
echo Send this folder to the user: %PACKAGE_DIR%
