import urllib.request
import json
import ssl
from datetime import datetime

ssl_context = ssl._create_unverified_context()
yahoo_url = "https://query1.finance.yahoo.com/v8/finance/chart/1312.TW?range=1mo&interval=1d"
print("Fetching from Yahoo:", yahoo_url)

try:
    req = urllib.request.Request(yahoo_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context) as res:
        data = json.loads(res.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        volumes = result['indicators']['quote'][0]['volume']
        for i in range(len(timestamps)):
            d_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
            print(f"Date: {d_str}, Close: {closes[i]}, Volume: {volumes[i]}")
except Exception as e:
    print("Error:", e)
