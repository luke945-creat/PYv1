import os
import glob

reports_dir = r"c:\Users\User\OneDrive\桌面\開發\ilikeblackgay-main\reports"
files = glob.glob(os.path.join(reports_dir, "*.md"))
print("Found reports:", len(files))
for f_path in files:
    with open(f_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "1312" in content or "國喬" in content:
        print(f"Match found in: {os.path.basename(f_path)}")
        # Print lines containing the match
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if "1312" in line or "國喬" in line:
                print(f"  Line {idx+1}: {line}")
