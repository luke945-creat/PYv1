# -*- coding: utf-8 -*-
import os
import sys
import json
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

import re
import datetime

# 定義目錄
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(SCRIPT_DIR, "db")
CACHE_FILE = os.path.join(DB_DIR, "dashboard_data.json")

# 色彩配置 (Sleek Dark Theme)
BG_MAIN = "#121212"       # 主背景 (深黑)
BG_PANEL = "#1E1E1E"      # 面板背景 (暗灰)
BG_SELECT = "#00D2FF"     # 選取背景 (亮青)
FG_PRIMARY = "#FFFFFF"    # 主要文字 (白)
FG_SECONDARY = "#B0B0B0"  # 次要文字 (灰)
FG_ACCENT_CYAN = "#00D2FF"# 青色
FG_ACCENT_MAGENTA = "#D800FF" # 洋紅
COLOR_GREEN = "#00FF66"   # 霓虹綠
COLOR_RED = "#FF3366"     # 霓虹紅
COLOR_YELLOW = "#FFD700"  # 金黃
BG_RED_LIGHT = "#3A1A22"  # 極易觸發背景 (淡紅)
BG_YELLOW_LIGHT = "#353018" # 重點監控背景 (淡黃)

def parse_roc_date_to_datetime(date_str):
    m = re.match(r"^(\d{2,3})[/\.\-](\d{2})[/\.\-](\d{2})$", date_str)
    if m:
        yr = int(m.group(1))
        if yr < 100: yr += 100
        return datetime.date(yr + 1911, int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{2,3})(\d{2})(\d{2})$", date_str)
    if m:
        yr = int(m.group(1))
        if yr < 100: yr += 100
        return datetime.date(yr + 1911, int(m.group(2)), int(m.group(3)))
    return None

def get_disposition_status(period_str):
    if not period_str:
        return "🔒 處置中", "disposed"
    
    dates = re.findall(r"(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})", period_str)
    if len(dates) >= 2:
        start_raw = dates[0][0] if dates[0][0] else dates[0][1]
        end_raw = dates[1][0] if dates[1][0] else dates[1][1]
        
        start_date = parse_roc_date_to_datetime(start_raw)
        end_date = parse_roc_date_to_datetime(end_raw)
        
        if start_date and end_date:
            today = datetime.date.today()
            if today < start_date:
                return "⏳ 即將處置", "upcoming_disposed"
            diff_days = (end_date - today).days
            if 0 <= diff_days <= 1:
                return "🔓 即將解禁", "release"
            return "🔒 處置中", "disposed"
            
    return "🔒 處置中", "disposed"

class StockDashboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("台灣股市連續注意股 & 處置預警盤中即時監控系統")
        self.root.geometry("1100x680")
        self.root.configure(bg=BG_MAIN)
        
        # 設置字體與樣式
        self.default_font = ("微軟正黑體", 10)
        self.header_font = ("微軟正黑體", 11, "bold")
        self.title_font = ("微軟正黑體", 16, "bold")
        self.detail_font = ("Consolas", 10)
        self.detail_bold_font = ("微軟正黑體", 11, "bold")
        
        # 資料集
        self.all_stocks = []
        self.filtered_stocks = []
        
        self.setup_styles()
        self.create_widgets()
        
        # 載入初次資料
        self.load_data()
        
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 全局背景與元件樣式設定
        self.style.configure(".", bg=BG_MAIN, foreground=FG_PRIMARY, font=self.default_font)
        
        # TFrame 樣式
        self.style.configure("TFrame", background=BG_MAIN)
        self.style.configure("Panel.TFrame", background=BG_PANEL)
        
        # TButton 樣式
        self.style.configure("TButton", background="#333333", foreground=FG_PRIMARY, borderwidth=0, focuscolor="")
        self.style.map("TButton", 
                       background=[("active", "#444444"), ("disabled", "#222222")],
                       foreground=[("active", "#FFFFFF"), ("disabled", "#888888")])
        
        # TCombobox 樣式
        self.style.configure("TCombobox", fieldbackground="#2A2A2A", background="#333333", foreground=FG_PRIMARY)
        self.style.map("TCombobox", fieldbackground=[("readonly", "#2A2A2A")], foreground=[("readonly", FG_PRIMARY)])
        
        # Treeview 樣式
        self.style.configure("Treeview", 
                             background=BG_PANEL, 
                             foreground=FG_PRIMARY, 
                             fieldbackground=BG_PANEL, 
                             rowheight=26,
                             borderwidth=0)
        self.style.configure("Treeview.Heading", 
                             background="#2A2A2A", 
                             foreground=FG_PRIMARY, 
                             borderwidth=0, 
                             font=self.header_font)
        self.style.map("Treeview", 
                       background=[("selected", BG_SELECT)], 
                       foreground=[("selected", "#000000")])
        
    def create_widgets(self):
        # 頂部標題與控制欄
        top_frame = ttk.Frame(self.root, style="TFrame")
        top_frame.pack(fill=tk.X, padx=15, pady=10)
        
        title_label = tk.Label(top_frame, text="📈 台灣股市注意股 & 處置預警即時監控系統", 
                               font=self.title_font, bg=BG_MAIN, fg=FG_ACCENT_CYAN)
        title_label.pack(side=tk.LEFT)
        
        # 控制按鈕與過濾器
        ctrl_frame = ttk.Frame(top_frame, style="TFrame")
        ctrl_frame.pack(side=tk.RIGHT)
        
        # 搜尋輸入框
        tk.Label(ctrl_frame, text="搜尋代號/名稱:", bg=BG_MAIN, fg=FG_SECONDARY).pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filters())
        self.search_entry = tk.Entry(ctrl_frame, textvariable=self.search_var, bg="#2A2A2A", fg=FG_PRIMARY,
                                     insertbackground=FG_PRIMARY, borderwidth=1, relief=tk.FLAT, width=15, font=self.default_font)
        self.search_entry.pack(side=tk.LEFT, padx=5, ipady=2)
        
        # 市場篩選
        tk.Label(ctrl_frame, text="市場:", bg=BG_MAIN, fg=FG_SECONDARY).pack(side=tk.LEFT, padx=5)
        self.market_var = tk.StringVar(value="全部")
        self.market_combo = ttk.Combobox(ctrl_frame, textvariable=self.market_var, values=["全部", "上市", "上櫃"], 
                                         state="readonly", width=6)
        self.market_combo.pack(side=tk.LEFT, padx=5)
        self.market_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        
        # 重新整理按鈕
        self.refresh_btn = ttk.Button(ctrl_frame, text="🔄 刷新最新數據", command=self.async_refresh, width=15)
        self.refresh_btn.pack(side=tk.LEFT, padx=10)
        
        # 頂部數據統計面板
        stats_frame = ttk.Frame(self.root, style="Panel.TFrame")
        stats_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # 使用 grid 排版 3 個統計卡片
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)
        stats_frame.columnconfigure(2, weight=1)
        
        self.lbl_stat_notice = tk.Label(stats_frame, text="⚠️ 隔日處置預警個股: -- 檔", bg=BG_PANEL, fg=FG_ACCENT_CYAN, font=self.header_font, pady=8)
        self.lbl_stat_notice.grid(row=0, column=0, sticky="nsew")
        
        self.lbl_stat_warn = tk.Label(stats_frame, text="💥 重點/極易監控個股: -- 檔", bg=BG_PANEL, fg=COLOR_YELLOW, font=self.header_font, pady=8)
        self.lbl_stat_warn.grid(row=0, column=1, sticky="nsew")
        
        self.lbl_stat_disposed = tk.Label(stats_frame, text="🔒 處置及即將處置股: -- 檔", bg=BG_PANEL, fg="#E066FF", font=self.header_font, pady=8)
        self.lbl_stat_disposed.grid(row=0, column=2, sticky="nsew")

        # 主分隔區域 (左側列表，右側明細)
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # === 左側表格區域 ===
        left_frame = ttk.Frame(main_pane, style="TFrame")
        main_pane.add(left_frame, weight=3)
        
        # 左側垂直分割面板 (上為預警股，下為處置股)
        left_pane = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
        left_pane.pack(fill=tk.BOTH, expand=True)
        
        # --- 上半部：預警股區塊 ---
        warn_container = ttk.Frame(left_pane, style="TFrame")
        left_pane.add(warn_container, weight=3)
        
        warn_title_lbl = tk.Label(warn_container, text="⚠️ 隔日處置預警有價證券 (連續注意股)", font=self.header_font, bg=BG_MAIN, fg=FG_ACCENT_CYAN, anchor=tk.W)
        warn_title_lbl.pack(fill=tk.X, pady=(0, 2))
        
        cols_warn = ("code", "name", "market", "close", "volume", "trigger", "status")
        self.tree_warning = ttk.Treeview(warn_container, columns=cols_warn, show="headings", selectmode="browse")
        
        self.tree_warning.heading("code", text="證券代號", anchor=tk.W)
        self.tree_warning.heading("name", text="證券名稱", anchor=tk.W)
        self.tree_warning.heading("market", text="市場", anchor=tk.CENTER)
        self.tree_warning.heading("close", text="今日收盤", anchor=tk.E)
        self.tree_warning.heading("volume", text="今日成交量", anchor=tk.E)
        self.tree_warning.heading("trigger", text="明日觸發價", anchor=tk.E)
        self.tree_warning.heading("status", text="預警狀態", anchor=tk.CENTER)
        
        self.tree_warning.column("code", width=70, minwidth=60)
        self.tree_warning.column("name", width=80, minwidth=75)
        self.tree_warning.column("market", width=45, minwidth=40, anchor=tk.CENTER)
        self.tree_warning.column("close", width=75, minwidth=65, anchor=tk.E)
        self.tree_warning.column("volume", width=80, minwidth=70, anchor=tk.E)
        self.tree_warning.column("trigger", width=145, minwidth=130, anchor=tk.E)
        self.tree_warning.column("status", width=80, minwidth=70, anchor=tk.CENTER)
        
        vsb_warn = ttk.Scrollbar(warn_container, orient=tk.VERTICAL, command=self.tree_warning.yview)
        self.tree_warning.configure(yscrollcommand=vsb_warn.set)
        
        self.tree_warning.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb_warn.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree_warning.bind("<<TreeviewSelect>>", self.on_warning_select)
        
        # --- 下半部：處置股區塊 ---
        disp_container = ttk.Frame(left_pane, style="TFrame")
        left_pane.add(disp_container, weight=2)
        
        disp_title_lbl = tk.Label(disp_container, text="🔒 當前處置及即將處置有價證券 (處置股名單)", font=self.header_font, bg=BG_MAIN, fg="#E066FF", anchor=tk.W)
        disp_title_lbl.pack(fill=tk.X, pady=(5, 2))
        
        cols_disp = ("code", "name", "market", "close", "period", "status")
        self.tree_disposed = ttk.Treeview(disp_container, columns=cols_disp, show="headings", selectmode="browse")
        
        self.tree_disposed.heading("code", text="證券代號", anchor=tk.W)
        self.tree_disposed.heading("name", text="證券名稱", anchor=tk.W)
        self.tree_disposed.heading("market", text="市場", anchor=tk.CENTER)
        self.tree_disposed.heading("close", text="今日收盤", anchor=tk.E)
        self.tree_disposed.heading("period", text="處置期間", anchor=tk.W)
        self.tree_disposed.heading("status", text="處置狀態", anchor=tk.CENTER)
        
        self.tree_disposed.column("code", width=70, minwidth=60)
        self.tree_disposed.column("name", width=80, minwidth=75)
        self.tree_disposed.column("market", width=45, minwidth=40, anchor=tk.CENTER)
        self.tree_disposed.column("close", width=75, minwidth=65, anchor=tk.E)
        self.tree_disposed.column("period", width=175, minwidth=150, anchor=tk.W)
        self.tree_disposed.column("status", width=85, minwidth=75, anchor=tk.CENTER)
        
        vsb_disp = ttk.Scrollbar(disp_container, orient=tk.VERTICAL, command=self.tree_disposed.yview)
        self.tree_disposed.configure(yscrollcommand=vsb_disp.set)
        
        self.tree_disposed.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb_disp.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree_disposed.bind("<<TreeviewSelect>>", self.on_disposed_select)
        
        # 設定兩張表格之標籤背景色
        for tree in (self.tree_warning, self.tree_disposed):
            tree.tag_configure("guaranteed", background="#4A0E17", foreground="#FF3333")
            tree.tag_configure("extreme", background=BG_RED_LIGHT, foreground=COLOR_RED)
            tree.tag_configure("warn", background=BG_YELLOW_LIGHT, foreground=COLOR_YELLOW)
            tree.tag_configure("normal", background=BG_PANEL, foreground=FG_PRIMARY)
            tree.tag_configure("disposed", background="#2A1535", foreground="#E066FF")
            tree.tag_configure("release", background="#10301B", foreground="#00FF66")
            tree.tag_configure("upcoming_disposed", background="#352010", foreground="#FF9900")
        
        # === 右側詳細面板 ===
        right_frame = ttk.Frame(main_pane, style="Panel.TFrame")
        main_pane.add(right_frame, weight=2)
        
        # 個股詳細資訊面板配置
        self.detail_text = tk.Text(right_frame, bg=BG_PANEL, fg=FG_PRIMARY, borderwidth=0, 
                                   padx=15, pady=15, wrap=tk.WORD, font=self.detail_font)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        
        # 設定詳細資訊文字標籤顏色
        self.detail_text.tag_configure("title", font=("微軟正黑體", 14, "bold"), foreground=FG_ACCENT_CYAN)
        self.detail_text.tag_configure("h2", font=self.detail_bold_font, foreground=COLOR_YELLOW)
        self.detail_text.tag_configure("subtitle", font=self.default_font, foreground=FG_SECONDARY)
        self.detail_text.tag_configure("label", font=self.default_font, foreground=FG_SECONDARY)
        self.detail_text.tag_configure("rule", font=self.detail_bold_font, foreground=FG_ACCENT_CYAN)
        self.detail_text.tag_configure("up", font=self.detail_bold_font, foreground=COLOR_GREEN)
        self.detail_text.tag_configure("down", font=self.detail_bold_font, foreground=COLOR_RED)
        self.detail_text.tag_configure("vol", font=self.detail_bold_font, foreground=FG_ACCENT_MAGENTA)
        self.detail_text.tag_configure("bold", font=self.header_font)
        
        # 底部狀態列
        self.status_bar = tk.Label(self.root, text="就緒", bg=BG_PANEL, fg=FG_SECONDARY, 
                                   anchor=tk.W, padx=15, pady=4)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
    def load_data(self):
        if not os.path.exists(CACHE_FILE):
            self.status_bar.configure(text="找不到 dashboard_data.json 預警數據，請點選刷新數據按鈕進行初次分析。")
            self.detail_text.insert(tk.END, "⚠️ 尚未有預警數據\n\n請點擊頂部「🔄 刷新最新數據」按鈕，系統會啟動證交所與櫃買中心 API 爬蟲進行數據分析與門檻試算。\n\n分析完成後，結果將會顯示在此處。", "subtitle")
            self.detail_text.configure(state=tk.DISABLED)
            return
            
        try:
            with open(CACHE_FILE, "r", encoding="utf-8-sig") as f:
                self.all_stocks = json.load(f)
                
            self.status_bar.configure(text=f"資料載入完成。共有 {len(self.all_stocks)} 檔連續注意及處置個股。")
            self.apply_filters()
            
            # 預設選擇預警表格第一檔
            if self.tree_warning.get_children():
                first_item = self.tree_warning.get_children()[0]
                self.tree_warning.selection_set(first_item)
            elif self.tree_disposed.get_children():
                first_item = self.tree_disposed.get_children()[0]
                self.tree_disposed.selection_set(first_item)
                
        except Exception as e:
            messagebox.showerror("載入失敗", f"讀取數據檔案時發生異常: {str(e)}")
            self.status_bar.configure(text="資料庫讀取異常。")
            
    def apply_filters(self):
        search_query = self.search_var.get().strip().upper()
        market_query = self.market_var.get()
        
        # 清空列表
        for item in self.tree_warning.get_children():
            self.tree_warning.delete(item)
        for item in self.tree_disposed.get_children():
            self.tree_disposed.delete(item)
            
        self.filtered_warning_stocks = []
        self.filtered_disposed_stocks = []
        
        for stock in self.all_stocks:
            code = stock.get("Code", "")
            name = stock.get("Name", "")
            market = stock.get("Market", "")
            
            if search_query and (search_query not in code.upper() and search_query not in name.upper()):
                continue
            if market_query != "全部" and market != market_query:
                continue
                
            is_disposed = stock.get("IsDisposed", False)
            disposed_period = stock.get("DisposedPeriod", "")
            
            close_val = stock.get("Close", "N/A")
            try:
                close_str = f"{float(close_val.replace(',', '')):.2f} 元"
            except:
                close_str = f"{close_val} 元"
                
            if is_disposed:
                self.filtered_disposed_stocks.append(stock)
                status_text, tag = get_disposition_status(disposed_period)
                self.tree_disposed.insert("", tk.END, values=(code, name, market, close_str, disposed_period, status_text), tags=(tag,))
            else:
                self.filtered_warning_stocks.append(stock)
                
                # 尋找明日可能觸發的價格門檻 (限制在 ±10% 漲跌停限制內)
                min_abs_change = 9999.0
                has_guaranteed_trigger = False
                calcs = stock.get("Calculations", [])
                for calc in calcs:
                    up_chg = calc.get("TargetUpChange")
                    down_chg = calc.get("TargetDownChange")
                    is_primary = calc.get("IsPrimary", False)
                    if up_chg is not None:
                        if -10.0 <= up_chg <= 10.0:
                            val = 0.0 if (up_chg <= 0 and is_primary) else abs(up_chg)
                            min_abs_change = min(min_abs_change, val)
                        elif up_chg < -10.0 and is_primary:
                            has_guaranteed_trigger = True
                            min_abs_change = 0.0
                    if down_chg is not None:
                        if -10.0 <= down_chg <= 10.0:
                            val = 0.0 if (down_chg >= 0 and is_primary) else abs(down_chg)
                            min_abs_change = min(min_abs_change, val)
                        elif down_chg > 10.0 and is_primary:
                            has_guaranteed_trigger = True
                            min_abs_change = 0.0
                
                tag = "normal"
                status_text = "正常"
                if has_guaranteed_trigger:
                    status_text = "🚨 必定觸發"
                    tag = "guaranteed"
                elif min_abs_change <= 1.0:
                    status_text = "💥 極易觸發"
                    tag = "extreme"
                elif min_abs_change <= 5.0:
                    status_text = "⚠️ 重點監控"
                    tag = "warn"
                
                vol_lots = "N/A"
                try:
                    cache_path = os.path.join(DB_DIR, "prices_cache.json")
                    if os.path.exists(cache_path):
                        with open(cache_path, "r", encoding="utf-8-sig") as cache_f:
                            prices_cache = json.load(cache_f)
                            if code in prices_cache:
                                prices = prices_cache[code].get("prices", [])
                                if prices:
                                    last_vol = prices[-1].get("Volume", 0)
                                    vol_lots = f"{int(round(last_vol / 1000)):,} 張"
                except:
                    pass
                    
                # 決定明日最容易觸發的價格與說明
                trigger_price_str = "無價格觸發"
                primary_calc = None
                for calc in calcs:
                    if calc.get("IsPrimary", False):
                        primary_calc = calc
                        break
                if not primary_calc and calcs:
                    primary_calc = calcs[0]
                
                if primary_calc:
                    up_p = primary_calc.get("TargetUpPrice")
                    up_chg = primary_calc.get("TargetUpChange")
                    down_p = primary_calc.get("TargetDownPrice")
                    down_chg = primary_calc.get("TargetDownChange")
                    
                    use_up = True
                    if up_chg is not None and down_chg is not None:
                        eff_up = 0.0 if up_chg <= 0 else abs(up_chg)
                        eff_down = 0.0 if down_chg >= 0 else abs(down_chg)
                        if eff_down < eff_up:
                            use_up = False
                    elif up_chg is None and down_chg is not None:
                        use_up = False
                        
                    if use_up and up_p is not None and up_chg is not None:
                        if up_chg <= 0:
                            trigger_price_str = f"已達標 (不跌破 {up_p:.2f})"
                        elif up_chg <= 10.0:
                            trigger_price_str = f"{up_p:.2f} 元 ({up_chg:+.2f}%)"
                    elif not use_up and down_p is not None and down_chg is not None:
                        if down_chg >= 0:
                            trigger_price_str = f"已達標 (不漲破 {down_p:.2f})"
                        elif down_chg >= -10.0:
                            trigger_price_str = f"{down_p:.2f} 元 ({down_chg:+.2f}%)"
                            
                # 插入樹狀表
                self.tree_warning.insert("", tk.END, values=(code, name, market, close_str, vol_lots, trigger_price_str, status_text), tags=(tag,))
            
        # 更新頂部數據統計面板
        num_warning = len(self.filtered_warning_stocks)
        num_disposed = len(self.filtered_disposed_stocks)
        
        # 計算極易觸發/重點監控的數量
        num_extreme_warn = 0
        for stock in self.filtered_warning_stocks:
            min_abs_change = 9999.0
            has_guaranteed_trigger = False
            for calc in stock.get("Calculations", []):
                up_chg = calc.get("TargetUpChange")
                down_chg = calc.get("TargetDownChange")
                is_primary = calc.get("IsPrimary", False)
                if up_chg is not None:
                    if -10.0 <= up_chg <= 10.0:
                        val = 0.0 if (up_chg <= 0 and is_primary) else abs(up_chg)
                        min_abs_change = min(min_abs_change, val)
                    elif up_chg < -10.0 and is_primary:
                        has_guaranteed_trigger = True
                        min_abs_change = 0.0
                if down_chg is not None:
                    if -10.0 <= down_chg <= 10.0:
                        val = 0.0 if (down_chg >= 0 and is_primary) else abs(down_chg)
                        min_abs_change = min(min_abs_change, val)
                    elif down_chg > 10.0 and is_primary:
                        has_guaranteed_trigger = True
                        min_abs_change = 0.0
            if has_guaranteed_trigger or min_abs_change <= 5.0:
                num_extreme_warn += 1
                
        self.lbl_stat_notice.configure(text=f"⚠️ 隔日處置預警個股: {num_warning} 檔")
        self.lbl_stat_warn.configure(text=f"💥 重點/極易監控個股: {num_extreme_warn} 檔")
        self.lbl_stat_disposed.configure(text=f"🔒 處置及即將處置股: {num_disposed} 檔")
            
    def on_warning_select(self, event):
        selected = self.tree_warning.selection()
        if not selected:
            return
        # 清除處置表格的選擇
        self.tree_disposed.selection_remove(self.tree_disposed.selection())
        
        # 獲取選中的索引
        item_idx = self.tree_warning.index(selected[0])
        if item_idx >= len(self.filtered_warning_stocks):
            return
            
        stock = self.filtered_warning_stocks[item_idx]
        self.render_detail(stock)
        
    def on_disposed_select(self, event):
        selected = self.tree_disposed.selection()
        if not selected:
            return
        # 清除預警表格的選擇
        self.tree_warning.selection_remove(self.tree_warning.selection())
        
        # 獲取選中的索引
        item_idx = self.tree_disposed.index(selected[0])
        if item_idx >= len(self.filtered_disposed_stocks):
            return
            
        stock = self.filtered_disposed_stocks[item_idx]
        self.render_detail(stock)
        
    def render_detail(self, stock):
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        
        code = stock.get("Code", "")
        name = stock.get("Name", "")
        market = stock.get("Market", "")
        close = stock.get("Close", "")
        reason = stock.get("Reason", "")
        
        is_disposed = stock.get("IsDisposed", False)
        if is_disposed:
            self.detail_text.insert(tk.END, f"📊 [{code}] {name} ({market})\n", "title")
            try:
                close_f = float(close.replace(',', ''))
                self.detail_text.insert(tk.END, f"今日收盤價: {close_f:.2f} 元\n", "bold")
            except:
                self.detail_text.insert(tk.END, f"今日收盤價: {close} 元\n", "bold")
                
            self.detail_text.insert(tk.END, "---------------------------------------------\n", "label")
            
            disposed_period = stock.get("DisposedPeriod", "")
            status_text, tag = get_disposition_status(disposed_period)
            
            # 依據狀態決定標籤顏色
            status_tag = "rule"
            if tag == "release":
                status_tag = "up"
            elif tag == "upcoming_disposed":
                status_tag = "h2"
                
            self.detail_text.insert(tk.END, f"🔒 處置狀態：{status_text}\n", status_tag)
            self.detail_text.insert(tk.END, f"處置期間：{disposed_period}\n", "bold")
            
            # 計算剩餘天數等資訊
            dates = re.findall(r"(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})", disposed_period)
            if len(dates) >= 2:
                start_raw = dates[0][0] if dates[0][0] else dates[0][1]
                end_raw = dates[1][0] if dates[1][0] else dates[1][1]
                start_date = parse_roc_date_to_datetime(start_raw)
                end_date = parse_roc_date_to_datetime(end_raw)
                if start_date and end_date:
                    today = datetime.date.today()
                    if today < start_date:
                        days_until = (start_date - today).days
                        self.detail_text.insert(tk.END, f"  ● 距離處置開始還有 {days_until} 天\n", "h2")
                    elif today <= end_date:
                        days_left = (end_date - today).days
                        self.detail_text.insert(tk.END, f"  ● 處置執行中，距離解禁還有 {days_left} 天\n", "down")
                        if days_left <= 1:
                            self.detail_text.insert(tk.END, "  ● 📢 提醒：此有價證券即將於近日解禁，請密切關注市場波動！\n", "up")
            
            self.detail_text.insert(tk.END, "---------------------------------------------\n", "label")
            self.detail_text.insert(tk.END, "📢 處置公告與措施細節:\n", "bold")
            clean_reason = reason.replace("<[^>]*>", "").replace("﹝", "[").replace("﹞", "]")
            self.detail_text.insert(tk.END, f"{clean_reason}\n\n", "subtitle")
            self.detail_text.configure(state=tk.DISABLED)
            return

        # 標題
        self.detail_text.insert(tk.END, f"📊 [{code}] {name} ({market})\n", "title")
        self.detail_text.insert(tk.END, f"今日收盤價: {close} 元\n", "bold")
        
        # 今日成交量
        vol_str = "N/A"
        try:
            cache_path = os.path.join(DB_DIR, "prices_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8-sig") as cache_f:
                    prices_cache = json.load(cache_f)
                    if code in prices_cache:
                        prices = prices_cache[code].get("prices", [])
                        if prices:
                            last_vol = prices[-1].get("Volume", 0)
                            vol_str = f"{int(last_vol):,} 股 ({int(round(last_vol/1000)):,} 張)"
        except:
            pass
        self.detail_text.insert(tk.END, f"今日成交量: {vol_str}\n", "subtitle")
        self.detail_text.insert(tk.END, "---------------------------------------------\n", "label")
        
        # 明日處置預警簡化結論
        self.detail_text.insert(tk.END, "💡 明日觸發簡化結論 (處置預警)\n", "title")
        
        # 價格結論
        possible_prices = []
        calcs = stock.get("Calculations", [])
        for calc in calcs:
            up_p = calc.get("TargetUpPrice", 0.0)
            up_chg = calc.get("TargetUpChange")
            down_p = calc.get("TargetDownPrice")
            down_chg = calc.get("TargetDownChange")
            rule = calc.get("Rule", "")
            
            if up_chg is not None and -10.0 <= up_chg <= 10.0:
                possible_prices.append((up_p, up_chg, "up", rule))
            if down_p is not None and down_chg is not None and -10.0 <= down_chg <= 10.0:
                possible_prices.append((down_p, down_chg, "down", rule))
                
        if possible_prices:
            possible_prices.sort(key=lambda x: abs(x[1]))
            for idx, (p, chg, t, r) in enumerate(possible_prices):
                if t == "up":
                    if chg <= 0:
                        desc = f"  ● 收盤高於 {p:.2f} 元 (不跌破即觸發)"
                    else:
                        desc = f"  ● 收盤高於 {p:.2f} 元 (需上漲 +{chg:.2f}%)"
                else:
                    if chg >= 0:
                        desc = f"  ● 收盤低於 {p:.2f} 元 (不漲破即觸發)"
                    else:
                        desc = f"  ● 收盤低於 {p:.2f} 元 (需下跌 {chg:.2f}%)"
                
                tag_name = "up" if t == "up" else "down"
                if abs(chg) <= 1.0:
                    highlight = " [💥 極易觸發]"
                elif abs(chg) <= 5.0:
                    highlight = " [⚠️ 重點監控]"
                else:
                    highlight = ""
                
                self.detail_text.insert(tk.END, f"{desc}{highlight}\n", tag_name)
                self.detail_text.insert(tk.END, f"    (依據: {r})\n", "label")
        else:
            self.detail_text.insert(tk.END, "  🛡️ 明日在漲跌停限制內 (±10%) 無任何價格會觸發注意。\n", "up")
            
        # 成交量結論
        v_calcs = stock.get("VolumeCalculations", [])
        if v_calcs:
            for v_calc in v_calcs:
                v_rule = v_calc.get("Rule", "")
                v_trig = v_calc.get("TriggerVolume", 0)
                if v_trig <= 0:
                    self.detail_text.insert(tk.END, f"  ● 任意成交量皆會觸發 (今日已達標)\n", "vol")
                else:
                    trig_lots = int(round(v_trig / 1000))
                    self.detail_text.insert(tk.END, f"  ● 明日成交量達 {trig_lots:,} 張 以上即觸發\n", "vol")
                self.detail_text.insert(tk.END, f"    (依據: {v_rule})\n", "label")
        else:
            avg_vol_60 = 0.0
            try:
                cache_path = os.path.join(DB_DIR, "prices_cache.json")
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8-sig") as cache_f:
                        prices_cache = json.load(cache_f)
                        if code in prices_cache:
                            prices = prices_cache[code].get("prices", [])
                            if len(prices) >= 60:
                                last_60 = prices[-60:]
                                avg_vol_60 = sum([p.get("Volume", 0) for p in last_60]) / 60
            except:
                pass
            if avg_vol_60 > 0:
                trig_60 = avg_vol_60 * 5.0
                trig_lots = int(round(trig_60 / 1000))
                self.detail_text.insert(tk.END, f"  ● 明日成交量達 {trig_lots:,} 張 以上即觸發\n", "vol")
                self.detail_text.insert(tk.END, f"    (依據: 60日均量放大 5.0 倍)\n", "label")
            else:
                self.detail_text.insert(tk.END, "  ❔ 無成交量推算數據 (歷史價格天數不足)\n", "label")
                
        self.detail_text.insert(tk.END, "---------------------------------------------\n", "label")
        
        # 今日公告注意原因
        clean_reason = reason.replace("<[^>]*>", "").replace("﹝", "[").replace("﹞", "]")
        self.detail_text.insert(tk.END, "📢 今日公告注意原因:\n", "bold")
        self.detail_text.insert(tk.END, f"{clean_reason}\n\n", "subtitle")
        self.detail_text.insert(tk.END, "---------------------------------------------\n", "label")
        
        # 明日價格門檻
        self.detail_text.insert(tk.END, "🎯 明日價格注意門檻 (收盤價預估):\n", "h2")
        calcs = stock.get("Calculations", [])
        if calcs:
            for calc in calcs:
                rule = calc.get("Rule", "")
                base = calc.get("BasePrice", 0)
                up_p = calc.get("TargetUpPrice", 0)
                up_chg = calc.get("TargetUpChange", 0)
                down_p = calc.get("TargetDownPrice")
                down_chg = calc.get("TargetDownChange")
                is_primary = calc.get("IsPrimary", False)
                
                rule_prefix = "⭐ " if is_primary else "  "
                self.detail_text.insert(tk.END, f"{rule_prefix}{rule}\n", "rule")
                self.detail_text.insert(tk.END, f"   (基準價: {base:.2f} 元)\n", "label")
                
                # 看漲
                up_note = ""
                if up_chg > 10.0:
                    up_note = " [超明日漲停限制 +10%]"
                elif 0 < up_chg <= 5.0:
                    up_note = " [🔥 極易觸發！]"
                self.detail_text.insert(tk.END, f"   ▲ 看漲觸發價: {up_p:.2f} 元 (漲幅需求: {up_chg:.2f}%){up_note}\n", "up")
                
                # 看跌
                if down_p is not None and down_chg is not None:
                    down_note = ""
                    if down_chg < -10.0:
                        down_note = " [超明日跌停限制 -10%]"
                    self.detail_text.insert(tk.END, f"   ▼ 看跌觸發價: {down_p:.2f} 元 (跌幅需求: {down_chg:.2f}%){down_note}\n", "down")
                self.detail_text.insert(tk.END, "\n")
        else:
            self.detail_text.insert(tk.END, "  無價格推算數據\n\n", "label")
            
        # 明日成交量門檻
        self.detail_text.insert(tk.END, "⚡ 明日成交量注意門檻 (成交張數預估):\n", "h2")
        v_calcs = stock.get("VolumeCalculations", [])
        if v_calcs:
            for v_calc in v_calcs:
                v_rule = v_calc.get("Rule", "")
                v_trig = v_calc.get("TriggerVolume", 0)
                
                self.detail_text.insert(tk.END, f"  ● {v_rule}:\n", "rule")
                if v_trig <= 0:
                    self.detail_text.insert(tk.END, "    👉 門檻: 明日任意成交量皆會觸發！(今日累積已提前達標)\n", "vol")
                else:
                    trig_lots = int(round(v_trig / 1000))
                    self.detail_text.insert(tk.END, f"    👉 觸發張數: {trig_lots:,} 張 ({int(v_trig):,} 股)\n", "vol")
                self.detail_text.insert(tk.END, "\n")
        else:
            # 60日均量 5 倍保底推算
            avg_vol_60 = 0
            # 嘗試計算 60 日均量
            try:
                cache_path = os.path.join(DB_DIR, "prices_cache.json")
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8-sig") as cache_f:
                        prices_cache = json.load(cache_f)
                        if code in prices_cache:
                            prices = prices_cache[code].get("prices", [])
                            if len(prices) >= 60:
                                last_60 = prices[-60:]
                                avg_vol_60 = sum([p.get("Volume", 0) for p in last_60]) / 60
            except:
                pass
                
            if avg_vol_60 > 0:
                trig_60 = avg_vol_60 * 5.0
                trig_lots = int(round(trig_60 / 1000))
                self.detail_text.insert(tk.END, "  ● 60日日平均成交量放大 5.0 倍門檻:\n", "rule")
                self.detail_text.insert(tk.END, f"    👉 觸發張數: {trig_lots:,} 張 ({int(trig_60):,} 股)\n\n", "vol")
            else:
                self.detail_text.insert(tk.END, "  無成交量推算數據 (歷史價格天數不足)\n\n", "label")
                
        self.detail_text.configure(state=tk.DISABLED)
        
    def async_refresh(self):
        # 禁用重新整理按鈕，防重複點選
        self.refresh_btn.configure(state=tk.DISABLED, text="正在更新數據...")
        self.status_bar.configure(text="正在啟動注意股數據重新整理 (這通常需要 10-15 秒，視網速而定)...")
        
        # 開啟背景執行緒執行爬蟲
        t = threading.Thread(target=self.refresh_thread)
        t.daemon = True
        t.start()
        
    def refresh_thread(self):
        try:
            # 執行 PowerShell 腳本
            ps_script = os.path.join(SCRIPT_DIR, "Get-AttentionStocks.ps1")
            
            # 使用 subprocess 靜默調用
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                startupinfo=startupinfo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            
            # 回到 GUI 執行緒更新 UI
            self.root.after(0, self.refresh_completed, process.returncode, process.stderr)
            
        except Exception as e:
            self.root.after(0, self.refresh_failed, str(e))
            
    def refresh_completed(self, returncode, stderr):
        self.refresh_btn.configure(state=tk.NORMAL, text="🔄 刷新最新數據")
        if returncode == 0:
            self.status_bar.configure(text="注意股預警數據已成功重新整理！")
            self.load_data()
            messagebox.showinfo("更新成功", "注意股與預警門檻數據已刷新成功！")
        else:
            self.status_bar.configure(text="更新失敗。請檢查日誌或手動執行 Get-AttentionStocks.ps1 排除錯誤。")
            messagebox.showerror("更新失敗", f"執行 PowerShell 數據爬蟲時發生錯誤:\n{stderr}")
            
    def refresh_failed(self, error_msg):
        self.refresh_btn.configure(state=tk.NORMAL, text="🔄 刷新最新數據")
        self.status_bar.configure(text=f"啟動更新發生例外: {error_msg}")
        messagebox.showerror("啟動失敗", f"無法執行背景更新執行緒: {error_msg}")

if __name__ == "__main__":
    # 解決 Windows 系統高 DPI 縮放字體模糊問題
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    root = tk.Tk()
    app = StockDashboardApp(root)
    root.mainloop()
