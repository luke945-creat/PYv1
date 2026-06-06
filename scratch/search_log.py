import os

brain_dir = r"C:\Users\User\.gemini\antigravity-ide\brain\950ca232-f069-4086-bb0a-b3e253362ca3"
log_files = []
for root, dirs, files in os.walk(brain_dir):
    for f in files:
        if f.endswith(".log"):
            log_files.append(os.path.join(root, f))

print("Found log files:", len(log_files))
for lf in log_files:
    print("Log path:", lf)
    try:
        with open(lf, "r", encoding="utf-8-sig", errors="ignore") as f:
            content = f.read()
        if "tpex" in content.lower() or "download" in content.lower():
            print("  Contains 'tpex' or 'download'!")
            for line in content.splitlines():
                if "tpex" in line.lower() or "download" in line.lower():
                    print("    ", line.strip()[:120])
    except Exception as e:
        pass
