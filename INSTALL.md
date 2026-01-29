# 安装说明

## 方法一：使用 pip 安装（推荐）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 安装 SDK（开发模式）
```bash
# Windows PowerShell 用户
$env:PYTHONUTF8=1
pip install -e .

```



## 方法二：直接运行（无需安装）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

## 测试是否安装成功

运行以下命令测试：
```bash
python -c "import Communication; import PythonWorkFlow; print('安装成功！')"
```



## 运行测试脚本
确保在项目根目录下运行：
1. moveJ读取csv文件并运行
```bash
python Tests\moveJ.py
```

2. 各类功能示例
```bash
python Tests\simple.py
```

**注意**：使用此方法时，必须在项目根目录下运行，否则会找不到模块。



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

### Q: 运行时出现以下错误
```
连接成功！启动 ModBusService...
❌ 读取参数失败: ModbusClientMixin.read_holding_registers() got an unexpected keyword argument 'device_id'
[ERROR] 写入单个线圈失败: ModbusClientMixin.write_coil() got an unexpected keyword argument 'device_id'
Traceback (most recent call last):
  File "E:\mecheye_nai_robot_tcp\SDKPythonV2-main\Communication\ModBusService.py", line 329, in _read_parameters_once_safe
    regs_part1 = self._com.read_holding_registers_block(p_start, 125)
  File "E:\mecheye_nai_robot_tcp\SDKPythonV2-main\Communication\ModBusCommunicator.py", line 242, in read_holding_registers_block
    rr = self.client.read_holding_registers(
TypeError: ModbusClientMixin.read_holding_registers() got an unexpected keyword argument 'device_id'
```

A: 检查自己的pymodbus版本，最好为3.11.**

