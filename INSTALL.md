# 安装说明

## 方法一：使用 pip 安装（推荐）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 安装 SDK（开发模式）
```bash
# Windows PowerShell 用户
$env:PYTHONUTF8=1; pip install -e .

# Linux/Mac 用户
pip install -e .
```

### 3. 使用示例
```python
from Communication.ModBusService import ModBusService
from PythonWorkFlow.Core.RobotCore import RobotCore

# 代码...
```

---

## 方法二：直接运行（无需安装）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 直接运行测试脚本
确保在项目根目录下运行：
```bash
python Tests\moveJ_test.py
```

**注意**：使用此方法时，必须在项目根目录下运行，否则会找不到模块。

---

## 测试是否安装成功

运行以下命令测试：
```bash
python -c "import Communication; import PythonWorkFlow; print('安装成功！')"
```

---

## 常见问题

### Q: 遇到 UnicodeDecodeError 错误？
A: 在 Windows 上运行时添加环境变量：
```powershell
$env:PYTHONUTF8=1
```

### Q: 找不到模块？
A: 确保你在项目根目录（SDKPythonV2）下运行命令。

### Q: pip 版本过旧？
A: 升级 pip：
```bash
pip install --upgrade pip
```

### Q: 安装时提示 "系统找不到指定的文件" 错误？
A: 这是因为之前在其他路径安装过 SDK，遗留了旧的安装记录。解决方法：
```powershell
# 1. 获取 site-packages 路径
$sitePackages = python -c "import site; print(site.getsitepackages()[0])"
Write-Host "site-packages 路径: $sitePackages"

# 2. 查找并删除旧的链接文件
Get-ChildItem "$sitePackages" | Where-Object { $_.Name -like "*robot*sdk*" }
Remove-Item "$sitePackages\robot-sdk.egg-link" -Force

# 3. 重新安装
$env:PYTHONUTF8=1; pip install -e .
```
