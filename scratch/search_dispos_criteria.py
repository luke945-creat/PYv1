import urllib.request
import ssl
import re

ssl_context = ssl._create_unverified_context()
url = "https://www.tpex.org.tw/web/bulletin/attention/attention_result.php?l=zh-tw"

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context) as res:
        html = res.read().decode('utf-8')
        
        # Search for all script tags or .php links inside script tags
        scripts = re.findall(r'<script.*?>((?:.|\n)*?)</script>', html)
        print("Found scripts count:", len(scripts))
        for idx, s in enumerate(scripts):
            if ".php" in s or "url" in s or "ajax" in s:
                print(f"--- Script {idx} ---")
                for line in s.splitlines():
                    if any(w in line for w in [".php", "url", "ajax", "type", "data"]):
                        print("  ", line.strip())
except Exception as e:
    print("Error:", e)
