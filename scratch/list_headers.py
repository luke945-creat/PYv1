import urllib.request
import json
import ssl

ssl_context = ssl._create_unverified_context()
swagger_url = "https://www.tpex.org.tw/openapi/swagger.json"

try:
    req = urllib.request.Request(swagger_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context) as res:
        spec = json.loads(res.read().decode('utf-8'))
        paths = spec.get("paths", {})
        
        target_paths = ["/tpex_trading_warning_information", "/tpex_trading_warning_note"]
        for tp in target_paths:
            if tp in paths:
                print(f"Path: {tp}")
                get_op = paths[tp].get("get", {})
                parameters = get_op.get("parameters", [])
                print("  Parameters:", parameters)
except Exception as e:
    print("Error:", e)
