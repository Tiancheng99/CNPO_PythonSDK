import pandas as pd
import numpy as np
import io

# 原始 CSV 数据 (这里使用字符串模拟文件读取)
csv_data = """ID,J1,J2,J3,J4,J5,J6,Info
1,-155.271720973102,-120.29994860799,-89.5036314428751,-150.213498913766,23.7162226817637,89.4749802625856,A1
2,-140.237185470967,-125.738056335488,-80.4732538503557,-153.728784076725,38.750665471051,89.381535145232,A2
3,-125.49706495027,-93.3085730427543,-98.0160254150156,-168.582814802847,53.4907358253727,89.3309813630787,A3
4,-143.83377533308,-84.0506618201835,-107.310967015086,-168.591042968482,35.1540921433007,89.3981813366666,A4
5,-141.575313524726,-104.616853959941,-97.9929620293944,-157.334668478568,37.4125432905067,89.387450309774,A5
"""

# 读取数据
df = pd.read_csv(io.StringIO(csv_data))

# 定义需要转换的关节列
joint_columns = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6']

# 将弧度转换为角度
角度 = 弧度 * (180 / pi)
df[joint_columns] = df[joint_columns].apply(lambda x: x * 180 / np.pi)

# 将角度转换为弧度
# df[joint_columns] = df[joint_columns].apply(lambda x: x * (np.pi / 180.0))


# 重命名列以区分单位 (可选)
new_columns = {col: f'{col}' for col in joint_columns}
df.rename(columns=new_columns, inplace=True)

# 调整列顺序
df = df[['ID'] + list(new_columns.values()) + ['Info']]

# 输出到新的 CSV 文件
output_filename = 'joint_angles_degrees.csv'
# output_filename = 'joint_angles_radians.csv'
df.to_csv(output_filename, index=False, float_format='%.6f')

print(f"数据转换完成，已保存到 {output_filename}")