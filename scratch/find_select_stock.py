import os
import glob
import time

temp_dir = "C:/Users/User/AppData/Local/Temp"
now = time.time()
print("Scanning temp dir for CSV content...")
if os.path.exists(temp_dir):
    files = glob.glob(os.path.join(temp_dir, "*"))
    for f in files:
        try:
            mtime = os.path.getmtime(f)
            if now - mtime < 3600: # Last 60 minutes
                size = os.path.getsize(f)
                if size > 0 and size < 100000: # We expect it to be small (e.g. < 100KB)
                    with open(f, "r", encoding="utf-8-sig", errors="ignore") as file:
                        first_line = file.readline().strip()
                    if "日期" in first_line or "證券代號" in first_line or "證券名稱" in first_line:
                        print(f"FOUND MATCHING TEMP FILE: {f}")
                        print(f"  Size: {size}, First line: {first_line}")
                        # Copy to Downloads
                        import shutil
                        dest = "C:/Users/User/Downloads/stk_wn1430.csv"
                        shutil.copy(f, dest)
                        print(f"  Copied to: {dest}")
        except Exception as e:
            pass
else:
    print("Temp dir not found")
