import urllib.request
import json
import ssl

ssl_context = ssl._create_unverified_context()
url = "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_note"

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context) as res:
        data = json.loads(res.read().decode('utf-8'))
        print("Warning note items count:", len(data))
        if data:
            print("First item keys:", data[0].keys())
            print("First item:", data[0])
            # Print unique dates
            dates = sorted(list(set(row.get("Date", "") for row in data)))
            print("Unique dates count:", len(dates))
            print("Dates:", dates)
except Exception as e:
    print("Error:", e)
