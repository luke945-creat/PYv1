import os
import glob
import time

download_dirs = [
    os.path.expanduser("~/Downloads"),
    "C:/Users/User/Downloads",
    "C:/Users/User/AppData/Local/Temp",
]

now = time.time()
print("Searching for recently modified CSV/HTML files...")
for d in download_dirs:
    if os.path.exists(d):
        print("Checking directory:", d)
        files = glob.glob(os.path.join(d, "*"))
        for f in files:
            try:
                mtime = os.path.getmtime(f)
                if now - mtime < 1800: # Last 30 minutes
                    print(f"Found: {os.path.basename(f)} (Size: {os.path.getsize(f)}, Modified: {time.ctime(mtime)})")
                    if f.endswith(".csv") or "attention" in f.lower():
                        # print first 5 lines
                        with open(f, "r", encoding="utf-8", errors="ignore") as file:
                            print("Content:")
                            for _ in range(5):
                                print("  ", file.readline().strip())
            except Exception as e:
                pass
