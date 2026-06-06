import os
import glob

browser_dir = r"C:\Users\User\.gemini\antigravity-ide\brain\950ca232-f069-4086-bb0a-b3e253362ca3\browser"
md_files = glob.glob(os.path.join(browser_dir, "*.md"))
for mdf in md_files:
    print("=" * 60)
    print("File:", os.path.basename(mdf))
    print("=" * 60)
    try:
        with open(mdf, "r", encoding="utf-8-sig", errors="ignore") as f:
            print(f.read())
    except Exception as e:
        print("Error:", e)
