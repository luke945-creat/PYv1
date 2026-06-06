# Register-DailyTask.ps1
# 註冊每日自動分析注意股與處置股之 Windows 排程工作

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ScriptDir)) { $ScriptDir = Get-Location }
$TargetScript = Join-Path $ScriptDir "Get-AttentionStocks.ps1"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         註冊每日自動更新排程工作 (Windows 工作排程器)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 檢查目標腳本是否存在
if (!(Test-Path $TargetScript)) {
    Write-Host "錯誤: 找不到目標分析腳本 $TargetScript" -ForegroundColor Red
    exit
}

$TaskName = "TaiwanStockMonitorDaily"
$TriggerTime = "19:05"

Write-Host "正在設定排程工作..." -ForegroundColor Gray
Write-Host "- 目標腳本: $TargetScript" -ForegroundColor White
Write-Host "- 執行時間: 每日 $TriggerTime" -ForegroundColor White
Write-Host "- 執行方式: 背景隱藏視窗 (不干擾電腦使用)" -ForegroundColor White

try {
    # 建立執行動作 (使用 -WindowStyle Hidden 隱藏視窗)
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$TargetScript`"" `
        -WorkingDirectory $ScriptDir

    # 建立觸發器 (每日 19:05 觸發)
    $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime

    # 建立排程設定 (允許電池模式下執行、錯過時間自動補跑、失敗自動重試)
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)

    # 註冊排程工作 (以當前登入使用者身分執行)
    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "每日台股注意股與處置預警自動分析並同步至 GitHub" `
        -Force | Out-Null

    Write-Host ""
    Write-Host "成功！排程工作 '$TaskName' 已成功註冊。" -ForegroundColor Green
    Write-Host "它將在每天的 $TriggerTime 自動於背景執行並嘗試將更新推送到 GitHub Pages。" -ForegroundColor Green
    Write-Host "如果執行時間電腦關機，在下次開機時會自動補跑分析。" -ForegroundColor Green
    Write-Host ""
    Write-Host "【如何測試排程是否正常執行？】" -ForegroundColor Yellow
    Write-Host "您可以開啟 Windows「工作排程器」，在列表中找到 '$TaskName'，" -ForegroundColor White
    Write-Host "右鍵點選「執行」，即可立即在背景測試其運作情況！" -ForegroundColor White
} catch {
    Write-Host ""
    Write-Host "錯誤: 註冊排程工作失敗！" -ForegroundColor Red
    Write-Host "原因: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "提示: 某些 Windows 系統需要「系統管理員權限 (Administrator)」才能註冊排程工作。" -ForegroundColor Yellow
    Write-Host "請嘗試以系統管理員身分開啟 PowerShell，然後重新執行本腳本。" -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
