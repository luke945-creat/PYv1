import os
import glob

bt_dir = r"c:\Users\User\OneDrive\桌面\處置回測"
for root, dirs, files in os.walk(bt_dir):
    for f in files:
        if f.endswith(('.py', '.json', '.txt', '.csv', '.html', '.bat')):
            f_path = os.path.join(root, f)
            try:
                with open(f_path, "r", encoding="utf-8-sig", errors="ignore") as file:
                    content = file.read()
                if "1312" in content or "國喬" in content:
                    print(f"Match found in: {os.path.relpath(f_path, bt_dir)}")
            except Exception as e:
                pass
