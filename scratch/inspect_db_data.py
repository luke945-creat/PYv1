import json
import os

db_path = r"c:\Users\User\OneDrive\桌面\開發\ilikeblackgay-main\db\dashboard_data.json"
if os.path.exists(db_path):
    with open(db_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    print("Items count in dashboard_data:", len(data))
    found = False
    for item in data:
        if item.get("Code") == "1312":
            print(json.dumps(item, indent=2, ensure_ascii=False))
            found = True
            break
    if not found:
        print("1312 not found in dashboard_data.json")
else:
    print("File not found")
