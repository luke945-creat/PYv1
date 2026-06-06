# -*- coding: utf-8 -*-
"""
台股處置股聽牌預測模組 (disposition_listener.py)
功能：
1. 建立近 60 個營業日的台股交易日曆。
2. 爬取 TWSE 與 TPEx 的注意股公告，統計個股截至「昨天」為止的累計/連續注意狀態。
3. 篩選出符合聽牌條件（連續2天、9日內5天、29日內11天）的股票。
4. 逆推今日價格變動與成交量門檻。
5. 獲取盤中（或當前收盤）最新價量，計算觸發進度。
6. 產出控制台看板、獨立 HTML 報表與 dashboard 整合 JSON。
"""

import urllib.request
import urllib.parse
import json
import ssl
import sys
import re
import os
from datetime import datetime, timedelta

# 確保輸出編碼為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')
ssl_context = ssl._create_unverified_context()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

# ANSI 顏色字串
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_GRAY = "\033[90m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

def log_info(msg):
    print(f"{C_CYAN}[INFO]{C_RESET} {msg}")

def log_success(msg):
    print(f"{C_GREEN}[SUCCESS]{C_RESET} {msg}")

def log_warning(msg):
    print(f"{C_YELLOW}[WARNING]{C_RESET} {msg}")

def log_error(msg):
    print(f"{C_RED}[ERROR]{C_RESET} {msg}")

# 將民國日期 (e.g. 115/06/05 或 115.06.05) 轉換為西元 YYYY-MM-DD
def convert_roc_date_to_normal(roc_date):
    if not roc_date:
        return ""
    roc_date = roc_date.strip().replace(".", "/")
    m = re.match(r"^(\d{2,3})/(\d{2})/(\d{2})$", roc_date)
    if m:
        year = int(m.group(1)) + 1911
        return f"{year}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2,3})(\d{2})(\d{2})$", roc_date)
    if m:
        year = int(m.group(1)) + 1911
        return f"{year}-{m.group(2)}-{m.group(3)}"
    return roc_date

# 格式化成交量
def format_volume(vol):
    if vol is None or vol < 0:
        return "N/A"
    return f"{int(vol / 1000):,} 張"

# 台灣股市升降單位 Tick Rounding
def round_to_taiwan_stock_tick(price, is_up):
    if price is None or price <= 0:
        return price
    
    if price < 10:
        tick = 0.01
    elif price < 50:
        tick = 0.05
    elif price < 100:
        tick = 0.1
    elif price < 500:
        tick = 0.5
    elif price < 1000:
        tick = 1.0
    else:
        tick = 5.0
        
    remainder = price % tick
    if abs(remainder) < 0.0001 or abs(remainder - tick) < 0.0001:
        return round(price, 2)
        
    if is_up:
        rounded = price - remainder + tick
    else:
        rounded = price - remainder
    return round(rounded, 2)

# 獲取交易日曆 (利用大盤指數 ^TWII)
def get_trading_calendar():
    log_info("正在從 Yahoo Finance 獲取台股交易日曆...")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/^TWII?range=3mo&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ssl_context) as res:
            data = json.loads(res.read().decode('utf-8'))
            chart = data.get("chart", {}).get("result", [])
            if not chart:
                return []
            timestamps = chart[0].get("timestamp", [])
            
            # 轉換為 YYYY-MM-DD
            dates = []
            for ts in timestamps:
                dates.append(datetime.fromtimestamp(ts).strftime("%Y-%m-%d"))
            
            # 過濾重複與排序 (新到舊)
            unique_dates = sorted(list(set(dates)), reverse=True)
            log_success(f"成功獲取 {len(unique_dates)} 個歷史交易日。")
            return unique_dates
    except Exception as e:
        log_error(f"無法獲取交易日曆: {e}")
        # 降級防禦方案：使用最近的平日日期
        dates = []
        curr = datetime.now()
        for _ in range(60):
            while curr.weekday() >= 5: # 排除週末
                curr -= timedelta(days=1)
            dates.append(curr.strftime("%Y-%m-%d"))
            curr -= timedelta(days=1)
        return dates

# 獲取上市注意股歷史 (TWSE)
def fetch_twse_attention_history(start_date_str, end_date_str):
    log_info(f"正在從證交所獲取上市注意股歷史 ({start_date_str} ~ {end_date_str})...")
    url = f"https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={start_date_str}&endDate={end_date_str}&sortKind=STKNO"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    records = []
    try:
        with urllib.request.urlopen(req, context=ssl_context) as res:
            data = json.loads(res.read().decode('utf-8'))
            rows = data.get("data", [])
            for row in rows:
                norm_date = convert_roc_date_to_normal(row[5])
                records.append({
                    "Date": norm_date,
                    "Code": row[1].strip(),
                    "Name": row[2].strip(),
                    "Reason": row[4].strip(),
                    "Close": row[6].strip(),
                    "Market": "上市"
                })
        log_success(f"成功獲取 {len(records)} 筆上市注意股記錄。")
    except Exception as e:
        log_error(f"獲取上市注意股歷史失敗: {e}")
    return records

# 獲取上櫃注意股歷史 (TPEx)
def fetch_tpex_attention_history(start_date, end_date):
    # 將 datetime 物件或 YYYY-MM-DD 轉為民國格式
    def to_roc_date_str(dt):
        return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"
        
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    start_roc = to_roc_date_str(start_dt)
    end_roc = to_roc_date_str(end_dt)
    
    log_info(f"正在從櫃買中心獲取上櫃注意股歷史 ({start_roc} ~ {end_roc})...")
    
    base_url = "https://www.tpex.org.tw/web/bulletin/warning_information/trading_warning_information_result.php"
    params = {
        "l": "zh-tw",
        "startDate": start_roc,
        "endDate": end_roc,
        "type": "all",
        "order": "date"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    records = []
    try:
        with urllib.request.urlopen(req, context=ssl_context) as res:
            data = json.loads(res.read().decode('utf-8'))
            tables = data.get("tables", [])
            if tables:
                rows = tables[0].get("data", [])
                for row in rows:
                    norm_date = convert_roc_date_to_normal(row[5])
                    records.append({
                        "Date": norm_date,
                        "Code": row[1].strip(),
                        "Name": row[2].strip(),
                        "Reason": row[4].strip(),
                        "Close": row[6].strip(),
                        "Market": "上櫃"
                    })
        log_success(f"成功獲取 {len(records)} 筆上櫃注意股記錄。")
    except Exception as e:
        log_error(f"獲取上櫃注意股歷史失敗: {e}")
    return records

# 從處置期間字串中提取開始與結束日期
def parse_disposal_date_range(period_str):
    matches = re.findall(r"(\d{2,3})[/\.\-](\d{2})[/\.\-](\d{2})", period_str)
    if len(matches) >= 2:
        start_yr = int(matches[0][0]) + 1911
        start_date = f"{start_yr}-{matches[0][1]}-{matches[0][2]}"
        end_yr = int(matches[1][0]) + 1911
        end_date = f"{end_yr}-{matches[1][1]}-{matches[1][2]}"
        return start_date, end_date
    return None

# 獲取當前處置中的股票代號
def get_active_disposition_stocks(target_date_str):
    disposed_codes = set()
    
    # 1. 上市處置有價證券
    try:
        url = "https://openapi.twse.com.tw/v1/announcement/punish"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_context) as res:
            items = json.loads(res.read().decode('utf-8'))
            for item in items:
                code = item.get("Code")
                period = item.get("DispositionPeriod", "")
                r = parse_disposal_date_range(period)
                if r and code:
                    start, end = r
                    if target_date_str <= end:
                        disposed_codes.add(code)
    except Exception as e:
        log_warning(f"無法獲取上市處置股名單: {e}")
        
    # 2. 上櫃處置有價證券
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_context) as res:
            items = json.loads(res.read().decode('utf-8'))
            for item in items:
                code = item.get("SecuritiesCompanyCode")
                period = item.get("DispositionPeriod", "")
                r = parse_disposal_date_range(period)
                if r and code:
                    start, end = r
                    if target_date_str <= end:
                        disposed_codes.add(code)
    except Exception as e:
        log_warning(f"無法獲取上櫃處置股名單: {e}")
        
    return disposed_codes

# 獲取個股歷史收盤價與成交量
def get_stock_history(code, is_tpex):
    cache_path = os.path.join(DB_DIR, "prices_cache.json")
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8-sig") as fh:
                cache = json.load(fh)
            entry = cache.get(str(code)) or cache.get(code)
            if isinstance(entry, dict) and isinstance(entry.get("prices"), list) and len(entry["prices"]) >= 60:
                return entry["prices"]
    except Exception:
        pass

    symbol = f"{code}.TWO" if is_tpex else f"{code}.TW"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ssl_context) as res:
            data = json.loads(res.read().decode('utf-8'))
            chart = data.get("chart", {}).get("result", [])
            if not chart:
                return []
            result = chart[0]
            meta = result.get("meta", {})
            timestamps = result.get("timestamp", [])
            quotes = result.get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])
            volumes = quotes.get("volume", [])
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            opens = quotes.get("open", [])
            
            prices = []
            for i in range(len(timestamps)):
                d_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
                close_val = closes[i]
                vol_val = volumes[i] if volumes[i] is not None else 0.0
                
                # 如果是最後一個資料點且 close_val 為 None，嘗試從 meta 的 regularMarketPrice 補件
                if i == len(timestamps) - 1 and close_val is None:
                    close_val = meta.get("regularMarketPrice")
                
                if close_val is not None:
                    prices.append({
                        "Date": d_str,
                        "Close": float(close_val),
                        "Volume": float(vol_val),
                        "High": float(highs[i]) if highs[i] is not None else float(close_val),
                        "Low": float(lows[i]) if lows[i] is not None else float(close_val),
                        "Open": float(opens[i]) if opens[i] is not None else float(close_val)
                    })
            return prices
    except Exception as e:
        log_error(f"無法獲取 {code} 歷史價格: {e}")
        return []

def main():
    print(f"{C_BOLD}{C_CYAN}=========================================================={C_RESET}")
    print(f"{C_BOLD}{C_CYAN}            台股處置股盤中即時聽牌預測系統 (disposition_listener.py){C_RESET}")
    print(f"{C_BOLD}{C_CYAN}=========================================================={C_RESET}")
    print(f"啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: 建立交易日曆
    calendar = get_trading_calendar()
    if not calendar or len(calendar) < 30:
        log_error("歷史交易日數量不足，無法執行預測。")
        sys.exit(1)
        
    # 自動判定 T (今天) 與 T-1 (昨天)
    # 若今日是交易日且開盤後(>=09:00)，則 T 是今日，yesterday (T-1) 是 calendar 中的最接近的前一個日期
    # 若今日非交易日，則 T 是 calendar[0], yesterday (T-1) 是 calendar[1]
    today_date_str = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().time()
    
    is_today_trading_day = False
    
    # 判斷今天是不是工作天且非週末
    if datetime.now().weekday() < 5:
        is_today_trading_day = True
        
    if is_today_trading_day and now_time >= datetime.strptime("09:00", "%H:%M").time():
        T_date = today_date_str
        # yesterday 必須是 calendar 中小於今天的第一個日期
        yesterday_candidates = [d for d in calendar if d < T_date]
        yesterday_date = yesterday_candidates[0] if yesterday_candidates else calendar[0]
    else:
        # 非開盤時間或週末，T_date 設為 calendar 中最新的交易日，yesterday 設為其次新的交易日
        T_date = calendar[0]
        yesterday_date = calendar[1]
        
    log_info(f"預測執行基準：今日 (T)={T_date}，昨日 (T-1)={yesterday_date}")
    
    # 找出 T-1 及往前的 29 個營業日
    t_days = [d for d in calendar if d <= yesterday_date][:29]
    if len(t_days) < 29:
        log_error(f"歷史營業日不足 29 天 (當前可用: {len(t_days)} 天)")
        sys.exit(1)
        
    # Step 2: 爬取 attention 歷史 (覆蓋過去 50 天以防萬一)
    start_history_dt = datetime.strptime(yesterday_date, "%Y-%m-%d") - timedelta(days=50)
    start_history_str = start_history_dt.strftime("%Y%m%d")
    end_history_str = datetime.strptime(yesterday_date, "%Y-%m-%d").strftime("%Y%m%d")
    
    twse_notices = fetch_twse_attention_history(start_history_str, end_history_str)
    tpex_notices = fetch_tpex_attention_history(start_history_dt.strftime("%Y-%m-%d"), yesterday_date)
    
    # 合併為一個便於查詢的結構: { (date, code): record }
    notice_map = {}
    all_notified_codes = set()
    stock_meta = {} # 記錄 code 的 name 與 market
    
    for r in twse_notices + tpex_notices:
        key = (r["Date"], r["Code"])
        notice_map[key] = r
        all_notified_codes.add(r["Code"])
        stock_meta[r["Code"]] = {
            "name": r["Name"],
            "market": r["Market"]
        }
        
    log_info(f"統計區間內，共有 {len(all_notified_codes)} 檔個股曾被列為注意股。")
    
    # 獲取當前已處置股票 (避免重複列出)
    disposed_codes = get_active_disposition_stocks(T_date)
    log_info(f"截至今日處置中的個股數量: {len(disposed_codes)}")
    
    # Step 3: 統計截至昨天的累計狀態並篩選聽牌股
    listening_candidates = []
    
    for code in all_notified_codes:
        if code in disposed_codes:
            continue
            
        # 計算連續注意天數
        consecutive_days = 0
        for d in t_days:
            if (d, code) in notice_map:
                consecutive_days += 1
            else:
                break
                
        # 9日內累計注意天數 (t_days[0..8])
        cumulative_9 = sum(1 for d in t_days[:9] if (d, code) in notice_map)
        
        # 29日內累計注意天數 (t_days[0..28])
        cumulative_29 = sum(1 for d in t_days[:29] if (d, code) in notice_map)
        
        # 判斷是否滿足聽牌條件
        # 1. 連續2天
        # 2. 9日內累計5天
        # 3. 29日內累計11天
        reasons_to_listen = []
        if consecutive_days >= 2:
            reasons_to_listen.append(f"連續注意 {consecutive_days} 天 (背景>=2)")
        if cumulative_9 >= 5:
            reasons_to_listen.append(f"9日內累計 {cumulative_9} 天 (背景>=5)")
        if cumulative_29 >= 11:
            reasons_to_listen.append(f"29日內累計 {cumulative_29} 天 (背景>=11)")
            
        if reasons_to_listen:
            listening_candidates.append({
                "code": code,
                "name": stock_meta[code]["name"],
                "market": stock_meta[code]["market"],
                "consecutive": consecutive_days,
                "cumulative_9": cumulative_9,
                "cumulative_29": cumulative_29,
                "listening_reasons": reasons_to_listen
            })
            
    log_success(f"統計出聽牌股背景候選個股: {len(listening_candidates)} 檔。")
    
    # Step 4: 對聽牌股進行門檻與即時價量試算
    listening_results = []
    
    for stock in listening_candidates:
        code = stock["code"]
        is_tpex = stock["market"] == "上櫃"
        
        # 獲取昨日注意股公告原因
        yesterday_reason = ""
        yesterday_record = notice_map.get((yesterday_date, code))
        if yesterday_record:
            yesterday_reason = yesterday_record["Reason"]
            
        # 獲取價格歷史
        history = get_stock_history(code, is_tpex)
        if not history or len(history) < 10:
            log_warning(f"無法獲取 {code} {stock['name']} 的足夠歷史價格，跳過。")
            continue
            
        # 確認昨日價格正確性與同步
        last_idx = len(history) - 1
        hist_date = history[last_idx]["Date"]
        
        # 如果 Yahoo 的最後一天大於昨日（即已含今日盤中數據），則 last_idx 指向昨日
        if hist_date >= T_date:
            # 尋找昨日 index
            for idx, item in enumerate(history):
                if item["Date"] == yesterday_date:
                    last_idx = idx
                    break
            else:
                last_idx = len(history) - 2
                
        # 截至昨日的最新收盤與成交量
        yesterday_close = history[last_idx]["Close"]
        yesterday_vol = history[last_idx]["Volume"]
        
        # 解析並設定計算規則
        std_pct = 30.0 if is_tpex else 32.0
        
        # 如果公告原因有寫 6日變動幅度，抓取
        rule6_pct = None
        m6 = re.search(r"六個營業日.*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%", yesterday_reason) or re.search(r"六日.*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%", yesterday_reason)
        if m6:
            rule6_pct = float(m6.group(1))
            
        # 解析 30, 60, 90 日漲跌幅限制
        rule30_pct = 100.0
        m30 = re.search(r"(?:三十個營業日|三十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%", yesterday_reason)
        has_rule30 = False
        if m30:
            rule30_pct = float(m30.group(1))
            has_rule30 = True
            
        rule60_pct = 130.0
        m60 = re.search(r"(?:六十個營業日|六十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%", yesterday_reason)
        has_rule60 = False
        if m60:
            rule60_pct = float(m60.group(1))
            has_rule60 = True
            
        rule90_pct = 160.0
        m90 = re.search(r"(?:九十個營業日|九十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%", yesterday_reason)
        has_rule90 = False
        if m90:
            rule90_pct = float(m90.group(1))
            has_rule90 = True
            
        # 獲取歷史基準價
        # 當前 history 長度相對於昨天的 last_idx 計算基準偏移
        p_t5 = history[last_idx - 5]["Close"] if last_idx >= 5 else None
        p_t29 = history[last_idx - 29]["Close"] if last_idx >= 29 else None
        p_t59 = history[last_idx - 59]["Close"] if last_idx >= 59 else None
        p_t89 = history[last_idx - 89]["Close"] if last_idx >= 89 else None
        
        # 計算價格門檻
        price_thresholds = []
        if p_t5:
            # 1. 標準 6日變動
            up_6d = round_to_taiwan_stock_tick(p_t5 * (1 + std_pct / 100.0), True)
            down_6d = round_to_taiwan_stock_tick(p_t5 * (1 - std_pct / 100.0), False)
            price_thresholds.append({
                "rule": f"6日累積變動 (標準 {std_pct}%)",
                "base_price": p_t5,
                "up_price": up_6d,
                "down_price": down_6d,
                "is_primary": True
            })
            
            # 2. 公告公告值變動
            if rule6_pct is not None:
                up_6d_act = round_to_taiwan_stock_tick(p_t5 * (1 + rule6_pct / 100.0), True)
                down_6d_act = round_to_taiwan_stock_tick(p_t5 * (1 - rule6_pct / 100.0), False)
                price_thresholds.append({
                    "rule": f"6日累積變動 (今日公告值 {rule6_pct}%)",
                    "base_price": p_t5,
                    "up_price": up_6d_act,
                    "down_price": down_6d_act,
                    "is_primary": False
                })
            
        if p_t29 and (has_rule30 or not is_tpex): # 30日
            up_30d = round_to_taiwan_stock_tick(p_t29 * (1 + rule30_pct / 100.0), True)
            price_thresholds.append({
                "rule": f"30日累積變動 ({rule30_pct}%)",
                "base_price": p_t29,
                "up_price": up_30d,
                "down_price": None,
                "is_primary": has_rule30
            })
            
        if p_t59 and has_rule60: # 60日
            up_60d = round_to_taiwan_stock_tick(p_t59 * (1 + rule60_pct / 100.0), True)
            price_thresholds.append({
                "rule": f"60日累積變動 ({rule60_pct}%)",
                "base_price": p_t59,
                "up_price": up_60d,
                "down_price": None,
                "is_primary": has_rule60
            })
            
        if p_t89 and has_rule90: # 90日
            up_90d = round_to_taiwan_stock_tick(p_t89 * (1 + rule90_pct / 100.0), True)
            price_thresholds.append({
                "rule": f"90日累積變動 ({rule90_pct}%)",
                "base_price": p_t89,
                "up_price": up_90d,
                "down_price": None,
                "is_primary": has_rule90
            })
            
        # 成交量門檻計算
        vol_thresholds = []
        
        # 1. 60日均量放大
        avg_vol_60 = 0.0
        if last_idx >= 59:
            vol_sum = sum(history[last_idx - i]["Volume"] for i in range(60))
            avg_vol_60 = vol_sum / 60.0
            
        vol_multiplier = 5.0
        mv = re.search(r"(?:成交量為最近六十個營業日日平均成交量之|日平均成交量之|日平均成交量.*放大)\s*([\d\.]+)\s*倍", yesterday_reason)
        if mv:
            vol_multiplier = float(mv.group(1))
            
        if avg_vol_60 > 0:
            vol_thresholds.append({
                "rule": f"60日日平均成交量放大 ({vol_multiplier}倍)",
                "baseline": avg_vol_60,
                "trigger_vol": round(avg_vol_60 * vol_multiplier)
            })
            
        # 2. 週轉率與流通股數倒推
        today_tr = 0.0
        mtr = re.search(r"(?:週轉率為|週轉率達)\s*([\d\.]+)%", yesterday_reason)
        if mtr:
            today_tr = float(mtr.group(1))
            
        est_shares = 0.0
        if yesterday_vol > 0 and today_tr > 0:
            est_shares = yesterday_vol * 100.0 / today_tr
            
        if est_shares > 0:
            # 當日週轉率達 10%
            vol_thresholds.append({
                "rule": "當日週轉率達 10.0% 門檻",
                "baseline": est_shares,
                "trigger_vol": round(est_shares * 0.10)
            })
            
            # 6日累積週轉率達 50% (明日需達多少)
            sum_vol_5 = sum(history[last_idx - i]["Volume"] for i in range(5))
            sum_tr_5 = (sum_vol_5 / est_shares) * 100.0
            req_tr_today = 50.0 - sum_tr_5
            trigger_vol_6tr = max(0.0, est_shares * (req_tr_today / 100.0)) if req_tr_today > 0 else 0.0
            
            vol_thresholds.append({
                "rule": f"6日累積週轉率達 50.0% (今日需達 {req_tr_today:.2f}%)",
                "baseline": est_shares,
                "trigger_vol": round(trigger_vol_6tr)
            })
            
        # 獲取「今日」盤中最新價量
        # 如果 history 最新日期是今天，則提取它；否則利用 regularMarketPrice / regularMarketVolume 補件的資料
        current_close = yesterday_close
        current_vol = 0.0
        if len(history) > 0 and history[-1]["Date"] == T_date:
            current_close = history[-1]["Close"]
            current_vol = history[-1]["Volume"]
            
        # 找出最容易觸發的價格門檻 (包含最近 6 日最高/最低收盤價限制)
        best_price_calc = None
        min_abs_pct = 9999.0
        
        # 過去 5 個營業日 (T-5 至 T-1) 的收盤價列表：last_idx 到 last_idx-4
        closes_5d = [history[last_idx - i]["Close"] for i in range(5)]
        max_close_5d = max(closes_5d)
        min_close_5d = min(closes_5d)
        
        for pt in price_thresholds:
            if not pt.get("is_primary", True):
                continue
            if pt["up_price"] is not None:
                # 必須大於等於原本門檻，且必須是過去 6 天最高收盤價
                effective_up = max(pt["up_price"], max_close_5d)
                effective_up = round_to_taiwan_stock_tick(effective_up, True)
                chg = ((effective_up - current_close) / current_close) * 100.0
                if abs(chg) < min_abs_pct:
                    min_abs_pct = abs(chg)
                    best_price_calc = {"price": effective_up, "change": chg, "rule": pt["rule"], "dir": "▲"}
            if pt["down_price"] is not None:
                # 必須小於等於原本門檻，且必須是過去 6 天最低收盤價
                effective_down = min(pt["down_price"], min_close_5d)
                effective_down = round_to_taiwan_stock_tick(effective_down, False)
                chg = ((effective_down - current_close) / current_close) * 100.0
                if abs(chg) < min_abs_pct:
                    min_abs_pct = abs(chg)
                    best_price_calc = {"price": effective_down, "change": chg, "rule": pt["rule"], "dir": "▼"}
                    
        # 找出成交量觸發門檻
        trigger_vol_val = 0
        trigger_vol_rule = "N/A"
        if vol_thresholds:
            # 取最小的正成交量門檻
            pos_vols = [v for v in vol_thresholds if v["trigger_vol"] > 0]
            if pos_vols:
                min_v = min(pos_vols, key=lambda x: x["trigger_vol"])
                trigger_vol_val = min_v["trigger_vol"]
                trigger_vol_rule = min_v["rule"]
            else:
                trigger_vol_val = 0
                trigger_vol_rule = "任意成交量皆會觸發 (前5日已達標)"
        elif avg_vol_60 > 0:
            # 默認 60日放大 5 倍
            trigger_vol_val = round(avg_vol_60 * 5.0)
            trigger_vol_rule = "60日日平均成交量放大 (5倍) (默認)"
            
        # 計算達標百分比
        price_progress = 100.0
        if best_price_calc:
            price_progress = (current_close / best_price_calc["price"]) * 100.0
            
        vol_progress = 0.0
        if trigger_vol_val > 0:
            vol_progress = (current_vol / trigger_vol_val) * 100.0
        elif trigger_vol_rule == "任意成交量皆會觸發 (前5日已達標)":
            vol_progress = 100.0
            
        listening_results.append({
            "code": code,
            "name": stock["name"],
            "market": stock["market"],
            "reasons": stock["listening_reasons"],
            "yesterday_close": yesterday_close,
            "current_close": current_close,
            "current_vol": current_vol,
            "best_price_calc": best_price_calc,
            "trigger_vol_val": trigger_vol_val,
            "trigger_vol_rule": trigger_vol_rule,
            "price_progress": price_progress,
            "vol_progress": vol_progress,
            "price_thresholds": price_thresholds,
            "vol_thresholds": vol_thresholds,
            "yesterday_reason": yesterday_reason
        })
        
    # Step 5: 排序結果（按最容易觸發價格進度排序）
    listening_results = sorted(listening_results, key=lambda x: abs(x["best_price_calc"]["change"]) if x["best_price_calc"] else 9999.0)
    
    # Step 6: 控制台 CLI 輸出
    print("\n" + C_BOLD + C_YELLOW + "【台股處置股聽牌監控看板 - 盤中即時預測】" + C_RESET)
    print(C_GRAY + "---------------------------------------------------------------------------------" + C_RESET)
    print(f" 序  代號  名稱      市場  昨日收盤  今日最新  今日成交  最易觸發價格門檻 (幅度)   觸發量門檻")
    print(C_GRAY + "---------------------------------------------------------------------------------" + C_RESET)
    
    for idx, r in enumerate(listening_results):
        p_calc = r["best_price_calc"]
        p_str = "N/A"
        hl_color = C_RESET
        if p_calc:
            p_str = f"{p_calc['dir']} {p_calc['price']:.2f}元 ({p_calc['change']:+.2f}%)"
            if abs(p_calc['change']) <= 1.0:
                hl_color = C_RED + C_BOLD
            elif abs(p_calc['change']) <= 4.0:
                hl_color = C_YELLOW
                
        vol_str = format_volume(r["trigger_vol_val"])
        if r["trigger_vol_val"] == 0:
            vol_str = "任意量"
            
        idx_str = f"[{idx+1}]"
        print(f" {idx_str:<3} {r['code']:<5} {r['name']:<8} {r['market']:<3} {r['yesterday_close']:>8.2f} {r['current_close']:>8.2f} {format_volume(r['current_vol']):>8} {hl_color}{p_str:<23}{C_RESET} {vol_str}")
        
    print(C_GRAY + "---------------------------------------------------------------------------------" + C_RESET)
    print(f" 共有 {len(listening_results)} 檔個股滿足昨日聽牌背景條件。")
    print(f" 註：亮{C_RED}紅{C_RESET}代表極易觸發，亮{C_YELLOW}黃{C_RESET}代表重點監控。\n")
    
    # Step 7: 將結果寫回本地工作區的 db/ 目錄，避免依賴舊路徑。
    db_listening_path = os.path.join(DB_DIR, "listening_data.json")
    os.makedirs(os.path.dirname(db_listening_path), exist_ok=True)
        
    # 包裝輸出為網頁與 JS 載入友善的 JSON 結構
    output_json = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "T_date": T_date,
        "yesterday_date": yesterday_date,
        "listening_stocks": listening_results
    }
    
    try:
        with open(db_listening_path, "w", encoding="utf-8") as f:
            json.dump(output_json, f, ensure_ascii=False, indent=4)
        log_success(f"成功將聽牌監控 JSON 數據寫入至: {db_listening_path}")
    except Exception as e:
        log_error(f"寫入 JSON 數據庫失敗: {e}")
        
    # 也儲存一份在本地端的 targets_listening.json
    try:
        local_json_path = "listening_data.json"
        with open(local_json_path, "w", encoding="utf-8") as f:
            json.dump(output_json, f, ensure_ascii=False, indent=4)
        log_success(f"成功將聽牌監控 JSON 數據備份至本地: {local_json_path}")
    except Exception as e:
        pass
        
    # Step 8: 生成美觀的獨立 HTML 報告 disposition_listening.html
    # 這裡用 JS 直接載入 db/listening_data.json，避免舊的靜態 HTML 內容一直顯示舊資料。
    html_content = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 台股處置聽牌即時預測看板</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>"""
    html_content += """
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --color-red: #ef4444;
            --color-yellow: #eab308;
            --color-green: #10b981;
            --color-cyan: #06b6d4;
            --border-color: #334155;
        }
        body {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', 'Outfit', sans-serif;
            margin: 0;
            padding: 24px;
        }
        header {
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }
        h1 {
            margin: 0;
            font-size: 1.8rem;
            color: var(--text-primary);
        }
        .update-time {
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            background-color: var(--bg-secondary);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        th, td {
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th {
            background-color: rgba(255,255,255,0.03);
            color: var(--text-secondary);
            font-weight: 600;
        }
        tr:last-child td {
            border-bottom: none;
        }
        tr:hover {
            background-color: rgba(255,255,255,0.01);
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .badge-red {
            background-color: rgba(239, 68, 68, 0.15);
            color: var(--color-red);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .badge-yellow {
            background-color: rgba(234, 179, 8, 0.15);
            color: var(--color-yellow);
            border: 1px solid rgba(234, 179, 8, 0.3);
        }
        .badge-gray {
            background-color: rgba(148, 163, 184, 0.15);
            color: var(--text-secondary);
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .text-right {
            text-align: right;
        }
        .text-center {
            text-align: center;
        }
        .price-up {
            color: var(--color-red);
            font-weight: bold;
        }
        .price-down {
            color: var(--color-green);
            font-weight: bold;
        }
        .muted {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
    </style>
    <script>
        async function loadListenerData() {
            const tbody = document.getElementById('listener-body');
            const stamp = document.getElementById('last-updated');
            const meta = document.getElementById('meta-range');
            try {
                const res = await fetch('./db/listening_data.json?t=' + new Date().getTime(), { cache: 'no-store' });
                if (!res.ok) throw new Error('無法讀取 db/listening_data.json');
                const data = await res.json();
                const stocks = Array.isArray(data.listening_stocks) ? data.listening_stocks : [];
                stamp.textContent = '最後更新: ' + (data.last_updated || 'N/A') + '（每 60 秒自動重新整理）';
                meta.textContent = '基準營業日: ' + (data.yesterday_date || 'N/A') + ' ｜ 預測目標日: ' + (data.T_date || 'N/A');
                if (!stocks.length) {
                    tbody.innerHTML = '<tr><td colspan="10" class="text-center" style="color: var(--text-secondary); padding: 40px 0;">☕ 目前沒有符合聽牌背景的個股。</td></tr>';
                    return;
                }
                tbody.innerHTML = stocks.map(stock => {
                    const pCalc = stock.best_price_calc || null;
                    let pStr = 'N/A';
                    let pCls = '';
                    let badgeClass = 'badge-gray';
                    let badgeText = '監控中';
                    if (pCalc) {
                        pStr = `${pCalc.dir} ${pCalc.price.toFixed(2)}元 (${pCalc.change >= 0 ? '+' : ''}${pCalc.change.toFixed(2)}%)`;
                        pCls = pCalc.dir === '▲' ? 'price-up' : 'price-down';
                        if (Math.abs(pCalc.change) <= 1.0) {
                            badgeClass = 'badge-red';
                            badgeText = '🔥 極易觸發';
                        } else if (Math.abs(pCalc.change) <= 4.0) {
                            badgeClass = 'badge-yellow';
                            badgeText = '⚠️ 重點預警';
                        }
                    }
                    let volStr = stock.trigger_vol_val > 0 ? (stock.trigger_vol_val / 1000).toFixed(0) + ' 張' : '任意量皆觸發';
                    const reasons = (stock.reasons || []).map(r => '• ' + r).join('<br>');
                    return `
                        <tr>
                            <td><strong>${stock.code}</strong></td>
                            <td>${stock.name}</td>
                            <td class="text-center">${stock.market}</td>
                            <td style="font-size: 0.85rem; color: var(--text-secondary);">${reasons}</td>
                            <td class="text-right">${stock.yesterday_close.toFixed(2)} 元</td>
                            <td class="text-right"><strong>${stock.current_close.toFixed(2)} 元</strong></td>
                            <td class="text-right">${(stock.current_vol / 1000).toFixed(0)} 張</td>
                            <td class="text-right ${pCls}">${pStr}</td>
                            <td class="text-right" style="color: var(--color-cyan); font-size: 0.9rem;">${volStr}<div style="font-size: 0.75rem; color: var(--text-secondary);">${stock.trigger_vol_rule || ''}</div></td>
                            <td class="text-center"><span class="badge ${badgeClass}">${badgeText}</span></td>
                        </tr>`;
                }).join('');
            } catch (err) {
                tbody.innerHTML = '<tr><td colspan="10" class="text-center" style="color: var(--text-secondary); padding: 40px 0;">⚠️ 無法載入最新聽牌資料，請確認 db/listening_data.json 已生成。</td></tr>';
                console.error(err);
            }
        }
        window.addEventListener('load', function() {
            loadListenerData();
            setInterval(function() {
                loadListenerData();
            }, 60000);
        });
        setTimeout(function() {
            location.reload();
        }, 60000);
    </script>
</head>
<body>
    <header>
        <div>
            <h1>🔥 台股處置聽牌即時預測監控</h1>
            <div id="meta-range" class="muted" style="margin-top: 6px;">基準營業日: 載入中…</div>
        </div>
        <div id="last-updated" class="update-time">最後更新: 載入中…（每 60 秒自動重新整理）</div>
    </header>
    <table>
        <thead>
            <tr>
                <th>代號</th>
                <th>名稱</th>
                <th class="text-center">市場</th>
                <th>聽牌背景原因</th>
                <th class="text-right">昨日收盤</th>
                <th class="text-right">今日最新</th>
                <th class="text-right">今日成交</th>
                <th class="text-right">最易觸發價格門檻</th>
                <th class="text-right">成交量觸發門檻</th>
                <th class="text-center">狀態</th>
            </tr>
        </thead>
        <tbody id="listener-body">
            <tr><td colspan="10" class="text-center" style="color: var(--text-secondary); padding: 40px 0;">資料載入中…</td></tr>
        </tbody>
    </table>
    <div style="margin-top: 30px; font-size: 0.85rem; color: var(--text-secondary); border-top: 1px solid var(--border-color); padding-top: 12px;">
        * 免責聲明：本儀表板所載數值為透過公開公式逆推之估算值，實際注意與處置股票之認定以臺灣證券交易所與中華民國證券櫃檯買賣中心官方公告為準。投資人操作請審慎評估風險。
    </div>
</body>
</html>"""

    html_report_path = os.path.join(BASE_DIR, "disposition_listening.html")
    try:
        with open(html_report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        log_success(f"成功產出獨立 HTML 預測看板: {html_report_path}")
    except Exception as e:
        log_error(f"寫入 HTML 報告失敗: {e}")
        
    print(f"{C_BOLD}{C_GREEN}=========================================================={C_RESET}")
    print(f"{C_BOLD}{C_GREEN}聽牌預測模組執行完畢！{C_RESET}")
    print(f"{C_BOLD}{C_GREEN}=========================================================={C_RESET}")

if __name__ == "__main__":
    main()
