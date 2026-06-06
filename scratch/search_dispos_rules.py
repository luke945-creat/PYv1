import urllib.request
import json
import ssl

ssl_context = ssl._create_unverified_context()

test_urls = [
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information",
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information?date=1150604",
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information?Date=1150604",
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information?date=115/06/04",
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information?Date=115/06/04",
    "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information?date=2026-06-04",
]

for url in test_urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_context) as res:
            data = json.loads(res.read().decode('utf-8'))
            dates = sorted(list(set(row.get("Date", "") for row in data)))
            print(f"URL: {url}")
            print(f"  Count: {len(data)}, Dates: {dates}")
    except Exception as e:
        print(f"URL: {url} error: {e}")
