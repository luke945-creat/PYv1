# Get-AttentionStocks.ps1
# 台灣股市注意股分析系統

# 設定編碼，確保中文正常顯示
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 定義目錄
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ScriptDir)) { $ScriptDir = Get-Location }
$DbDir = Join-Path $ScriptDir "db"
$ReportsDir = Join-Path $ScriptDir "reports"
$CacheFile = Join-Path $DbDir "prices_cache.json"

# 初始化目錄
if (!(Test-Path $DbDir)) { New-Item -ItemType Directory -Path $DbDir -Force | Out-Null }
if (!(Test-Path $ReportsDir)) { New-Item -ItemType Directory -Path $ReportsDir -Force | Out-Null }

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "            台灣股市注意股追蹤與隔日處置預警分析系統" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "執行時間: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# ----------------- 輔助函式 -----------------

# 將民國日期轉換為西元日期 (格式: yyyy-MM-dd)
function Convert-RocDateToNormal($rocDate) {
    if ($rocDate -match "^(\d{3})\.(\d{2})\.(\d{2})$") {
        $year = [int]$Matches[1] + 1911
        return "$year-$($Matches[2])-$($Matches[3])"
    } elseif ($rocDate -match "^(\d{3})(\d{2})(\d{2})$") {
        $year = [int]$Matches[1] + 1911
        return "$year-$($Matches[2])-$($Matches[3])"
    }
    return $rocDate
}

# 格式化成交量為 張 (及股數)
function Format-Volume($vol) {
    if ($vol -le 0 -or $vol -eq $null) { return "N/A" }
    $lots = [Math]::Round($vol / 1000, 0)
    return "{0:N0} 張 ({1:N0} 股)" -f $lots, $vol
}

# 解析民國日期字串，支援 yyy/MM/dd, yyy.MM.dd, yyy-MM-dd, yyyMMdd 格式，回傳 DateTime 物件 (0毫秒)
function Parse-RocDateString($dateStr) {
    if ($dateStr -match "^(\d{2,3})[/\.\-](\d{2})[/\.\-](\d{2})$") {
        $yrVal = [int]($Matches[1])
        if ($yrVal -lt 100) { $yrVal += 100 }
        $year = $yrVal + 1911
        $month = [int]($Matches[2])
        $day = [int]($Matches[3])
        return New-Object DateTime($year, $month, $day, 0, 0, 0, 0)
    } elseif ($dateStr -match "^(\d{2,3})(\d{2})(\d{2})$") {
        $yrVal = [int]($Matches[1])
        if ($yrVal -lt 100) { $yrVal += 100 }
        $year = $yrVal + 1911
        $month = [int]($Matches[2])
        $day = [int]($Matches[3])
        return New-Object DateTime($year, $month, $day, 0, 0, 0, 0)
    }
    return $null
}

# 將價格對齊台灣股市升降單位 (Tick Size)
# 看漲 ($isUp = $true) 採無條件進位 (Ceiling) 對齊 Tick，看跌 ($isUp = $false) 採無條件捨去 (Floor) 對齊 Tick
function Round-ToTaiwanStockTick($price, $isUp) {
    if ($price -le 0 -or $price -eq $null) { return $price }
    
    $tick = 0.01
    if ($price -lt 10) {
        $tick = 0.01
    } elseif ($price -lt 50) {
        $tick = 0.05
    } elseif ($price -lt 100) {
        $tick = 0.1
    } elseif ($price -lt 500) {
        $tick = 0.5
    } elseif ($price -lt 1000) {
        $tick = 1.0
    } else {
        $tick = 5.0
    }
    
    $remainder = $price % $tick
    if ([Math]::Abs($remainder) -lt 0.0001) {
        return [Math]::Round($price, 2)
    }
    
    if ($isUp) {
        $rounded = $price - $remainder + $tick
    } else {
        $rounded = $price - $remainder
    }
    return [Math]::Round($rounded, 2)
}

# 從處置期間字串中提取開始與結束日期
function Get-DispositionDateRange($periodStr) {
    $matches = [regex]::Matches($periodStr, "(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})")
    if ($matches.Count -ge 2) {
        $startStr = $matches[0].Value
        $endStr = $matches[1].Value
        $startDate = Parse-RocDateString $startStr
        $endDate = Parse-RocDateString $endStr
        if ($startDate -and $endDate) {
            return @{ Start = $startDate; End = $endDate }
        }
    }
    return $null
}

# 獲取指定日期下所有處於處置期間的個股清單 (回傳雜湊表，鍵為代號，時間精準至0毫秒比對)
function Get-ActiveDispositionStocks($targetDate) {
    if ($null -eq $targetDate) {
        $dt = Get-Date
        $targetDate = New-Object DateTime($dt.Year, $dt.Month, $dt.Day, 0, 0, 0, 0)
    } else {
        if ($targetDate -is [string]) {
            $targetDate = [DateTime]::Parse($targetDate)
        }
        $targetDate = New-Object DateTime($targetDate.Year, $targetDate.Month, $targetDate.Day, 0, 0, 0, 0)
    }
    
    $disposedCodes = @{}
    
    # 1. 抓取上市處置股 (TWSE)
    Write-Host "正在從證交所獲取上市處置股名單..." -ForegroundColor Yellow
    try {
        $twseDisposUrl = "https://openapi.twse.com.tw/v1/announcement/punish"
        $tempTwseFile = Join-Path $DbDir "temp_twse_dispos.json"
        Invoke-WebRequest -Uri $twseDisposUrl -UserAgent "Mozilla/5.0" -OutFile $tempTwseFile -TimeoutSec 10 -UseBasicParsing
        if (Test-Path $tempTwseFile) {
            $respText = Get-Content -Path $tempTwseFile -Raw -Encoding UTF8
            Remove-Item $tempTwseFile -ErrorAction SilentlyContinue
            $twseDispos = ConvertFrom-Json $respText
            if ($twseDispos) {
                foreach ($item in $twseDispos) {
                    $code = $item.Code
                    if ($code) {
                        $period = $item.DispositionPeriod
                        $range = Get-DispositionDateRange $period
                        if ($range) {
                            if ($targetDate -le $range.End) {
                                $disposedCodes[$code] = @{
                                    Name = $item.Name
                                    Period = $period
                                    Start = $range.Start.ToString("yyyy-MM-dd")
                                    End = $range.End.ToString("yyyy-MM-dd")
                                    Market = "上市"
                                }
                            }
                        }
                    }
                }
            }
        }
    } catch {
        Write-Host "警告: 無法獲取上市處置股名單 ($($_.Exception.Message))" -ForegroundColor Yellow
    }
    
    # 2. 抓取上櫃處置股 (TPEx)
    Write-Host "正在從櫃買中心獲取上櫃處置股名單..." -ForegroundColor Yellow
    try {
        $tpexDisposUrl = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
        $tempTpexDisposFile = Join-Path $DbDir "temp_tpex_dispos.json"
        Invoke-WebRequest -Uri $tpexDisposUrl -UserAgent "Mozilla/5.0" -OutFile $tempTpexDisposFile -TimeoutSec 10 -UseBasicParsing
        if (Test-Path $tempTpexDisposFile) {
            $respText = Get-Content -Path $tempTpexDisposFile -Raw -Encoding UTF8
            Remove-Item $tempTpexDisposFile -ErrorAction SilentlyContinue
            $tpexDispos = ConvertFrom-Json $respText
            if ($tpexDispos) {
                foreach ($item in $tpexDispos) {
                    $code = $item.SecuritiesCompanyCode
                    if ($code) {
                        $period = $item.DispositionPeriod
                        $range = Get-DispositionDateRange $period
                        if ($range) {
                            if ($targetDate -le $range.End) {
                                $disposedCodes[$code] = @{
                                    Name = $item.CompanyName
                                    Period = $period
                                    Start = $range.Start.ToString("yyyy-MM-dd")
                                    End = $range.End.ToString("yyyy-MM-dd")
                                    Market = "上櫃"
                                }
                            }
                        }
                    }
                }
            }
        }
    } catch {
        Write-Host "警告: 無法獲取上櫃處置股名單 ($($_.Exception.Message))" -ForegroundColor Yellow
    }
    
    return $disposedCodes
}

# 載入快取
function Get-PricesCache {
    if (Test-Path $CacheFile) {
        try {
            $content = Get-Content $CacheFile -Raw -Encoding UTF8
            return ConvertFrom-Json $content
        } catch {
            return @{}
        }
    }
    return @{}
}

# 儲存快取
function Save-PricesCache($cache) {
    try {
        $json = ConvertTo-Json $cache -Depth 10
        Set-Content -Path $CacheFile -Value $json -Encoding UTF8 -Force
    } catch {
        Write-Host "警告: 無法寫入價格快取檔案。" -ForegroundColor Yellow
    }
}

# 備用手動同步提示說明
function Show-GitFallbackInstructions {
    Write-Host ""
    Write-Host "【手動更新 GitHub Pages 指南】" -ForegroundColor Yellow
    Write-Host "1. 開啟您的 GitHub 專案頁面 (例如: https://github.com/您的帳號/專案名稱)" -ForegroundColor White
    Write-Host "2. 點擊「Add file」->「Upload files」" -ForegroundColor White
    Write-Host "3. 將以下檔案拖放上傳到儲存庫中：" -ForegroundColor White
    Write-Host "   - db/dashboard_data.json" -ForegroundColor Green
    Write-Host "   - db/prices_cache.json (非必要，但上傳後網頁版能顯示今日成交張數)" -ForegroundColor Green
    Write-Host "   - index.html、index.css、dashboard.js (若有修改)" -ForegroundColor Green
    Write-Host "   - reports/ 目錄下的最新 Markdown 報告" -ForegroundColor Green
    Write-Host "4. 點擊「Commit changes」完成更新。" -ForegroundColor White
    Write-Host ""
    Write-Host "【自動化推薦】" -ForegroundColor Yellow
    Write-Host "建議安裝 Git (https://git-scm.com/) 並設定好遠端推送權限，" -ForegroundColor White
    Write-Host "本腳本即可在每次分析結束後自動為您推送到網頁版儀表板！" -ForegroundColor White
    Write-Host ""
}

# 將變更同步至 GitHub 儲存庫
function Sync-ToGitHub {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "                 正在執行 GitHub 同步檢查" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    
    # 自動偵測預設安裝路徑，若不在 PATH 中則加入
    if (!(Get-Command git -ErrorAction SilentlyContinue)) {
        $defaultGitPaths = @(
            "C:\Program Files\Git\cmd",
            "C:\Program Files (x86)\Git\cmd",
            "$env:LocalAppData\Programs\Git\cmd"
        )
        foreach ($gp in $defaultGitPaths) {
            if (Test-Path (Join-Path $gp "git.exe")) {
                $env:PATH += ";$gp"
                break
            }
        }
    }

    # 檢查 git 是否可用
    $gitExists = $false
    try {
        $gitVersion = git --version 2>&1
        if ($LASTEXITCODE -eq 0 -or $gitVersion -match "git version") {
            $gitExists = $true
        }
    } catch {
        # git 不存在或發生錯誤
    }
    
    if ($gitExists) {
        Write-Host "偵測到本機已安裝 Git，正在自動推送更新至 GitHub..." -ForegroundColor Green
        try {
            # 檢查是否為 git 專案
            $inWorkTree = git rev-parse --is-inside-work-tree 2>&1
            if ($LASTEXITCODE -ne 0 -or $inWorkTree -ne "true") {
                Write-Host "此目錄尚未初始化為 Git 儲存庫。請手動執行 git init 並設定 remote。" -ForegroundColor Yellow
                Show-GitFallbackInstructions
                return
            }
            
            # 加入更新檔案
            Write-Host "-> 正在加入檔案至暫存區..." -ForegroundColor Gray
            git add db/dashboard_data.json db/prices_cache.json reports/ .gitignore index.html index.css dashboard.js
            
            # 提交變更
            $commitMsg = "Auto Update Stock Data: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
            Write-Host "-> 正在提交變更: $commitMsg" -ForegroundColor Gray
            git commit -m $commitMsg
            
            # 推送變更 (預設推送至 origin 的當前分支，或 main)
            # 獲取目前分支名稱
            $branch = git branch --show-current
            if ([string]::IsNullOrEmpty($branch)) { $branch = "main" }
            
            Write-Host "-> 正在推送到遠端倉庫 ($branch)..." -ForegroundColor Gray
            git push origin $branch
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "同步成功！資料已推送到 GitHub Pages。" -ForegroundColor Green
            } else {
                Write-Host "警告: Git 推送失敗，請確認網路連線或是否已設定遠端權限。" -ForegroundColor Red
                Show-GitFallbackInstructions
            }
        } catch {
            Write-Host "執行 Git 同步時發生錯誤: $($_.Exception.Message)" -ForegroundColor Red
            Show-GitFallbackInstructions
        }
    } else {
        Write-Host "未在系統中偵測到 Git 指令。" -ForegroundColor Yellow
        Show-GitFallbackInstructions
    }
    Write-Host "==========================================================" -ForegroundColor Cyan
}


# 獲取個股歷史收盤價與成交量
function Get-StockHistory($code, $isTpex) {
    $cache = Get-PricesCache
    $todayStr = (Get-Date).ToString("yyyy-MM-dd")
    
    # 檢查快取
    if ($cache.PSObject.Properties[$code] -ne $null) {
        $entry = $cache.$code
        # 如果快取日期是今天，且資料點數量足夠，則直接返回
        if ($entry.last_updated -eq $todayStr -and $entry.prices.Count -gt 90) {
            return $entry.prices
        }
    }
    
    Write-Host "正在獲取個股歷史價格與成交量: $code..." -ForegroundColor DarkGray
    $prices = @()
    
    # 1. 嘗試使用 Yahoo Finance Chart API
    $symbol = if ($isTpex) { "$code.TWO" } else { "$code.TW" }
    $yahooUrl = "https://query1.finance.yahoo.com/v8/finance/chart/$($symbol)?range=6mo&interval=1d"
    
    try {
        $res = Invoke-RestMethod -Uri $yahooUrl -UserAgent "Mozilla/5.0" -TimeoutSec 10
        if ($res -and $res.chart.result -and $res.chart.result[0].timestamp) {
            $timestamps = $res.chart.result[0].timestamp
            $closes = $res.chart.result[0].indicators.quote[0].close
            $volumes = $res.chart.result[0].indicators.quote[0].volume
            for ($i=0; $i -lt $timestamps.Count; $i++) {
                if ($closes[$i] -ne $null) {
                    $dateStr = [TimeZoneInfo]::ConvertTimeFromUtc((Get-Date "1970-01-01").AddSeconds($timestamps[$i]), [TimeZoneInfo]::Local).ToString("yyyy-MM-dd")
                    $volVal = if ($volumes[$i] -ne $null) { [double]$volumes[$i] } else { 0.0 }
                    $prices += [PSCustomObject]@{ Date = $dateStr; Close = [double]$closes[$i]; Volume = $volVal }
                }
            }
        }
    } catch {
        # Yahoo Finance 失敗，對上市股票嘗試使用證交所 STOCK_DAY API
    }
    
    # 2. 如果 Yahoo 沒資料，且為上市股票，則使用證交所 STOCK_DAY API
    if ($prices.Count -eq 0 -and !$isTpex) {
        Write-Host "Yahoo 無資料或被限制，嘗試從證交所 API 補件: $code..." -ForegroundColor DarkGray
        $months = @()
        for ($m = 0; $m -lt 5; $m++) {
            $months += (Get-Date).AddMonths(-$m).ToString("yyyyMM01")
        }
        
        foreach ($month in $months) {
            $twseDayUrl = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=$month&stockNo=$code"
            try {
                $monthRes = Invoke-RestMethod -Uri $twseDayUrl -UserAgent "Mozilla/5.0" -TimeoutSec 10
                if ($monthRes -and $monthRes.stat -eq "OK" -and $monthRes.data) {
                    foreach ($row in $monthRes.data) {
                        # 解析民國日期 115/06/01 -> 2026-06-01
                        if ($row[0] -match "^(\d+)/(\d+)/(\d+)$") {
                            $year = [int]$Matches[1] + 1911
                            $dateStr = "$year-$($Matches[2])-$($Matches[3])"
                            $closeStr = $row[6].Replace(",", "")
                            $volStr = $row[1].Replace(",", "")
                            $closeVal = 0.0
                            $volVal = 0.0
                            if ([double]::TryParse($closeStr, [ref]$closeVal) -and [double]::TryParse($volStr, [ref]$volVal)) {
                                $prices += [PSCustomObject]@{ Date = $dateStr; Close = $closeVal; Volume = $volVal }
                            }
                        }
                    }
                }
                Start-Sleep -Milliseconds 1200 # 延遲避免被封鎖
            } catch {
                Write-Host "證交所 API 獲取失敗: $month" -ForegroundColor DarkYellow
            }
        }
        # 排序
        $prices = $prices | Sort-Object Date
    }
    
    # 3. 儲存至快取並返回
    if ($prices.Count -gt 0) {
        if ($cache.PSObject.Properties[$code] -eq $null) {
            $cache | Add-Member -MemberType NoteProperty -Name $code -Value $null
        }
        $cache.$code = @{
            last_updated = $todayStr
            prices = $prices
        }
        Save-PricesCache $cache
        # 查詢完成後，給予 Yahoo/證交所 API 緩衝時間，防範 HTTP 429 封鎖
        Start-Sleep -Milliseconds 1000
        return $prices
    }
    
    # 失敗也給予延遲
    Start-Sleep -Milliseconds 1000
    return $null
}

# ----------------- 1. 抓取注意股 -----------------

Write-Host "正在從證券交易所 (TWSE) 獲取上市注意股資料..." -ForegroundColor Yellow
$startDate = (Get-Date).AddDays(-12).ToString("yyyyMMdd")
$endDate = (Get-Date).ToString("yyyyMMdd")
$twseUrl = "https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate=$startDate&endDate=$endDate&sortKind=STKNO"

try {
    $twseRes = Invoke-RestMethod -Uri $twseUrl -UserAgent "Mozilla/5.0" -TimeoutSec 15
    if ($twseRes -and $twseRes.data) {
        $twseList = @()
        foreach ($row in $twseRes.data) {
            $normDate = Convert-RocDateToNormal $row[5]
            $twseList += [PSCustomObject]@{
                Date = $normDate
                Code = $row[1]
                Name = $row[2]
                Reason = $row[4]
                Close = $row[6]
                PE = $row[7]
                Market = "上市"
            }
        }
    } else {
        Write-Host "錯誤: 證交所返回無效資料。" -ForegroundColor Red
        $twseList = @()
    }
} catch {
    Write-Host "錯誤: 無法連線至證交所 API。$($_.Exception.Message)" -ForegroundColor Red
    $twseList = @()
}

Write-Host "正在從櫃買中心 (TPEx) 獲取上櫃注意股資料..." -ForegroundColor Yellow
$tpexUrl = "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information"
$tempTpexFile = Join-Path $DbDir "temp_tpex.json"

try {
    # 使用 Basic Parsing 下載至本地檔案，徹底避開 .NET 字元編碼與 IE 引擎卡死問題
    Invoke-WebRequest -Uri $tpexUrl -UserAgent "Mozilla/5.0" -OutFile $tempTpexFile -TimeoutSec 15 -UseBasicParsing
    if (Test-Path $tempTpexFile) {
        $tpexText = Get-Content -Path $tempTpexFile -Raw -Encoding UTF8
        $tpexJson = ConvertFrom-Json $tpexText
        $tpexList = @()
        foreach ($row in $tpexJson) {
            $normDate = Convert-RocDateToNormal $row.Date
            $tpexList += [PSCustomObject]@{
                Date = $normDate
                Code = $row.SecuritiesCompanyCode
                Name = $row.CompanyName
                Reason = $row.TradingInformation
                Close = $row.ClosePrice
                PE = $row.PriceEarningRatio
                Market = "上櫃"
            }
        }
        Remove-Item $tempTpexFile -ErrorAction SilentlyContinue
    } else {
        Write-Host "錯誤: 櫃買中心返回無效資料。" -ForegroundColor Red
        $tpexList = @()
    }
} catch {
    Write-Host "錯誤: 無法連線至櫃買中心 API。$($_.Exception.Message)" -ForegroundColor Red
    $tpexList = @()
}

# 合併清單
$allList = $twseList + $tpexList

if ($allList.Count -eq 0) {
    Write-Host "未獲取到任何注意股資料，程式結束。" -ForegroundColor Red
    exit
}

# ----------------- 2. 篩選連續兩天注意股 -----------------

$tradingDates = $allList.Date | Select-Object -Unique | Sort-Object -Descending
if ($tradingDates.Count -lt 2) {
    Write-Host "資料日數不足 2 天，無法統計連續兩天注意股。" -ForegroundColor Yellow
    exit
}

$todayDate = $tradingDates[0]
$yesterdayDate = $tradingDates[1]

Write-Host ""
Write-Host "今日交易日: $todayDate (注意股數量: $(($allList | Where-Object { $_.Date -eq $todayDate }).Count))" -ForegroundColor Green
Write-Host "昨日交易日: $yesterdayDate (注意股數量: $(($allList | Where-Object { $_.Date -eq $yesterdayDate }).Count))" -ForegroundColor Green

# 篩選
$todayStocks = $allList | Where-Object { $_.Date -eq $todayDate }
$yesterdayStocks = $allList | Where-Object { $_.Date -eq $yesterdayDate }

# 獲取今日處置股名單，用於排除已處置個股
$disposedStocks = Get-ActiveDispositionStocks $todayDate

# 找出連續兩天注意股
$consecutiveStocks = @()
foreach ($ts in $todayStocks) {
    $ys = $yesterdayStocks | Where-Object { $_.Code -eq $ts.Code }
    if ($ys) {
        if ($disposedStocks -and $disposedStocks.ContainsKey($ts.Code)) {
            Write-Host "個股 $($ts.Code) $($ts.Name) 目前已在處置股名單中 (期間: $($disposedStocks[$ts.Code].Period))，跳過預警分析。" -ForegroundColor Yellow
        } else {
            $consecutiveStocks += $ts
        }
    }
}

# 彙整所有當前與即將處置股以供輸出
$disposedResultList = @()
if ($disposedStocks) {
    foreach ($code in $disposedStocks.Keys) {
        # 優先從今日注意股獲取收盤價，其次為快取
        $ts = $todayStocks | Where-Object { $_.Code -eq $code }
        $closePrice = "N/A"
        if ($ts) {
            $closePrice = $ts.Close
        } else {
            $cache = Get-PricesCache
            if ($cache.PSObject.Properties[$code] -ne $null -and $cache.$code.prices.Count -gt 0) {
                $lastIdx = $cache.$code.prices.Count - 1
                $closePrice = $cache.$code.prices[$lastIdx].Close.ToString()
            }
        }
        
        $name = $disposedStocks[$code].Name
        $market = $disposedStocks[$code].Market
        $period = $disposedStocks[$code].Period
        
        $disposedResultList += [PSCustomObject]@{
            Code = $code
            Name = $name
            Market = $market
            Close = $closePrice
            Reason = "【已處置有價證券】處置期間: $period 。現正執行人工管制撮合及預收款券等處置措施。"
            IsDisposed = $true
            DisposedPeriod = $period
            Calculations = @()
            VolumeCalculations = @()
        }
    }
}

Write-Host "連續兩天被列為注意股的股票數量: $($consecutiveStocks.Count)" -ForegroundColor Green
Write-Host "----------------------------------------------------------" -ForegroundColor Gray

if ($consecutiveStocks.Count -eq 0) {
    Write-Host "今日沒有連續兩天被列為注意的股票。" -ForegroundColor Yellow
    exit
}

# ----------------- 3. 分析與計算隔日觸發門檻 -----------------

$results = @()

foreach ($stock in $consecutiveStocks) {
    $cleanClose = [double]($stock.Close.Replace(",", ""))
    
    # 獲取價格歷史
    $isTpex = $stock.Market -eq "上櫃"
    $history = Get-StockHistory -code $stock.Code -isTpex $isTpex
    
    if (!$history -or $history.Count -lt 10) {
        Write-Host "警告: 無法獲取 $($stock.Code) $($stock.Name) 的歷史價格，跳過計算。" -ForegroundColor Yellow
        continue
    }
    
    $lastIdx = $history.Count - 1
    $histDate = $history[$lastIdx].Date
    $currentPrice = $history[$lastIdx].Close
    $currentVolume = $history[$lastIdx].Volume
    
    # 確保當前最新價格和公告價格同步
    $histDateTime = [datetime]::ParseExact($histDate, "yyyy-MM-dd", $null)
    $stockDateTime = [datetime]::ParseExact($stock.Date, "yyyy-MM-dd", $null)
    if ($stockDateTime -eq $histDateTime) {
        # 如果日期相同，確保收盤價使用官方公告值（以防 Yahoo 數據延遲或未更新）
        $history[$lastIdx].Close = $cleanClose
        $currentPrice = $cleanClose
    } elseif ($stockDateTime -gt $histDateTime) {
        # 如果公告日期大於歷史資料最新日期（Yahoo 尚未更新今日收盤），則補上今日資料
        $history += [PSCustomObject]@{ Date = $stock.Date; Close = $cleanClose; Volume = 0.0 }
        $lastIdx = $history.Count - 1
        $currentPrice = $cleanClose
    }
    
    $reason = $stock.Reason
    $stockCalculations = @()
    $volumeCalculations = @()
    
    # 解析價格規則
    # 6日累積漲跌幅
    $rule6 = $false
    $rule6_pct = if ($isTpex) { 30.0 } else { 32.0 }
    if ($reason -match "六個營業日.*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%" -or 
        $reason -match "六日.*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%") {
        $rule6 = $true
        $rule6_pct = [double]$Matches[1]
    }
    
    # 6日價差規則
    $ruleDiff = $false
    $ruleDiff_val = 0.0
    if ($reason -match "收盤價價差達\s*([\d\.,]+)\s*元" -or $reason -match "最後成交價價差達\s*([\d\.,]+)\s*元") {
        $ruleDiff = $true
        $ruleDiff_val = [double]($Matches[1].Replace(",", ""))
    }
    
    # 30日累積漲幅
    $rule30 = $false
    $rule30_pct = 100.0
    if ($reason -match "(?:三十個營業日|三十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%") {
        $rule30 = $true
        $rule30_pct = [double]$Matches[1]
    }
    
    # 60日累積漲幅
    $rule60 = $false
    $rule60_pct = 130.0
    if ($reason -match "(?:六十個營業日|六十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%") {
        $rule60 = $true
        $rule60_pct = [double]$Matches[1]
    }
    
    # 90日累積漲幅
    $rule90 = $false
    $rule90_pct = 160.0
    if ($reason -match "(?:九十個營業日|九十日).*(?:漲跌幅|漲幅|跌幅)達\s*([\d\.]+)%") {
        $rule90 = $true
        $rule90_pct = [double]$Matches[1]
    }
    
    # 取得歷史基準價 (基準日為 T-5, T-29, T-59, T-89 以計算 T+1 日的 6日, 30日, 60日, 90日累積變動，對應 index 偏移量分別為 5, 29, 59, 89)
    $p_t5 = if ($lastIdx -ge 5) { $history[$lastIdx-5].Close } else { $null }
    $p_t29 = if ($lastIdx -ge 29) { $history[$lastIdx-29].Close } else { $null }
    $p_t59 = if ($lastIdx -ge 59) { $history[$lastIdx-59].Close } else { $null }
    $p_t89 = if ($lastIdx -ge 89) { $history[$lastIdx-89].Close } else { $null }
    
    # 6日價格計算
    if ($p_t5) {
        $std_pct = if ($isTpex) { 30.0 } else { 32.0 }
        $up_price = Round-ToTaiwanStockTick ([Math]::Round($p_t5 * (1 + $std_pct/100), 2)) $true
        $down_price = Round-ToTaiwanStockTick ([Math]::Round($p_t5 * (1 - $std_pct/100), 2)) $false
        $up_change = [Math]::Round((($up_price - $currentPrice) / $currentPrice) * 100, 2)
        $down_change = [Math]::Round((($down_price - $currentPrice) / $currentPrice) * 100, 2)
        
        $stockCalculations += [PSCustomObject]@{
            Rule = "6日累積漲跌幅 (標準 $std_pct%)"
            BasePrice = $p_t5
            TargetUpPrice = $up_price
            TargetUpChange = $up_change
            TargetDownPrice = $down_price
            TargetDownChange = $down_change
            IsPrimary = $true
        }
        
        # 2. 公告值門檻
        if ($rule6) {
            $up_price_act = Round-ToTaiwanStockTick ([Math]::Round($p_t5 * (1 + $rule6_pct/100), 2)) $true
            $down_price_act = Round-ToTaiwanStockTick ([Math]::Round($p_t5 * (1 - $rule6_pct/100), 2)) $false
            $up_change_act = [Math]::Round((($up_price_act - $currentPrice) / $currentPrice) * 100, 2)
            $down_change_act = [Math]::Round((($down_price_act - $currentPrice) / $currentPrice) * 100, 2)
            
            $stockCalculations += [PSCustomObject]@{
                Rule = "6日累積漲跌幅 (今日公告值 $rule6_pct%)"
                BasePrice = $p_t5
                TargetUpPrice = $up_price_act
                TargetUpChange = $up_change_act
                TargetDownPrice = $down_price_act
                TargetDownChange = $down_change_act
                IsPrimary = $false
            }
        }
        
        # 3. 6日價差與新高低門檻
        if ($ruleDiff) {
            $target_up = $p_t5 + $ruleDiff_val
            $target_down = $p_t5 - $ruleDiff_val
            # 5日高低收盤價 (N 至 N-4)
            $subHistory = $history[$lastIdx..($lastIdx-4)]
            $max_price = $subHistory | ForEach-Object { $_.Close } | Measure-Object -Maximum | Select-Object -ExpandProperty Maximum
            $min_price = $subHistory | ForEach-Object { $_.Close } | Measure-Object -Minimum | Select-Object -ExpandProperty Minimum
            
            $up_price_diff = Round-ToTaiwanStockTick ([Math]::Round([Math]::Max($target_up, $max_price), 2)) $true
            $down_price_diff = Round-ToTaiwanStockTick ([Math]::Round([Math]::Min($target_down, $min_price), 2)) $false
            $up_change_diff = [Math]::Round((($up_price_diff - $currentPrice) / $currentPrice) * 100, 2)
            $down_change_diff = [Math]::Round((($down_price_diff - $currentPrice) / $currentPrice) * 100, 2)
            
            $stockCalculations += [PSCustomObject]@{
                Rule = "6日收盤價差 ($ruleDiff_val 元) 且為最高/最低"
                BasePrice = $p_t5
                TargetUpPrice = $up_price_diff
                TargetUpChange = $up_change_diff
                TargetDownPrice = $down_price_diff
                TargetDownChange = $down_change_diff
                IsPrimary = $true
            }
        }
    }
    
    # 30日價格計算
    if ($p_t29) {
        $std_pct = 100.0
        if ($rule30) { $std_pct = $rule30_pct }
        $up_price = Round-ToTaiwanStockTick ([Math]::Round($p_t29 * (1 + $std_pct/100), 2)) $true
        $up_change = [Math]::Round((($up_price - $currentPrice) / $currentPrice) * 100, 2)
        
        $stockCalculations += [PSCustomObject]@{
            Rule = "30日累積漲跌幅 ($std_pct%)"
            BasePrice = $p_t29
            TargetUpPrice = $up_price
            TargetUpChange = $up_change
            TargetDownPrice = $null
            TargetDownChange = $null
            IsPrimary = $rule30
        }
    }
    
    # 60日價格計算
    if ($p_t59) {
        $std_pct = 130.0
        if ($rule60) { $std_pct = $rule60_pct }
        $up_price = Round-ToTaiwanStockTick ([Math]::Round($p_t59 * (1 + $std_pct/100), 2)) $true
        $up_change = [Math]::Round((($up_price - $currentPrice) / $currentPrice) * 100, 2)
        
        $stockCalculations += [PSCustomObject]@{
            Rule = "60日累積漲跌幅 ($std_pct%)"
            BasePrice = $p_t59
            TargetUpPrice = $up_price
            TargetUpChange = $up_change
            TargetDownPrice = $null
            TargetDownChange = $null
            IsPrimary = $rule60
        }
    }
    
    # 90日價格計算
    if ($p_t89) {
        $std_pct = 160.0
        if ($rule90) { $std_pct = $rule90_pct }
        $up_price = Round-ToTaiwanStockTick ([Math]::Round($p_t89 * (1 + $std_pct/100), 2)) $true
        $up_change = [Math]::Round((($up_price - $currentPrice) / $currentPrice) * 100, 2)
        
        $stockCalculations += [PSCustomObject]@{
            Rule = "90日累積漲跌幅 ($std_pct%)"
            BasePrice = $p_t89
            TargetUpPrice = $up_price
            TargetUpChange = $up_change
            TargetDownPrice = $null
            TargetDownChange = $null
            IsPrimary = $rule90
        }
    }
    
    # ----------------- 成交量規則計算 -----------------
    
    # 1. 60日均量放大倍數 (標準 5.0 倍)
    $avg_vol_60 = 0.0
    if ($lastIdx -ge 59) {
        $vol_sum = 0.0
        for ($i=0; $i -lt 60; $i++) {
            $vol_sum += $history[$lastIdx-$i].Volume
        }
        $avg_vol_60 = [Math]::Round($vol_sum / 60, 2)
    }
    
    $vol_multiplier = 5.0
    if ($reason -match "(?:成交量為最近六十個營業日日平均成交量之|日平均成交量之|日平均成交量.*放大)\s*([\d\.]+)\s*倍") {
        $vol_multiplier = [double]$Matches[1]
    }
    
    if ($avg_vol_60 -gt 0) {
        $volumeCalculations += [PSCustomObject]@{
            Rule = "60日日平均成交量放大倍數 ($vol_multiplier 倍)"
            Baseline = $avg_vol_60
            TriggerVolume = [Math]::Round($avg_vol_60 * $vol_multiplier, 0)
        }
    }
    
    # 2. 週轉率與發行股數倒推
    $today_tr = 0.0
    if ($reason -match "(?:週轉率為|週轉率達)\s*([\d\.]+)%") {
        $today_tr = [double]$Matches[1]
    }
    
    $est_shares = 0.0
    $today_vol = $history[$lastIdx].Volume
    if ($today_vol -gt 0 -and $today_tr -gt 0) {
        $est_shares = $today_vol * 100 / $today_tr
    }
    
    if ($est_shares -gt 0) {
        # 當日週轉率達 10% 門檻
        $vol_threshold_10tr = [Math]::Round($est_shares * 0.10, 0)
        $volumeCalculations += [PSCustomObject]@{
            Rule = "當日週轉率達 10.0% 門檻"
            Baseline = $est_shares
            TriggerVolume = $vol_threshold_10tr
        }
        
        # 6日累積週轉率達 50% 門檻
        $sum_vol_5 = 0.0
        for ($i=0; $i -lt 5; $i++) {
            $sum_vol_5 += $history[$lastIdx-$i].Volume
        }
        $sum_tr_5 = ($sum_vol_5 / $est_shares) * 100
        $req_tr_tomorrow = 50.0 - $sum_tr_5
        
        $vol_threshold_6tr = if ($req_tr_tomorrow -gt 0) {
            [Math]::Round($est_shares * ($req_tr_tomorrow / 100), 0)
        } else {
            0.0
        }
        
        $volumeCalculations += [PSCustomObject]@{
            Rule = "6日累積週轉率達 50.0% 門檻 (明日需達 $($req_tr_tomorrow.ToString('F2'))%)"
            Baseline = $est_shares
            TriggerVolume = $vol_threshold_6tr
        }
    }
    
    # 輸出至控制台呈現 (CLI)
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " 證券代號: $($stock.Code)  $($stock.Name) ($($stock.Market))" -ForegroundColor White
    Write-Host " 今日收盤價: $($stock.Close) 元  |  今日成交量: $(Format-Volume $today_vol)" -ForegroundColor DarkGray
    Write-Host " 今日公告原因: $($reason -replace '<[^>]*>', '')" -ForegroundColor Gray
    Write-Host "----------------------------------------------------------" -ForegroundColor Gray
    
    Write-Host " 【明日價格注意門檻 (收盤價)】" -ForegroundColor Yellow
    foreach ($calc in $stockCalculations) {
        $ruleName = $calc.Rule
        $limitNoteUp = ""
        $limitNoteDown = ""
        $highlightUp = ""
        
        if ($calc.TargetUpChange -gt 10.0) { 
            $limitNoteUp = " [超出明日漲停限制 +10%]" 
        } else {
            if ($calc.TargetUpChange -gt 0 -and $calc.TargetUpChange -le 5.0) {
                $highlightUp = " [盤中重點監控！極易觸發]"
            }
        }
        
        if ($calc.TargetDownPrice) {
            if ($calc.TargetDownChange -lt -10.0) { $limitNoteDown = " [超出明日跌停限制 -10%]" }
        }
        
        $clauseTag = if ($calc.IsPrimary) { "*" } else { " " }
        
        Write-Host "  $clauseTag $ruleName" -ForegroundColor Cyan
        Write-Host "      ▲ 看漲觸發價: $($calc.TargetUpPrice.ToString('F2')) 元 (漲幅需求: $($calc.TargetUpChange.ToString('F2'))%)$limitNoteUp$highlightUp" -ForegroundColor Green
        if ($calc.TargetDownPrice) {
            Write-Host "      ▼ 看跌觸發價: $($calc.TargetDownPrice.ToString('F2')) 元 (跌幅需求: $($calc.TargetDownChange.ToString('F2'))%)$limitNoteDown" -ForegroundColor Red
        }
    }
    
    if ($volumeCalculations.Count -gt 0) {
        Write-Host ""
        Write-Host " 【明日成交量注意門檻】" -ForegroundColor Yellow
        foreach ($vCalc in $volumeCalculations) {
            $clauseTag = " "
            if ($vCalc.TriggerVolume -le 0) {
                Write-Host "    $($vCalc.Rule):" -ForegroundColor Magenta
                Write-Host "      ● 觸發量: 明日任意成交量皆會觸發！(已提前累積達標)" -ForegroundColor Yellow
            } else {
                Write-Host "    $($vCalc.Rule):" -ForegroundColor Magenta
                Write-Host "      ● 觸發成交量: $(Format-Volume $vCalc.TriggerVolume)" -ForegroundColor Green
            }
        }
    } else {
        Write-Host ""
        Write-Host " 【明日成交量注意門檻】" -ForegroundColor Yellow
        Write-Host "    由於今日公告原因中未提及週轉率且查無歷史股數，僅推算 60日均量規則。" -ForegroundColor DarkGray
        if ($avg_vol_60 -gt 0) {
            $req_60 = [Math]::Round($avg_vol_60 * 5, 0)
            Write-Host "    - 60日均量放大 5 倍門檻:" -ForegroundColor Magenta
            Write-Host "      ● 觸發成交量: $(Format-Volume $req_60)" -ForegroundColor Green
        } else {
            Write-Host "    - 60日均量放大 5 倍門檻: 資料不足無法推算" -ForegroundColor Red
        }
    }
    
    $results += [PSCustomObject]@{
        Code = $stock.Code
        Name = $stock.Name
        Market = $stock.Market
        Close = $stock.Close
        Reason = $stock.Reason
        Calculations = $stockCalculations
        VolumeCalculations = $volumeCalculations
    }
}

# ----------------- 4. 產出 Markdown 報告 -----------------

$reportDate = (Get-Date).ToString("yyyyMMdd")
$reportFile = Join-Path $ReportsDir "attention_report_$reportDate.md"

$md = @()
$md += "# 台灣股市注意股分析與隔日處置預警報告"
$md += ""
$md += "- **報告日期**: $(Get-Date -Format 'yyyy-MM-dd')"
$md += "- **今日交易日 ($T$)**: $todayDate"
$md += "- **昨日交易日 ($T-1$)**: $yesterdayDate"
$md += ""
$md += "## 連續被列為注意股兩天的股票名單"
$md += ""
$md += "當股票連續兩天被列為注意股時，若第三天再次被列為注意股，**將有極大機率觸發「處置有價證券」（關禁閉）**。以下為您整理這些股票在隔日（下一個交易日）若再度符合各項價格與成交量異常條件所需的收盤門檻。"
$md += ""
$md += "| 證券代號 | 證券名稱 | 市場 | 今日收盤價 | 今日成交量 | 注意原因 |"
$md += "| --- | --- | --- | --- | --- | --- |"

foreach ($res in $results) {
    $ts = $consecutiveStocks | Where-Object { $_.Code -eq $res.Code }
    $code_history = Get-PricesCache | ForEach-Object { $_.$($res.Code) }
    $vol_lots = "N/A"
    if ($code_history) {
        $last_idx = $code_history.prices.Count - 1
        $vol_val = $code_history.prices[$last_idx].Volume
        $vol_lots = "{0:N0} 張" -f [Math]::Round($vol_val / 1000, 0)
    }
    $cleanReason = $res.Reason -replace "<[^>]*>", ""
    $md += "| $($res.Code) | $($res.Name) | $($res.Market) | $($res.Close) | $vol_lots | $cleanReason |"
}

$md += ""
$md += "---"
$md += ""
$md += "## 各股隔日處置觸發門檻預警明細"
$md += ""

foreach ($res in $results) {
    $md += "### [$($res.Code) $($res.Name) ($($res.Market))](https://tw.stock.yahoo.com/quote/$($res.Code))"
    $md += ""
    $md += "- **今日收盤價**: $($res.Close) 元"
    $md += "- **今日公告注意原因**: $($res.Reason -replace '<[^>]*>', '')"
    $md += ""
    $md += "#### 1. 價格觸發門檻"
    $md += ""
    $md += "| 觸發條件類型 | 基準日價格 | 隔日看漲觸發價 | 漲幅需求 | 隔日看跌觸發價 | 跌幅需求 | 備註 |"
    $md += "| --- | --- | --- | --- | --- | --- | --- |"
    
    foreach ($calc in $res.Calculations) {
        $upPriceStr = $calc.TargetUpPrice.ToString("F2")
        $upChangeStr = "$($calc.TargetUpChange.ToString('F2'))%"
        $downPriceStr = if ($calc.TargetDownPrice) { $calc.TargetDownPrice.ToString("F2") } else { "N/A" }
        $downChangeStr = if ($calc.TargetDownChange) { "$($calc.TargetDownChange.ToString('F2'))%" } else { "N/A" }
        
        $note = ""
        if ($calc.TargetUpChange -gt 10.0 -or $calc.TargetUpChange -lt -10.0) {
            $note += "看漲超出漲停限制(10%)。 "
        }
        if ($calc.TargetDownPrice -and ($calc.TargetDownChange -lt -10.0 -or $calc.TargetDownChange -gt 10.0)) {
            $note += "看跌超出跌停限制(-10%)。"
        }
        if ($calc.IsPrimary) {
            $note += "**今日觸發主條款**"
        }
        
        $md += "| $($calc.Rule) | $($calc.BasePrice) | $upPriceStr | $upChangeStr | $downPriceStr | $downChangeStr | $note |"
    }
    $md += ""
    
    $md += "#### 2. 成交量觸發門檻"
    $md += ""
    if ($res.VolumeCalculations.Count -gt 0) {
        $md += "| 成交量規則 | 估算流通股數 / 60日均量 | 明日觸發成交量門檻 | 張數換算 | 備註 |"
        $md += "| --- | --- | --- | --- | --- |"
        foreach ($vCalc in $res.VolumeCalculations) {
            $baselineStr = "{0:N0} 股" -f $vCalc.Baseline
            $triggerStr = if ($vCalc.TriggerVolume -le 0) { "任意量皆觸發" } else { "{0:N0} 股" -f $vCalc.TriggerVolume }
            $lotsStr = if ($vCalc.TriggerVolume -le 0) { "任意量" } else { "{0:N0} 張" -f [Math]::Round($vCalc.TriggerVolume / 1000, 0) }
            $md += "| $($vCalc.Rule) | $baselineStr | $triggerStr | $lotsStr | |"
        }
    } else {
        $md += "無發行股數估算，預估 **60日均量放大 5 倍** 門檻為："
        $code_history = Get-PricesCache | ForEach-Object { $_.$($res.Code) }
        if ($code_history -and $avg_vol_60 -gt 0) {
            $req_60 = [Math]::Round($avg_vol_60 * 5, 0)
            $req_lots = [Math]::Round($req_60 / 1000, 0)
            $md += "- 60日平均日銷成交量: {0:N0} 股 ({1:N0} 張)" -f $avg_vol_60, [Math]::Round($avg_vol_60 / 1000, 0)
            $md += "- 明日觸發成交量門檻: **{0:N0} 股 ({1:N0} 張)**" -f $req_60, $req_lots
        } else {
            $md += "- 資料不足無法預估。"
        }
    }
    $md += ""
}

$md += ""
$md += "> **免責聲明**: 本報告之計算數值基於公開交易數據與各項常見注意股公式進行純學術推算，實際注意股票與處置股票之判定以證券交易所與櫃買中心之每日公告為準。投資人操作時請審慎評估風險。"
$md += ""

if ($disposedResultList.Count -gt 0) {
    $md += "---"
    $md += ""
    $md += "## 當前處置中 / 即將處置之有價證券名單"
    $md += ""
    $md += "以下有價證券目前已在處置股名單中（或即將進入處置），系統已自動排除其隔日價格與成交量注意門檻之預警計算："
    $md += ""
    $md += "| 證券代號 | 證券名稱 | 市場 | 今日收盤價 | 處置期間 |"
    $md += "| --- | --- | --- | --- | --- |"
    foreach ($dr in $disposedResultList) {
        $md += "| $($dr.Code) | $($dr.Name) | $($dr.Market) | $($dr.Close) | $($dr.DisposedPeriod) |"
    }
    $md += ""
}

Set-Content -Path $reportFile -Value ($md -join "`n") -Encoding UTF8 -Force

# 將結果輸出成 JSON 檔案，以供 Python GUI 讀取
try {
    $jsonPath = Join-Path $DbDir "dashboard_data.json"
    $finalResults = $results + $disposedResultList
    $resultsJson = ConvertTo-Json $finalResults -Depth 10
    Set-Content -Path $jsonPath -Value $resultsJson -Encoding UTF8 -Force
} catch {
    Write-Host "警告: 無法寫入 JSON 預警數據庫。" -ForegroundColor Yellow
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "分析完成！" -ForegroundColor Green
Write-Host "今日報告已儲存至: $reportFile" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

Sync-ToGitHub


# ----------------- 5. 互動式 CLI 儀表板 -----------------

function Get-VisualWidth($str) {
    if ($null -eq $str) { return 0 }
    $width = 0
    foreach ($char in $str.ToCharArray()) {
        if ([int]$char -gt 127) {
            $width += 2
        } else {
            $width += 1
        }
    }
    return $width
}

function Pad-RightVisual($str, $targetWidth) {
    if ($null -eq $str) { $str = "" }
    $currentWidth = Get-VisualWidth $str
    $needed = $targetWidth - $currentWidth
    if ($needed -le 0) { return $str }
    return $str + (" " * $needed)
}

function Pad-LeftVisual($str, $targetWidth) {
    if ($null -eq $str) { $str = "" }
    $currentWidth = Get-VisualWidth $str
    $needed = $targetWidth - $currentWidth
    if ($needed -le 0) { return $str }
    return (" " * $needed) + $str
}

function Show-Dashboard($results) {
    $cache = Get-PricesCache
    $loop = $true
    
    while ($loop) {
        Clear-Host
        Write-Host "=================================================================================" -ForegroundColor Cyan
        Write-Host "             台灣股市連續注意股 & 處置預警盤中監控儀表板 ($(Get-Date -Format 'yyyy-MM-dd'))" -ForegroundColor Cyan
        Write-Host "=================================================================================" -ForegroundColor Cyan
        Write-Host " 共有 $($results.Count) 檔連續被列為注意股兩天的股票，明日再觸發將面臨處置（關禁閉）風險：" -ForegroundColor White
        Write-Host ""
        
        Write-Host " 序    代號   名稱         市場     今日收盤     今日成交   最易觸發價格門檻 (收盤 / 漲幅)" -ForegroundColor Yellow
        Write-Host " ---------------------------------------------------------------------------------" -ForegroundColor Gray
        
        $idx = 1
        foreach ($res in $results) {
            $code = $res.Code
            $name = $res.Name
            $mkt = $res.Market
            $close = $res.Close
            
            # 從快取中取得歷史與成交量
            $code_history = if ($cache.PSObject.Properties[$code] -ne $null) { $cache.$code } else { $null }
            $vol_str = "N/A"
            if ($code_history) {
                $last_idx = $code_history.prices.Count - 1
                $vol_val = $code_history.prices[$last_idx].Volume
                $vol_str = "{0:N0} 張" -f [Math]::Round($vol_val / 1000, 0)
            }
            
            # 尋找最接近/最易觸發的價格門檻
            $bestCalc = $null
            $minAbsChange = 9999.0
            foreach ($calc in $res.Calculations) {
                if ($calc.TargetUpChange -ne $null) {
                    $absChange = [Math]::Abs($calc.TargetUpChange)
                    if ($absChange -lt $minAbsChange) {
                        $minAbsChange = $absChange
                        $bestCalc = $calc
                    }
                }
                if ($calc.TargetDownChange -ne $null) {
                    $absChange = [Math]::Abs($calc.TargetDownChange)
                    if ($absChange -lt $minAbsChange) {
                        $minAbsChange = $absChange
                        $bestCalc = $calc
                    }
                }
            }
            
            $thresholdStr = "無推算數據"
            $highlightText = ""
            $highlightColor = "Gray"
            
            if ($bestCalc) {
                $isUp = $true
                $targetPrice = $bestCalc.TargetUpPrice
                $targetChange = $bestCalc.TargetUpChange
                if ($bestCalc.TargetDownPrice -ne $null -and [Math]::Abs($bestCalc.TargetDownChange) -lt [Math]::Abs($bestCalc.TargetUpChange)) {
                    $isUp = $false
                    $targetPrice = $bestCalc.TargetDownPrice
                    $targetChange = $bestCalc.TargetDownChange
                }
                
                $direction = if ($isUp) { "▲" } else { "▼" }
                $thresholdStr = "{0} {1:F2} 元 ({2:F2}%)" -f $direction, $targetPrice, $targetChange
                
                if ($targetChange -ge -1.0 -and $targetChange -le 1.0) {
                    $highlightText = " *極易觸發*"
                    $highlightColor = "Red"
                } elseif ($targetChange -ge -5.0 -and $targetChange -le 5.0) {
                    $highlightText = " *重點監控*"
                    $highlightColor = "Yellow"
                } else {
                    $highlightColor = "White"
                }
            }
            
            # 輸出格式化行
            $col_idx = Pad-RightVisual "[$idx]" 5
            $col_code = Pad-RightVisual $code 6
            $col_name = Pad-RightVisual $name 12
            $col_mkt = Pad-RightVisual $mkt 6
            $col_close = Pad-LeftVisual ("{0:F2}" -f [double]($close.Replace(",", ""))) 10
            $col_vol = Pad-LeftVisual $vol_str 12
            
            Write-Host " $col_idx $col_code $col_name $col_mkt $col_close $col_vol   " -NoNewline -ForegroundColor White
            Write-Host $thresholdStr -NoNewline -ForegroundColor $highlightColor
            if ($highlightText) {
                Write-Host $highlightText -ForegroundColor $highlightColor
            } else {
                Write-Host ""
            }
            
            $idx++
        }
        
        Write-Host " ---------------------------------------------------------------------------------" -ForegroundColor Gray
        Write-Host " [R] 重新整理資料      [S] 搜尋特定股票      [Q] 離開系統" -ForegroundColor Green
        Write-Host ""
        Write-Output -NoNewline " 請輸入股票序號、代號查看詳細門檻 (或選擇指令): "
        
        $inputVal = Read-Host
        if ([string]::IsNullOrEmpty($inputVal)) { continue }
        
        $inputVal = $inputVal.Trim().ToUpper()
        
        if ($inputVal -eq "Q") {
            $loop = $false
            break
        } elseif ($inputVal -eq "R") {
            return "REFRESH"
        } elseif ($inputVal -eq "S") {
            Write-Output -NoNewline "請輸入要搜尋的股票代號或名稱: "
            $searchQuery = Read-Host
            if (![string]::IsNullOrEmpty($searchQuery)) {
                $searchQuery = $searchQuery.Trim()
                $found = $results | Where-Object { $_.Code -eq $searchQuery -or $_.Name -like "*$searchQuery*" }
                if ($found) {
                    Show-StockDetail $found[0]
                } else {
                    Write-Host "找不到符合條件的股票。" -ForegroundColor Red
                    Start-Sleep -Seconds 2
                }
            }
        } else {
            # 檢查是否為序號
            $selectIdx = 0
            if ([int]::TryParse($inputVal, [ref]$selectIdx)) {
                if ($selectIdx -ge 1 -and $selectIdx -le $results.Count) {
                    Show-StockDetail $results[$selectIdx - 1]
                    continue
                }
            }
            
            # 檢查是否為代號
            $found = $results | Where-Object { $_.Code -eq $inputVal }
            if ($found) {
                Show-StockDetail $found[0]
            } else {
                Write-Host "輸入無效，請輸入正確的序號、代號或指令。" -ForegroundColor Red
                Start-Sleep -Seconds 2
            }
        }
    }
    return "EXIT"
}

function Show-StockDetail($res) {
    Clear-Host
    $code = $res.Code
    $name = $res.Name
    $mkt = $res.Market
    $close = $res.Close
    $reason = $res.Reason
    
    $cache = Get-PricesCache
    $code_history = if ($cache.PSObject.Properties[$code] -ne $null) { $cache.$code } else { $null }
    $vol_str = "N/A"
    if ($code_history) {
        $last_idx = $code_history.prices.Count - 1
        $vol_val = $code_history.prices[$last_idx].Volume
        $vol_str = Format-Volume $vol_val
    }
    
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " 證券代號: $code  $name ($mkt)" -ForegroundColor White
    Write-Host " 今日收盤價: $close 元  |  今日成交量: $vol_str" -ForegroundColor DarkGray
    Write-Host " 今日公告原因: $($reason -replace '<[^>]*>', '')" -ForegroundColor Gray
    Write-Host "----------------------------------------------------------" -ForegroundColor Gray
    
    Write-Host " 【明日價格注意門檻 (收盤價)】" -ForegroundColor Yellow
    foreach ($calc in $res.Calculations) {
        $ruleName = $calc.Rule
        $limitNoteUp = ""
        $limitNoteDown = ""
        $highlightUp = ""
        
        if ($calc.TargetUpChange -gt 10.0) { 
            $limitNoteUp = " [超出明日漲停限制 +10%]" 
        } else {
            if ($calc.TargetUpChange -gt 0 -and $calc.TargetUpChange -le 5.0) {
                $highlightUp = " [盤中重點監控！極易觸發]"
            }
        }
        
        if ($calc.TargetDownPrice) {
            if ($calc.TargetDownChange -lt -10.0) { $limitNoteDown = " [超出明日跌停限制 -10%]" }
        }
        
        $clauseTag = if ($calc.IsPrimary) { "*" } else { " " }
        
        Write-Host "  $clauseTag $ruleName" -ForegroundColor Cyan
        Write-Host "      ▲ 看漲觸發價: $($calc.TargetUpPrice.ToString('F2')) 元 (漲幅需求: $($calc.TargetUpChange.ToString('F2'))%)$limitNoteUp$highlightUp" -ForegroundColor Green
        if ($calc.TargetDownPrice) {
            Write-Host "      ▼ 看跌觸發價: $($calc.TargetDownPrice.ToString('F2')) 元 (跌幅需求: $($calc.TargetDownChange.ToString('F2'))%)$limitNoteDown" -ForegroundColor Red
        }
    }
    
    if ($res.VolumeCalculations.Count -gt 0) {
        Write-Host ""
        Write-Host " 【明日成交量注意門檻】" -ForegroundColor Yellow
        foreach ($vCalc in $res.VolumeCalculations) {
            if ($vCalc.TriggerVolume -le 0) {
                Write-Host "    $($vCalc.Rule):" -ForegroundColor Magenta
                Write-Host "      ● 觸發量: 明日任意成交量皆會觸發！(已提前累積達標)" -ForegroundColor Yellow
            } else {
                Write-Host "    $($vCalc.Rule):" -ForegroundColor Magenta
                Write-Host "      ● 觸發成交量: $(Format-Volume $vCalc.TriggerVolume)" -ForegroundColor Green
            }
        }
    } else {
        Write-Host ""
        Write-Host " 【明日成交量注意門檻】" -ForegroundColor Yellow
        Write-Host "    由於今日公告原因中未提及週轉率且查無歷史股數，僅推算 60日均量規則。" -ForegroundColor DarkGray
        
        $avg_vol_60 = 0.0
        if ($code_history) {
            $last_idx = $code_history.prices.Count - 1
            if ($last_idx -ge 59) {
                $vol_sum = 0.0
                for ($i=0; $i -lt 60; $i++) {
                    $vol_sum += $code_history.prices[$last_idx-$i].Volume
                }
                $avg_vol_60 = $vol_sum / 60
            }
        }
        
        if ($avg_vol_60 -gt 0) {
            $req_60 = [Math]::Round($avg_vol_60 * 5, 0)
            Write-Host "    - 60日均量放大 5 倍門檻:" -ForegroundColor Magenta
            Write-Host "      ● 觸發成交量: $(Format-Volume $req_60)" -ForegroundColor Green
        } else {
            Write-Host "    - 60日均量放大 5 倍門檻: 資料不足無法推算" -ForegroundColor Red
        }
    }
    
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Output "請按任意鍵返回儀表板列表..."
    $null = [Console]::ReadKey($true)
}

# 判斷是否在互動式環境下執行
$isInteractive = [Environment]::UserInteractive -and ![Console]::IsInputRedirected
if ($isInteractive) {
    $dashAction = Show-Dashboard $results
    if ($dashAction -eq "REFRESH") {
        Write-Host "正在重新下載並整理注意股資料，請稍候..." -ForegroundColor Yellow
        Start-Sleep -Seconds 1
        & $MyInvocation.MyCommand.Path
        exit
    }
} else {
    Write-Host "偵測到非互動式環境，已跳過互動式儀表板。" -ForegroundColor Gray
}

