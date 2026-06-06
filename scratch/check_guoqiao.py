import json
import os

cache_path = r"c:\Users\User\OneDrive\桌面\開發\ilikeblackgay-main\db\prices_cache.json"
with open(cache_path, "r", encoding="utf-8-sig") as f:
    cache = json.load(f)

prices = cache["1312"]["prices"]

# We know:
# June 4th (115.06.04) Close = 14.20
# June 3rd (115.06.03) Close = 14.55
# Let's print historical prices and their index relative to June 4th and June 3rd.

idx_june4 = -1
idx_june3 = -1
for idx, p in enumerate(prices):
    if p["Date"] == "2026-06-04":
        idx_june4 = idx
    if p["Date"] == "2026-06-03":
        idx_june3 = idx

print(f"June 4 index: {idx_june4}, June 3 index: {idx_june3}")

def check_returns_for_target(target_idx, target_date, target_val):
    print(f"\n--- Checking returns ending on {target_date} (Announced: {target_val}%) ---")
    close_target = prices[target_idx]["Close"]
    for offset in range(1, 10):
        base_idx = target_idx - offset
        if base_idx >= 0:
            close_base = prices[base_idx]["Close"]
            ret = (close_target - close_base) / close_base * 100
            print(f"Offset {offset} (Base Date: {prices[base_idx]['Date']}, Base Close: {close_base:.2f}): Calculated Return = {ret:.2f}% (Diff: {abs(ret - target_val):.2f}%)")

check_returns_for_target(idx_june4, "2026-06-04", 36.88)
check_returns_for_target(idx_june3, "2026-06-03", 38.10)
