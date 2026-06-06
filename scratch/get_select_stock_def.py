import os

user_dir = r"C:\Users\User"
print("Scanning C:\\Users\\User for all CSV files...")
count = 0
for root, dirs, files in os.walk(user_dir):
    if any(p in root for p in ["AppData\\Local\\Microsoft", "AppData\\Roaming\\npm", "AppData\\Local\\Google", ".git"]):
        continue
    for f in files:
        if f.endswith(".csv"):
            f_path = os.path.join(root, f)
            print(f"Found CSV: {f_path} (Size: {os.path.getsize(f_path)})")
            count += 1
print(f"Total CSV files found: {count}")
