import urllib.request
import ssl
import re

ssl_context = ssl._create_unverified_context()
url = "https://www.tpex.org.tw/zh-tw/"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ssl_context) as res:
        html = res.read().decode('utf-8', errors='ignore')
        print("Homepage HTML length:", len(html))
        
        # Search for links
        links = re.findall(r'href="([^"]+)"', html)
        print("Total links found:", len(links))
        matches = []
        for l in links:
            if "attention" in l.lower() or "%E6%B3%A8%E6%84%8F" in l or "注意" in l:
                matches.append(l)
        print("Matching links:")
        for m in sorted(list(set(matches))):
            print("  ", m)
except Exception as e:
    print("Error:", e)
