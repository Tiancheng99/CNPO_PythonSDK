import sqlite3
import pandas as pd # 如果安装了 pandas
import csv

def db_to_csv(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM robot_data")
    
    rows = cursor.fetchall()
    # 获取列名
    col_names = [description[0] for description in cursor.description]
    
    csv_name = db_name.replace(".db", ".csv")
    
    with open(csv_name, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        writer.writerows(rows)
        
    print(f"转换完成: {csv_name}")
    conn.close()


if __name__ == "__main__":
    db_to_csv("RobotTest_20251211_193137.db")