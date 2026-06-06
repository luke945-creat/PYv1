import json
import os

cache_path = r"c:\Users\User\OneDrive\桌面\開發\ilikeblackgay-main\db\prices_cache.json"
with open(cache_path, "r", encoding="utf-8-sig") as f:
    cache = json.load(f)

prices = cache["1718"]["prices"]

idx_june4 = -1
for idx, p in enumerate(prices):
    if p["Date"] == "2026-06-04":
        idx_june4 = idx

print(f"1718 June 4 index: {idx_june4}")

close_target = prices[idx_june4]["Close"]
for offset in range(1, 10):
    base_idx = idx_june4 - offset
    if base_idx >= 0:
        close_base = prices[base_idx]["Close"]
        ret = (close_target - close_base) / close_base * 100
        print(f"Offset {offset} (Base Date: {prices[base_idx]['Date']}, Base Close: {close_base:.2f}): Calculated Return = {ret:.2f}% (Diff: {abs(ret - 44.70):.2f}%)")
