import urllib.request
import json
import ssl
from datetime import datetime, timedelta

ssl_context = ssl._create_unverified_context()
today_str = datetime.now().strftime("%Y%m%d")
start_str = (datetime.now() - timedelta(days=12)).strftime("%Y%m%d")

twse_url = f"https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={start_str}&endDate={today_str}&sortKind=STKNO"
print("Fetching from URL:", twse_url)

try:
    req = urllib.request.Request(twse_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context) as res:
        data = json.loads(res.read().decode('utf-8'))
        rows = data.get("data", [])
        print("Total attention items returned:", len(rows))
        for row in rows:
            code = row[1]
            name = row[2]
            date_roc = row[5] # Roc date string
            close_price = row[6]
            reason = row[4]
            if code == "1312":
                print(f"Date ROC: {date_roc}, Code: {code}, Name: {name}, Close: {close_price}, Reason: {reason[:80]}")
except Exception as e:
    print("Error:", e)
