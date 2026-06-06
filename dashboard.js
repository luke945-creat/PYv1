// dashboard.js

document.addEventListener('DOMContentLoaded', () => {
    // DOM 元素引用
    const searchInput = document.getElementById('search-input');
    const marketFilter = document.getElementById('market-filter');
    const warningTbody = document.getElementById('warning-tbody');
    const disposedTbody = document.getElementById('disposed-tbody');
    const listeningTbody = document.getElementById('listening-tbody');
    const countNotice = document.getElementById('count-notice');
    const countWarn = document.getElementById('count-warn');
    const countDisposed = document.getElementById('count-disposed');
    const detailPlaceholder = document.getElementById('detail-placeholder');
    const detailCard = document.getElementById('detail-card');
    const detailSection = document.getElementById('detail-section');
    const statusText = document.getElementById('status-text');

    // 全局資料狀態
    let allStocks = [];
    let listeningStocks = [];
    let filteredWarningStocks = [];
    let filteredDisposedStocks = [];
    let selectedStockCode = null;
    let dispositionTargets = [];

    // 日期解析輔助函式 (民國日期 -> JavaScript Date)
    function parseRocDateToDate(dateStr) {
        if (!dateStr) return null;
        let m = dateStr.match(/^(\d{2,3})[/\.\-](\d{2})[/\.\-](\d{2})$/);
        if (m) {
            let yr = parseInt(m[1], 10);
            if (yr < 100) yr += 100;
            return new Date(yr + 1911, parseInt(m[2], 10) - 1, parseInt(m[3], 10));
        }
        m = dateStr.match(/^(\d{2,3})(\d{2})(\d{2})$/);
        if (m) {
            let yr = parseInt(m[1], 10);
            if (yr < 100) yr += 100;
            return new Date(yr + 1911, parseInt(m[2], 10) - 1, parseInt(m[3], 10));
        }
        return null;
    }

    // 處置狀態判定邏輯
    function getDispositionStatus(periodStr) {
        if (!periodStr) return { text: "🔒 處置中", tag: "disposed" };
        
        let regex = /(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})/g;
        let dates = periodStr.match(regex);
        if (dates && dates.length >= 2) {
            let startDate = parseRocDateToDate(dates[0]);
            let endDate = parseRocDateToDate(dates[1]);
            if (startDate && endDate) {
                let today = new Date();
                today.setHours(0, 0, 0, 0);
                
                if (today < startDate) {
                    return { text: "⏳ 即將處置", tag: "upcoming" };
                }
                
                let diffTime = endDate.getTime() - today.getTime();
                let diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                if (diffDays >= 0 && diffDays <= 1) {
                    return { text: "🔓 即將解禁", tag: "release" };
                }
                return { text: "🔒 處置中", tag: "disposed" };
            }
        }
        return { text: "🔒 處置中", tag: "disposed" };
    }

    // 從本地 JSON 載入數據
    async function loadData() {
        try {
            statusText.textContent = "正在載入預警數據...";
            
            // 嘗試載入黃金多方目標價
            try {
                const targetsRes = await fetch('db/targets.json?t=' + new Date().getTime());
                if (targetsRes.ok) {
                    dispositionTargets = await targetsRes.json();
                    console.log("成功載入處置黃金目標價:", dispositionTargets);
                }
            } catch (e) {
                console.warn("未能載入 db/targets.json (可能尚未計算):", e);
            }

            // 嘗試載入聽牌監控數據
            try {
                const listeningRes = await fetch('db/listening_data.json?t=' + new Date().getTime());
                if (listeningRes.ok) {
                    const data = await listeningRes.json();
                    listeningStocks = data.listening_stocks || [];
                    console.log("成功載入聽牌股監控:", listeningStocks);
                }
            } catch (e) {
                console.warn("未能載入 db/listening_data.json (可能尚未執行預測):", e);
            }

            // 讀取相對路徑的資料庫
            const response = await fetch('db/dashboard_data.json');
            if (!response.ok) {
                throw new Error("無法讀取 db/dashboard_data.json，請確認分析指令已執行。");
            }
            allStocks = await response.json();
            statusText.textContent = `載入成功。共有 ${allStocks.length} 檔連續注意/處置，${listeningStocks.length} 檔聽牌監控個股。`;
            applyFilters();
            
            // 預設選取第一選中的列 (優先聽牌股，其次預警股，再者處置股)
            const firstListRow = listeningTbody.querySelector('tr[data-code]');
            if (firstListRow) {
                firstListRow.click();
            } else {
                const firstRow = warningTbody.querySelector('tr[data-code]');
                if (firstRow) {
                    firstRow.click();
                } else {
                    const firstDispRow = disposedTbody.querySelector('tr[data-code]');
                    if (firstDispRow) firstDispRow.click();
                }
            }
        } catch (error) {
            console.error(error);
            statusText.textContent = `錯誤: ${error.message}`;
            warningTbody.innerHTML = `<tr><td colspan="7" class="placeholder-row">⚠️ 載入失敗: ${error.message}</td></tr>`;
            disposedTbody.innerHTML = `<tr><td colspan="6" class="placeholder-row">⚠️ 載入失敗: ${error.message}</td></tr>`;
        }
    }

    // 套用過濾器與搜尋
    function applyFilters() {
        const searchQuery = searchInput.value.trim().toUpperCase();
        const marketQuery = marketFilter.value;

        // 清空列表
        warningTbody.innerHTML = '';
        disposedTbody.innerHTML = '';
        listeningTbody.innerHTML = '';

        filteredWarningStocks = [];
        filteredDisposedStocks = [];
        let filteredListeningStocks = [];

        allStocks.forEach(stock => {
            const code = stock.Code || "";
            const name = stock.Name || "";
            const market = stock.Market || "";

            // 搜尋過濾
            if (searchQuery && !code.includes(searchQuery) && !name.includes(searchQuery)) {
                return;
            }
            // 市場過濾
            if (marketQuery !== "全部" && market !== marketQuery) {
                return;
            }

            const isDisposed = stock.IsDisposed || false;
            const disposedPeriod = stock.DisposedPeriod || "";
            
            let closeVal = stock.Close || "N/A";
            let closeStr = closeVal === "N/A" ? "N/A" : `${parseFloat(closeVal.replace(/,/g, '')).toFixed(2)} 元`;

            if (isDisposed) {
                filteredDisposedStocks.push(stock);
                const status = getDispositionStatus(disposedPeriod);
                
                // 尋找 targets.json 中對應的黃金目標價
                const tgt = dispositionTargets.find(t => t.code === code);
                let targetPriceStr = code.length === 4 ? "N/A" : `<span style="color: var(--text-secondary); font-size: 0.8rem;">— (衍生品)</span>`;
                if (tgt) {
                    if (tgt.target_price === "WAITING_FOR_OPEN") {
                        targetPriceStr = `<span style="color: var(--fg-secondary); font-style: italic; font-size: 0.8rem;">待開盤</span>`;
                    } else {
                        targetPriceStr = `<strong style="color: var(--color-green); font-family: 'Outfit', monospace; font-size: 0.95rem; text-shadow: 0 0 10px rgba(0, 255, 102, 0.2);">${parseFloat(tgt.target_price).toFixed(2)} 元</strong>`;
                    }
                }
                
                const tr = document.createElement('tr');
                tr.setAttribute('data-code', code);
                tr.classList.add(`${status.tag}-row`);
                if (selectedStockCode === code) tr.classList.add('selected-row');

                tr.innerHTML = `
                    <td>${code}</td>
                    <td>${name}</td>
                    <td class="text-center">${market}</td>
                    <td class="text-right">${closeStr}</td>
                    <td class="text-right">${targetPriceStr}</td>
                    <td>${disposedPeriod}</td>
                    <td class="text-center"><span class="status-badge ${status.tag}">${status.text}</span></td>
                `;
                
                tr.addEventListener('click', () => selectStock(stock, tr, 'disposed'));
                disposedTbody.appendChild(tr);
            } else {
                filteredWarningStocks.push(stock);
                
                // 尋找最易觸發價格距離
                let minAbsChange = 9999.0;
                let hasGuaranteedTrigger = false;
                const calcs = stock.Calculations || [];
                
                calcs.forEach(calc => {
                    const upChg = calc.TargetUpChange;
                    const downChg = calc.TargetDownChange;
                    const isPrimary = calc.IsPrimary || false;
                    
                    if (upChg !== null && upChg !== undefined) {
                        if (upChg >= -10.0 && upChg <= 10.0) {
                            let val = (upChg <= 0 && isPrimary) ? 0.0 : Math.abs(upChg);
                            minAbsChange = Math.min(minAbsChange, val);
                        } else if (upChg < -10.0 && isPrimary) {
                            hasGuaranteedTrigger = true;
                            minAbsChange = 0.0;
                        }
                    }
                    if (downChg !== null && downChg !== undefined) {
                        if (downChg >= -10.0 && downChg <= 10.0) {
                            let val = (downChg >= 0 && isPrimary) ? 0.0 : Math.abs(downChg);
                            minAbsChange = Math.min(minAbsChange, val);
                        } else if (downChg > 10.0 && isPrimary) {
                            hasGuaranteedTrigger = true;
                            minAbsChange = 0.0;
                        }
                    }
                });

                let tag = "normal";
                let statusText = "正常";
                if (hasGuaranteedTrigger) {
                    statusText = "🚨 必定觸發";
                    tag = "guaranteed";
                } else if (minAbsChange <= 1.0) {
                    statusText = "💥 極易觸發";
                    tag = "extreme";
                } else if (minAbsChange <= 5.0) {
                    statusText = "⚠️ 重點監控";
                    tag = "warn";
                }

                // 決定顯示的最易觸發價
                let triggerPriceStr = "無價格觸發";
                let primaryCalc = calcs.find(c => c.IsPrimary) || calcs[0];
                
                if (primaryCalc) {
                    const upP = primaryCalc.TargetUpPrice;
                    const upChg = primaryCalc.TargetUpChange;
                    const downP = primaryCalc.TargetDownPrice;
                    const downChg = primaryCalc.TargetDownChange;

                    let useUp = true;
                    if (upChg !== null && downChg !== null) {
                        let effUp = upChg <= 0 ? 0.0 : Math.abs(upChg);
                        let effDown = downChg >= 0 ? 0.0 : Math.abs(downChg);
                        if (effDown < effUp) useUp = false;
                    } else if (upChg === null && downChg !== null) {
                        useUp = false;
                    }

                    if (useUp && upP !== null && upChg !== null) {
                        if (upChg <= 0) {
                            triggerPriceStr = `已達標 (不跌破 ${upP.toFixed(2)})`;
                        } else if (upChg <= 10.0) {
                            triggerPriceStr = `${upP.toFixed(2)} 元 (${upChg > 0 ? '+' : ''}${upChg.toFixed(2)}%)`;
                        }
                    } else if (!useUp && downP !== null && downChg !== null) {
                        if (downChg >= 0) {
                            triggerPriceStr = `已達標 (不漲破 ${downP.toFixed(2)})`;
                        } else if (downChg >= -10.0) {
                            triggerPriceStr = `${downP.toFixed(2)} 元 (${downChg > 0 ? '+' : ''}${downChg.toFixed(2)}%)`;
                        }
                    }
                }

                // 推算今日成交張數 (從價格快取中尋找今日量)
                let volLots = "N/A";
                // 這裡僅留作空值，後續由 JS 或 PS 已經寫入的欄位來填充更佳。因網頁版無法直接存取 prices_cache.json（除非發起 fetch）
                // 為了效能，我們簡化顯示，或後續加載
                
                const tr = document.createElement('tr');
                tr.setAttribute('data-code', code);
                tr.classList.add(`${tag}-row`);
                if (selectedStockCode === code) tr.classList.add('selected-row');

                tr.innerHTML = `
                    <td>${code}</td>
                    <td>${name}</td>
                    <td class="text-center">${market}</td>
                    <td class="text-right">${closeStr}</td>
                    <td class="text-right" data-role="vol-placeholder">...張</td>
                    <td class="text-right">${triggerPriceStr}</td>
                    <td class="text-center"><span class="status-badge ${tag}">${statusText}</span></td>
                `;

                tr.addEventListener('click', () => selectStock(stock, tr, 'warning'));
                warningTbody.appendChild(tr);
            }
        });
        // 渲染聽牌股列表
        listeningStocks.forEach(stock => {
            const code = stock.code || "";
            const name = stock.name || "";
            const market = stock.market || "";

            // 搜尋過濾
            if (searchQuery && !code.includes(searchQuery) && !name.includes(searchQuery)) {
                return;
            }
            // 市場過濾
            if (marketQuery !== "全部" && market !== marketQuery) {
                return;
            }

            filteredListeningStocks.push(stock);

            // 價格門檻顯示
            const pCalc = stock.best_price_calc;
            let priceThresholdStr = "N/A";
            let priceClass = "";
            let changeVal = 999.0;
            if (pCalc) {
                const dir = pCalc.dir;
                const price = pCalc.price;
                const change = pCalc.change;
                changeVal = change;
                priceThresholdStr = `${dir} ${price.toFixed(2)}元 (${change >= 0 ? '+' : ''}${change.toFixed(2)}%)`;
                priceClass = dir === "▲" ? "up-val" : "down-val";
            }

            // 成交量門檻顯示
            let volThresholdStr = "N/A";
            if (stock.trigger_vol_val > 0) {
                volThresholdStr = `${(stock.trigger_vol_val / 1000).toLocaleString(undefined, {maximumFractionDigits: 0})} 張`;
            } else if (stock.trigger_vol_rule === "任意成交量皆會觸發 (前5日已達標)") {
                volThresholdStr = "任意量";
            }

            // 狀態 badge
            let badgeClass = "normal";
            let badgeText = "監控中";
            if (Math.abs(changeVal) <= 1.0) {
                badgeClass = "extreme";
                badgeText = "🔥 極易觸發";
            } else if (Math.abs(changeVal) <= 4.0) {
                badgeClass = "warn";
                badgeText = "⚠️ 重點預警";
            }

            const tr = document.createElement('tr');
            tr.setAttribute('data-code', code);
            tr.classList.add('listening-row');
            if (selectedStockCode === code) tr.classList.add('selected-row');

            const yesterdayClose = stock.yesterday_close || 0;
            const currentClose = stock.current_close || 0;
            const currentVol = stock.current_vol || 0;

            tr.innerHTML = `
                <td><strong>${code}</strong></td>
                <td>${name}</td>
                <td class="text-center">${market}</td>
                <td class="text-right">${yesterdayClose.toFixed(2)} 元</td>
                <td class="text-right"><strong>${currentClose.toFixed(2)} 元</strong></td>
                <td class="text-right">${(currentVol / 1000).toLocaleString(undefined, {maximumFractionDigits: 0})} 張</td>
                <td class="text-right ${priceClass}" style="font-weight: 600;">${priceThresholdStr}</td>
                <td class="text-right" style="color: var(--fg-accent-cyan); font-size: 0.9rem;">${volThresholdStr}</td>
                <td class="text-center"><span class="status-badge ${badgeClass}">${badgeText}</span></td>
            `;

            tr.addEventListener('click', () => selectStock(stock, tr, 'listening'));
            listeningTbody.appendChild(tr);
        });

        if (filteredListeningStocks.length === 0) {
            listeningTbody.innerHTML = `<tr><td colspan="9" class="placeholder-row">☕ 當前無符合過濾條件的聽牌股票</td></tr>`;
        }

        // 異步非同步抓取快取以填補成交量張數 (避免阻塞渲染)
        loadVolumes();

        // 填補空行提示
        if (warningTbody.children.length === 0) {
            warningTbody.innerHTML = `<tr><td colspan="7" class="placeholder-row">無符合篩選條件的預警股</td></tr>`;
        }
        if (disposedTbody.children.length === 0) {
            disposedTbody.innerHTML = `<tr><td colspan="6" class="placeholder-row">無符合篩選條件的處置股</td></tr>`;
        }

        // 更新統計卡片
        const numWarning = filteredWarningStocks.length;
        const numDisposed = filteredDisposedStocks.length;
        
        let numExtremeWarn = 0;
        filteredWarningStocks.forEach(stock => {
            let minAbs = 9999.0;
            let guaranteed = false;
            (stock.Calculations || []).forEach(calc => {
                const upChg = calc.TargetUpChange;
                const downChg = calc.TargetDownChange;
                const isPrimary = calc.IsPrimary || false;
                if (upChg !== null) {
                    if (upChg >= -10.0 && upChg <= 10.0) {
                        let val = (upChg <= 0 && isPrimary) ? 0.0 : Math.abs(upChg);
                        minAbs = Math.min(minAbs, val);
                    } else if (upChg < -10.0 && isPrimary) {
                        guaranteed = true;
                    }
                }
                if (downChg !== null) {
                    if (downChg >= -10.0 && downChg <= 10.0) {
                        let val = (downChg >= 0 && isPrimary) ? 0.0 : Math.abs(downChg);
                        minAbs = Math.min(minAbs, val);
                    } else if (downChg > 10.0 && isPrimary) {
                        guaranteed = true;
                    }
                }
            });
            if (guaranteed || minAbs <= 5.0) {
                numExtremeWarn++;
            }
        });

        countNotice.textContent = `${numWarning} 檔`;
        countWarn.textContent = `${numExtremeWarn} 檔`;
        countDisposed.textContent = `${numDisposed} 檔`;
    }

    // 異步加載成交量快取
    async function loadVolumes() {
        try {
            const response = await fetch('db/prices_cache.json');
            if (!response.ok) return;
            const cache = await response.json();
            
            // 更新 Warning 表格的成交量
            const rows = warningTbody.querySelectorAll('tr[data-code]');
            rows.forEach(row => {
                const code = row.getAttribute('data-code');
                const volCell = row.querySelector('[data-role="vol-placeholder"]');
                if (volCell && cache[code] && cache[code].prices.length > 0) {
                    const lastPrice = cache[code].prices[cache[code].prices.length - 1];
                    const vol = lastPrice.Volume || lastPrice.volume || 0;
                    const lots = Math.round(vol / 1000);
                    volCell.textContent = `${lots.toLocaleString()} 張`;
                } else if (volCell) {
                    volCell.textContent = "N/A";
                }
            });
        } catch (e) {
            console.warn("Failed to load volumes cache:", e);
        }
    }

    // 處理個股選取與切換
    function selectStock(stock, trElement, tableType) {
        selectedStockCode = stock.Code || stock.code;
        
        // 清除所有選取狀態
        const allRows = document.querySelectorAll('tbody tr');
        allRows.forEach(r => r.classList.remove('selected-row'));
        
        // 設定選取樣式
        trElement.classList.add('selected-row');

        // 渲染詳細卡片
        renderDetailCard(stock, tableType);

        // 行動裝置滾動
        if (window.innerWidth <= 1024) {
            detailSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    // 渲染詳細面板 HTML
    async function renderDetailCard(stock, tableType) {
        detailPlaceholder.classList.add('hidden');
        detailCard.classList.remove('hidden');

        const code = stock.Code || stock.code || "";
        const name = stock.Name || stock.name || "";
        const market = stock.Market || stock.market || "";
        const close = stock.Close || (stock.current_close !== undefined ? stock.current_close.toString() : "") || "";
        const reason = stock.Reason || stock.yesterday_reason || "";
        const isDisposed = stock.IsDisposed || false;
        
        let closePriceStr = close === "N/A" || close === "" ? "N/A" : `${parseFloat(close.replace(/,/g, '')).toFixed(2)} 元`;

        if (tableType === 'listening') {
            const reasons = stock.reasons || [];
            const reasonsHtml = reasons.map(r => `• ${r}`).join('<br>');
            const yesterdayClose = stock.yesterday_close || 0;
            const currentClose = stock.current_close || 0;
            const currentVol = stock.current_vol || 0;
            
            let priceThresholdHtml = '';
            (stock.price_thresholds || []).forEach(pt => {
                const rule = pt.rule || "";
                const base = pt.base_price || 0;
                const upP = pt.up_price || 0;
                const downP = pt.down_price;
                const isPrimary = pt.is_primary || false;
                
                let upNote = '';
                const upChg = ((upP - currentClose) / currentClose) * 100.0;
                let upClass = 'up-val';
                if (upChg > 10.0) {
                    upNote = ' <span class="status-badge normal" style="padding: 1px 4px; font-size: 0.68rem;">超漲停限制 +10%</span>';
                } else if (upChg <= 0 && isPrimary) {
                    upNote = ' <span class="status-badge release" style="padding: 1px 4px; font-size: 0.68rem;">🚨 已達標</span>';
                    upClass = 'up-val guaranteed';
                } else if (upChg <= 1.0) {
                    upNote = ' <span class="status-badge extreme" style="padding: 1px 4px; font-size: 0.68rem;">🔥 極易觸發</span>';
                } else if (upChg <= 5.0) {
                    upNote = ' <span class="status-badge warn" style="padding: 1px 4px; font-size: 0.68rem;">⚠️ 重點監控</span>';
                }
                
                let downHtml = '';
                if (downP !== null) {
                    const downChg = ((downP - currentClose) / currentClose) * 100.0;
                    let downNote = '';
                    let downClass = 'down-val';
                    if (downChg < -10.0) {
                        downNote = ' <span class="status-badge normal" style="padding: 1px 4px; font-size: 0.68rem;">超跌停限制 -10%</span>';
                    } else if (downChg >= 0 && isPrimary) {
                        downNote = ' <span class="status-badge release" style="padding: 1px 4px; font-size: 0.68rem;">🚨 已達標</span>';
                    }
                    downHtml = `<div class="${downClass}">▼ 看跌觸發價: <strong>${downP.toFixed(2)} 元</strong> (跌幅需求: ${downChg.toFixed(2)}%)${downNote}</div>`;
                }
                
                priceThresholdHtml += `
                    <div class="threshold-row">
                        <div class="threshold-rule">${isPrimary ? '⭐ ' : '  '}${rule}</div>
                        <div style="font-size: 0.75rem; color: var(--fg-secondary); margin-bottom: 4px;">基準價: ${base.toFixed(2)} 元</div>
                        <div class="threshold-values">
                            <div class="${upClass}">▲ 看漲觸發價: <strong>${upP.toFixed(2)} 元</strong> (漲幅需求: ${upChg > 0 ? '+' : ''}${upChg.toFixed(2)}%)${upNote}</div>
                            ${downHtml}
                        </div>
                    </div>
                `;
            });
            
            let volumeThresholdHtml = '';
            (stock.vol_thresholds || []).forEach(vt => {
                const rule = vt.rule || "";
                const trigger = vt.trigger_vol || 0;
                let trigText = '';
                if (trigger <= 0) {
                    trigText = '<strong class="vol-val">任意成交量皆會觸發！</strong> (今日已達標)';
                } else {
                    const lots = Math.round(trigger / 1000);
                    trigText = `觸發張數: <strong class="vol-val">${lots.toLocaleString()} 張</strong> (${parseInt(trigger).toLocaleString()} 股)`;
                }
                volumeThresholdHtml += `
                    <div class="threshold-row">
                        <div class="threshold-rule">${rule}</div>
                        <div class="threshold-values" style="font-size: 0.8rem;">
                            <div>${trigText}</div>
                        </div>
                    </div>
                `;
            });
            if (volumeThresholdHtml === '') {
                volumeThresholdHtml = '<p class="detail-text" style="font-style: italic;">本檔個股無特殊量變動公告，預設採用 60日均量 5 倍保底門檻。</p>';
            }
            
            detailCard.innerHTML = `
                <div>
                    <h2 class="detail-title">[${code}] ${name} (${market})</h2>
                    <p class="detail-subtitle">昨日收盤價: <strong>${yesterdayClose.toFixed(2)} 元</strong> | 今日最新: <strong>${currentClose.toFixed(2)} 元</strong></p>
                    <p class="detail-subtitle" style="margin-top: 5px;">今日成交量: <strong>${(currentVol/1000).toLocaleString(undefined, {maximumFractionDigits:0})} 張</strong></p>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block" id="kline-container">
                    <h3 class="detail-section-title">📊 股價歷史走勢與注意門檻</h3>
                    <div id="chart-loading" style="text-align: center; padding: 20px; color: var(--text-secondary); font-size: 0.85rem;">正在從 Yahoo Finance 獲取即時 K 線...</div>
                    <canvas id="kline-canvas" class="hidden" style="width: 100%; height: 180px; background: rgba(0,0,0,0.15); border-radius: 8px; border: 1px solid var(--border-color); margin-top: 10px;"></canvas>
                    <div id="chart-legend" class="hidden" style="display: flex; gap: 15px; font-size: 0.75rem; justify-content: center; margin-top: 5px; color: var(--text-secondary);">
                        <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #ef4444;"></span> 今日看漲門檻</span>
                        <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #10b981;"></span> 今日看跌門檻</span>
                    </div>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">🔥 處置聽牌狀態</h3>
                    <p class="detail-text" style="color: var(--color-yellow); font-weight: 600;">滿足背景原因：</p>
                    <p class="detail-text" style="font-size: 0.85rem; color: var(--fg-secondary); white-space: pre-wrap;">${reasonsHtml}</p>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">📢 昨日公告注意原因</h3>
                    <p class="detail-text" style="font-size: 0.85rem; white-space: pre-wrap;">${stock.yesterday_reason ? stock.yesterday_reason.replace(/﹝/g, '[').replace(/﹞/g, ']') : '無歷史公告原因'}</p>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">🎯 今日價格注意門檻 (收盤價逆推)</h3>
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        ${priceThresholdHtml}
                    </div>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">⚡ 今日成交量注意門檻</h3>
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        ${volumeThresholdHtml}
                    </div>
                </div>
            `;
            
            const mappedCalcs = (stock.price_thresholds || []).map(pt => ({
                Rule: pt.rule,
                BasePrice: pt.base_price,
                TargetUpPrice: pt.up_price,
                TargetUpChange: ((pt.up_price - currentClose) / currentClose) * 100.0,
                TargetDownPrice: pt.down_price,
                TargetDownChange: pt.down_price ? ((pt.down_price - currentClose) / currentClose) * 100.0 : null,
                IsPrimary: pt.is_primary
            }));
            loadAndDrawChart(code, market, false, "", "", mappedCalcs);
            return;
        }

        if (isDisposed) {
            const disposedPeriod = stock.DisposedPeriod || "";
            const status = getDispositionStatus(disposedPeriod);
            
            let statusText = status.text;
            let statusClass = status.tag;
            
            let extraInfoHtml = "";
            let regex = /(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})/g;
            let dates = disposedPeriod.match(regex);
            if (dates && dates.length >= 2) {
                let startDate = parseRocDateToDate(dates[0]);
                let endDate = parseRocDateToDate(dates[1]);
                if (startDate && endDate) {
                    let today = new Date();
                    today.setHours(0,0,0,0);
                    if (today < startDate) {
                        let diff = Math.ceil((startDate - today) / (1000 * 60 * 60 * 24));
                        extraInfoHtml = `<div class="status-badge upcoming" style="margin-top:5px; display:inline-block;">● 距離處置開始還有 ${diff} 天</div>`;
                    } else if (today <= endDate) {
                        let diff = Math.ceil((endDate - today) / (1000 * 60 * 60 * 24));
                        let alertHtml = diff <= 1 ? `<div class="status-badge release" style="margin-top:5px; display:inline-block;">📢 提醒：此有價證券即將於近日解禁，請密切關注！</div>` : "";
                        extraInfoHtml = `
                            <div class="status-badge disposed" style="margin-top:5px; display:inline-block;">● 處置執行中，距離解禁還有 ${diff} 天</div>
                            ${alertHtml}
                        `;
                    }
                }
            }

            detailCard.innerHTML = `
                <div>
                    <h2 class="detail-title">[${code}] ${name} (${market})</h2>
                    <p class="detail-subtitle">今日收盤價: <strong>${closePriceStr}</strong></p>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">🔒 處置監控細節</h3>
                    <p class="detail-text">處置狀態: <span class="status-badge ${statusClass}">${statusText}</span></p>
                    <p class="detail-text">處置期間: <strong>${disposedPeriod}</strong></p>
                    ${extraInfoHtml}
                    <div id="disp-calc-placeholder"></div>
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block" id="kline-container">
                    <h3 class="detail-section-title">📊 股價歷史與黃金回測線</h3>
                    ${code.length === 4 ? `
                    <div id="chart-loading" style="text-align: center; padding: 20px; color: var(--text-secondary); font-size: 0.85rem;">正在從 Yahoo Finance 獲取即時 K 線...</div>
                    <canvas id="kline-canvas" class="hidden" style="width: 100%; height: 180px; background: rgba(0,0,0,0.15); border-radius: 8px; border: 1px solid var(--border-color); margin-top: 10px;"></canvas>
                    <div id="chart-legend" class="hidden" style="display: flex; gap: 15px; font-size: 0.75rem; justify-content: center; margin-top: 5px; color: var(--text-secondary);">
                        <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #00bfff;"></span> 放空基準線</span>
                        <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #ef4444;"></span> 黃金目標價</span>
                    </div>
                    ` : `
                    <div style="text-align: center; padding: 30px 20px; color: var(--text-secondary); font-size: 0.85rem; border: 1px dashed var(--border-color); border-radius: 8px;">
                        ⚠️ 此商品為權證/可轉債等衍生性金融商品，無普通股日 K 線圖與黃金目標價。請參考其標的股票。
                    </div>
                    `}
                </div>
                <div class="detail-divider"></div>
                <div class="detail-block">
                    <h3 class="detail-section-title">📢 處置公告原因與措施</h3>
                    <p class="detail-text" style="white-space: pre-wrap; font-size: 0.85rem;">${reason.replace(/﹝/g, '[').replace(/﹞/g, ']')}</p>
                </div>
            `;
            if (code.length === 4) {
                loadAndDrawChart(code, market, true, disposedPeriod, reason, []);
            }
            return;
        }

        let volStr = "載入中...";
        try {
            const cacheResponse = await fetch('db/prices_cache.json');
            if (cacheResponse.ok) {
                const cache = await cacheResponse.json();
                if (cache[code] && cache[code].prices.length > 0) {
                    const lastVol = cache[code].prices[cache[code].prices.length - 1].Volume || 0;
                    volStr = `${lastVol.toLocaleString()} 股 (約 ${Math.round(lastVol/1000).toLocaleString()} 張)`;
                }
            }
        } catch(e) {
            volStr = "N/A (載入失敗)";
        }

        let priceHtml = '';
        const calcs = stock.Calculations || [];
        calcs.forEach(calc => {
            const rule = calc.Rule || "";
            const base = calc.BasePrice || 0;
            const upP = calc.TargetUpPrice || 0;
            const upChg = calc.TargetUpChange;
            const downP = calc.TargetDownPrice;
            const downChg = calc.TargetDownChange;
            const isPrimary = calc.IsPrimary || false;

            let upNote = '';
            let upClass = 'up-val';
            if (upChg > 10.0) {
                upNote = ' <span class="status-badge normal" style="padding: 1px 4px; font-size: 0.68rem;">超漲停限制 +10%</span>';
            } else if (upChg <= 0 && isPrimary) {
                upNote = ' <span class="status-badge guaranteed" style="padding: 1px 4px; font-size: 0.68rem;">🚨 必定觸發</span>';
                upClass = 'up-val guaranteed';
            } else if (upChg <= 5.0) {
                upNote = ' <span class="status-badge extreme" style="padding: 1px 4px; font-size: 0.68rem;">🔥 極易觸發</span>';
            }

            let downNote = '';
            let downClass = 'down-val';
            let downHtml = '';
            if (downP !== null && downChg !== null) {
                if (downChg < -10.0) {
                    downNote = ' <span class="status-badge normal" style="padding: 1px 4px; font-size: 0.68rem;">超跌停限制 -10%</span>';
                } else if (downChg >= 0 && isPrimary) {
                    downNote = ' <span class="status-badge guaranteed" style="padding: 1px 4px; font-size: 0.68rem;">🚨 必定觸發</span>';
                }
                downHtml = `<div class="${downClass}">▼ 看跌觸發價: <strong>${downP.toFixed(2)} 元</strong> (跌幅需求: ${downChg.toFixed(2)}%)${downNote}</div>`;
            }

            priceHtml += `
                <div class="threshold-row">
                    <div class="threshold-rule">${isPrimary ? '⭐ ' : '  '}${rule}</div>
                    <div style="font-size: 0.75rem; color: var(--fg-secondary); margin-bottom: 4px;">基準價: ${base.toFixed(2)} 元</div>
                    <div class="threshold-values">
                        <div class="${upClass}">▲ 看漲觸發價: <strong>${upP.toFixed(2)} 元</strong> (漲幅需求: ${upChg > 0 ? '+' : ''}${upChg.toFixed(2)}%)${upNote}</div>
                        ${downHtml}
                    </div>
                </div>
            `;
        });

        let volumeHtml = '';
        const vCalcs = stock.VolumeCalculations || [];
        if (vCalcs.length > 0) {
            vCalcs.forEach(vCalc => {
                const rule = vCalc.Rule || "";
                const trigger = vCalc.TriggerVolume || 0;
                let trigText = '';
                if (trigger <= 0) {
                    trigText = '<strong class="vol-val">任意成交量皆會觸發！</strong> (今日已達標)';
                } else {
                    const lots = Math.round(trigger / 1000);
                    trigText = `觸發張數: <strong class="vol-val">${lots.toLocaleString()} 張</strong> (${parseInt(trigger).toLocaleString()} 股)`;
                }
                volumeHtml += `
                    <div class="threshold-row">
                        <div class="threshold-rule">${rule}</div>
                        <div class="threshold-values" style="font-size: 0.8rem;">
                            <div>${trigText}</div>
                        </div>
                    </div>
                `;
            });
        } else {
            volumeHtml = '<p class="detail-text" style="font-style: italic;">本檔個股查無歷史股數，僅推算 60日均量 5 倍保底門檻。</p>';
        }

        detailCard.innerHTML = `
            <div>
                <h2 class="detail-title">[${code}] ${name} (${market})</h2>
                <p class="detail-subtitle">今日收盤價: <strong>${closePriceStr}</strong> | 今日成交量: <span id="detail-vol-val">${volStr}</span></p>
            </div>
            <div class="detail-divider"></div>
            <div class="detail-block" id="kline-container">
                <h3 class="detail-section-title">📊 股價歷史走勢與注意門檻</h3>
                <div id="chart-loading" style="text-align: center; padding: 20px; color: var(--text-secondary); font-size: 0.85rem;">正在從 Yahoo Finance 獲取即時 K 線...</div>
                <canvas id="kline-canvas" class="hidden" style="width: 100%; height: 180px; background: rgba(0,0,0,0.15); border-radius: 8px; border: 1px solid var(--border-color); margin-top: 10px;"></canvas>
                <div id="chart-legend" class="hidden" style="display: flex; gap: 15px; font-size: 0.75rem; justify-content: center; margin-top: 5px; color: var(--text-secondary);">
                    <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #ef4444;"></span> 明日看漲門檻</span>
                    <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 10px; height: 1px; border-bottom: 2px dashed #10b981;"></span> 明日看跌門檻</span>
                </div>
            </div>
            <div class="detail-divider"></div>
            <div class="detail-block">
                <h3 class="detail-section-title">📢 今日公告注意原因</h3>
                <p class="detail-text" style="font-size: 0.85rem;">${reason.replace(/﹝/g, '[').replace(/﹞/g, ']')}</p>
            </div>
            <div class="detail-divider"></div>
            <div class="detail-block">
                <h3 class="detail-section-title">🎯 明日價格注意門檻 (收盤價預估)</h3>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${priceHtml}
                </div>
            </div>
            <div class="detail-divider"></div>
            <div class="detail-block">
                <h3 class="detail-section-title">⚡ 明日成交量注意門檻</h3>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${volumeHtml}
                </div>
            </div>
        `;
        loadAndDrawChart(code, market, false, "", "", calcs);
    }

    // 註冊搜尋與過濾事件監聽
    searchInput.addEventListener('input', applyFilters);
    marketFilter.addEventListener('change', applyFilters);

    // 啟動加載
    loadData();
    
    // --- 以下為黃金目標價與 K線圖 擴充函式 ---
    
    // 1. 台股 Tick Size 四捨五入
    function roundToValidTick(price) {
        if (price <= 0) return 0.01;
        let tick;
        if (price < 10) tick = 0.01;
        else if (price < 50) tick = 0.05;
        else if (price < 100) tick = 0.1;
        else if (price < 500) tick = 0.5;
        else if (price < 1000) tick = 1.0;
        else tick = 5.0;
        
        let rounded = Math.round(price / tick) * tick;
        if (tick === 0.01 || tick === 0.05) return parseFloat(rounded.toFixed(2));
        if (tick === 0.1 || tick === 0.5) return parseFloat(rounded.toFixed(1));
        return parseFloat(rounded.toFixed(0));
    }

    // 2. 解析 Yahoo Finance JSON 數據為結構化日K線
    function parseYahooData(data) {
        const result = data.chart.result[0];
        const timestamps = result.timestamp || [];
        const quote = result.indicators.quote[0];
        const opens = quote.open || [];
        const highs = quote.high || [];
        const lows = quote.low || [];
        const closes = quote.close || [];
        const volumes = quote.volume || [];
        
        const history = [];
        for (let i = 0; i < timestamps.length; i++) {
            if (opens[i] === null || closes[i] === null || highs[i] === null || lows[i] === null) continue;
            const d = new Date(timestamps[i] * 1000);
            const dStr = d.toISOString().split('T')[0];
            history.push({
                dateStr: dStr,
                dateObj: d,
                open: opens[i],
                high: highs[i],
                low: lows[i],
                close: closes[i],
                volume: volumes[i]
            });
        }
        history.sort((a, b) => a.dateObj - b.dateObj);
        return history;
    }

    // 3. 繪製日K線蠟燭圖 (Canvas)
    function drawCandlestickChart(canvas, history, options = {}) {
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
        
        const width = rect.width;
        const height = rect.height;
        ctx.clearRect(0, 0, width, height);
        
        const marginTop = 15;
        const marginBottom = 18;
        const marginLeft = 10;
        const marginRight = 50;
        
        const chartWidth = width - marginLeft - marginRight;
        const chartHeight = height - marginTop - marginBottom;
        
        if (history.length === 0) return;
        
        // 顯示最後 30 根 K 線
        const displayCount = Math.min(30, history.length);
        const visibleData = history.slice(-displayCount);
        
        let maxPrice = -Infinity;
        let minPrice = Infinity;
        
        visibleData.forEach(bar => {
            if (bar.high > maxPrice) maxPrice = bar.high;
            if (bar.low < minPrice) minPrice = bar.low;
        });
        
        const refLines = options.refLines || [];
        refLines.forEach(line => {
            if (line.price > maxPrice) maxPrice = line.price;
            if (line.price < minPrice) minPrice = line.price;
        });
        
        const priceRange = maxPrice - minPrice;
        const padding = priceRange * 0.08 || 1;
        maxPrice += padding;
        minPrice -= padding;
        
        // 繪製網格線
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.font = '9px Outfit, Noto Sans TC, sans-serif';
        ctx.fillStyle = '#9ca3af';
        ctx.textAlign = 'left';
        
        const gridCount = 4;
        for (let i = 0; i <= gridCount; i++) {
            const yPrice = minPrice + (maxPrice - minPrice) * (i / gridCount);
            const y = marginTop + chartHeight * (1 - i / gridCount);
            
            ctx.beginPath();
            ctx.moveTo(marginLeft, y);
            ctx.lineTo(marginLeft + chartWidth, y);
            ctx.stroke();
            
            ctx.fillText(yPrice.toFixed(2), marginLeft + chartWidth + 5, y + 3);
        }
        
        // 繪製蠟燭 K 線
        const barWidth = (chartWidth / displayCount) * 0.7;
        const gap = (chartWidth / displayCount) * 0.3;
        
        visibleData.forEach((bar, i) => {
            const x = marginLeft + i * (barWidth + gap) + gap/2;
            
            const yOpen = marginTop + chartHeight * (1 - (bar.open - minPrice) / (maxPrice - minPrice));
            const yClose = marginTop + chartHeight * (1 - (bar.close - minPrice) / (maxPrice - minPrice));
            const yHigh = marginTop + chartHeight * (1 - (bar.high - minPrice) / (maxPrice - minPrice));
            const yLow = marginTop + chartHeight * (1 - (bar.low - minPrice) / (maxPrice - minPrice));
            
            const isUp = bar.close >= bar.open;
            const color = isUp ? '#f43f5e' : '#10b981'; // 台灣紅漲綠跌
            
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.lineWidth = 1.2;
            
            // 繪製影線
            ctx.beginPath();
            ctx.moveTo(x + barWidth/2, yHigh);
            ctx.lineTo(x + barWidth/2, yLow);
            ctx.stroke();
            
            // 繪製實體
            const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
            ctx.fillRect(x, Math.min(yOpen, yClose), barWidth, bodyHeight);
            
            // 日期標籤
            if (i % 8 === 0 || i === displayCount - 1) {
                ctx.fillStyle = '#6b7280';
                ctx.font = '8px Outfit, sans-serif';
                ctx.textAlign = 'center';
                const parts = bar.dateStr.split('-');
                ctx.fillText(`${parts[1]}/${parts[2]}`, x + barWidth/2, height - 2);
            }
            
            // 標記交易點位
            if (options.specialDates && options.specialDates[bar.dateStr]) {
                const marker = options.specialDates[bar.dateStr];
                ctx.fillStyle = marker.color;
                ctx.textAlign = 'center';
                ctx.font = 'bold 9px Noto Sans TC, sans-serif';
                if (marker.type === 'short') {
                    ctx.fillText('▼空', x + barWidth/2, yHigh - 5);
                } else if (marker.type === 'cover') {
                    ctx.fillText('▲多', x + barWidth/2, yLow + 12);
                }
            }
        });
        
        // 繪製基準線與目標線
        refLines.forEach(line => {
            const y = marginTop + chartHeight * (1 - (line.price - minPrice) / (maxPrice - minPrice));
            ctx.strokeStyle = line.color;
            ctx.lineWidth = 1.2;
            ctx.setLineDash([4, 4]);
            
            ctx.beginPath();
            ctx.moveTo(marginLeft, y);
            ctx.lineTo(marginLeft + chartWidth, y);
            ctx.stroke();
            ctx.setLineDash([]);
            
            ctx.fillStyle = line.color;
            ctx.font = 'bold 9px Noto Sans TC, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(line.label, marginLeft + chartWidth - 5, y - 4);
        });
    }

    // 4. 繪製歷史收盤價折線圖 (備用方案，當 Yahoo 連線失敗或離線時)
    function drawClosePriceChart(canvas, history, options = {}) {
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
        
        const width = rect.width;
        const height = rect.height;
        ctx.clearRect(0, 0, width, height);
        
        const marginTop = 15;
        const marginBottom = 18;
        const marginLeft = 10;
        const marginRight = 50;
        
        const chartWidth = width - marginLeft - marginRight;
        const chartHeight = height - marginTop - marginBottom;
        
        const displayCount = Math.min(30, history.length);
        const visibleData = history.slice(-displayCount);
        
        let maxPrice = -Infinity;
        let minPrice = Infinity;
        
        visibleData.forEach(bar => {
            const val = parseFloat(bar.Close || bar.close);
            if (val > maxPrice) maxPrice = val;
            if (val < minPrice) minPrice = val;
        });
        
        const refLines = options.refLines || [];
        refLines.forEach(line => {
            if (line.price > maxPrice) maxPrice = line.price;
            if (line.price < minPrice) minPrice = line.price;
        });
        
        const priceRange = maxPrice - minPrice;
        const padding = priceRange * 0.08 || 1;
        maxPrice += padding;
        minPrice -= padding;
        
        // 網格線
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.font = '9px Outfit, Noto Sans TC, sans-serif';
        ctx.fillStyle = '#9ca3af';
        ctx.textAlign = 'left';
        
        const gridCount = 4;
        for (let i = 0; i <= gridCount; i++) {
            const yPrice = minPrice + (maxPrice - minPrice) * (i / gridCount);
            const y = marginTop + chartHeight * (1 - i / gridCount);
            ctx.beginPath();
            ctx.moveTo(marginLeft, y);
            ctx.lineTo(marginLeft + chartWidth, y);
            ctx.stroke();
            ctx.fillText(yPrice.toFixed(2), marginLeft + chartWidth + 5, y + 3);
        }
        
        // 繪製曲線
        ctx.strokeStyle = '#8b5cf6';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        
        const step = chartWidth / (displayCount - 1 || 1);
        visibleData.forEach((bar, i) => {
            const val = parseFloat(bar.Close || bar.close);
            const x = marginLeft + i * step;
            const y = marginTop + chartHeight * (1 - (val - minPrice) / (maxPrice - minPrice));
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        
        // 漸層填充
        ctx.lineTo(marginLeft + (displayCount - 1) * step, marginTop + chartHeight);
        ctx.lineTo(marginLeft, marginTop + chartHeight);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, marginTop, 0, marginTop + chartHeight);
        grad.addColorStop(0, 'rgba(139, 92, 246, 0.15)');
        grad.addColorStop(1, 'rgba(139, 92, 246, 0.0)');
        ctx.fillStyle = grad;
        ctx.fill();
        
        // 橫軸標籤
        visibleData.forEach((bar, i) => {
            if (i % 8 === 0 || i === displayCount - 1) {
                ctx.fillStyle = '#6b7280';
                ctx.font = '8px Outfit, sans-serif';
                ctx.textAlign = 'center';
                const dateStr = bar.Date || bar.dateStr || "";
                const displayDate = dateStr.includes('-') ? dateStr.split('-').slice(1).join('/') : dateStr;
                ctx.fillText(displayDate, marginLeft + i * step, height - 2);
            }
        });
        
        // 畫參考線
        refLines.forEach(line => {
            const y = marginTop + chartHeight * (1 - (line.price - minPrice) / (maxPrice - minPrice));
            ctx.strokeStyle = line.color;
            ctx.lineWidth = 1.2;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(marginLeft, y);
            ctx.lineTo(marginLeft + chartWidth, y);
            ctx.stroke();
            ctx.setLineDash([]);
            
            ctx.fillStyle = line.color;
            ctx.font = 'bold 9px Noto Sans TC, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(line.label, marginLeft + chartWidth - 5, y - 4);
        });
    }

    // 5. 動態載入 Yahoo 數據並繪製圖表
    async function loadAndDrawChart(code, market, isDisposed, disposedPeriod, detail, calcs) {
        const canvas = document.getElementById('kline-canvas');
        const loadingDiv = document.getElementById('chart-loading');
        const legendDiv = document.getElementById('chart-legend');
        
        if (!canvas) return;
        
        const suffix = market === "上市" ? ".TW" : ".TWO";
        const yahooCode = `${code}${suffix}`;
        
        const options = {
            refLines: [],
            specialDates: {}
        };
        
        let dispType = "5分鐘";
        let startDateStr = "";
        let baseline = null;
        let targetPrice = null;
        
        // 1. 嘗試從 targets.json 載入數值
        const tgt = dispositionTargets.find(t => t.code === code);
        if (tgt) {
            dispType = tgt.type || "5分鐘";
            startDateStr = tgt.start_date || "";
            if (tgt.baseline_price !== "WAITING_FOR_OPEN") {
                baseline = parseFloat(tgt.baseline_price);
            }
            if (tgt.target_price !== "WAITING_FOR_OPEN") {
                targetPrice = parseFloat(tgt.target_price);
            }
        }
        
        // 2. 若 targets.json 沒有或不完整，使用原本的備用路徑
        if ((!baseline || !targetPrice) && isDisposed && disposedPeriod) {
            let regex = /(\d{2,3}[/\.\-]\d{2}[/\.\-]\d{2})|(\d{6,7})/g;
            let dates = disposedPeriod.match(regex);
            if (dates && dates.length >= 2) {
                const rocToAdStr = (rStr) => {
                    rStr = rStr.trim();
                    let m = rStr.match(/^(\d{2,3})[/\.\-](\d{2})[/\.\-](\d{2})$/);
                    if (m) {
                        let yr = parseInt(m[1], 10) + 1911;
                        return `${yr}-${m[2]}-${m[3]}`;
                    }
                    return "";
                };
                startDateStr = rocToAdStr(dates[0]);
            }
            
            detail = (detail || "").toLowerCase();
            if (detail.includes("20分") || detail.includes("二十分") || detail.includes("c20")) {
                dispType = "20分鐘";
            }
        }
        
        try {
            const url = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooCode}?interval=1d&range=3mo`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Yahoo chart request failed");
            
            const data = await res.json();
            const history = parseYahooData(data);
            
            if (history.length === 0) throw new Error("No live prices");
            
            if (isDisposed && startDateStr) {
                let idx_d1 = history.findIndex(h => h.dateStr >= startDateStr);
                if (idx_d1 !== -1) {
                    let idx_t1 = idx_d1 - 1;
                    if (idx_t1 >= 0) {
                        let t1_close = history[idx_t1].close;
                        let t1_high = history[idx_t1].high;
                        let isLimitUp = false;
                        if (idx_t1 - 1 >= 0) {
                            let t2_close = history[idx_t1 - 1].close;
                            isLimitUp = (t1_close === t1_high) && ((t1_close - t2_close) / t2_close >= 0.098);
                        }
                        
                        // 若未從 targets.json 載入，則由歷史計算
                        if (baseline === null) {
                            baseline = isLimitUp ? history[idx_d1].open : t1_close;
                        }
                        if (targetPrice === null) {
                            let multiplier = dispType === "5分鐘" ? 0.87 : 0.85;
                            let rawTarget = baseline * multiplier;
                            targetPrice = roundToValidTick(rawTarget);
                        }
                        
                        options.refLines.push({
                            price: baseline,
                            color: '#00bfff',
                            label: `放空基準: ${baseline.toFixed(2)}`
                        });
                        options.refLines.push({
                            price: targetPrice,
                            color: '#ef4444',
                            label: `黃金目標: ${targetPrice.toFixed(2)}`
                        });
                        
                        options.specialDates[history[idx_t1].dateStr] = {
                            type: 'short',
                            color: '#00bfff'
                        };
                        
                        let endIdx = Math.min(idx_d1 + 10, history.length);
                        for (let j = idx_d1; j < endIdx; j++) {
                            if (history[j].low <= targetPrice) {
                                options.specialDates[history[j].dateStr] = {
                                    type: 'cover',
                                    color: '#ef4444'
                                };
                                break;
                            }
                        }
                        
                        updateDetailPanelText(baseline, targetPrice, dispType, isLimitUp);
                    }
                }
            } else if (!isDisposed && calcs && calcs.length > 0) {
                const primaryCalc = calcs.find(c => c.IsPrimary) || calcs[0];
                if (primaryCalc) {
                    if (primaryCalc.TargetUpPrice) {
                        options.refLines.push({
                            price: primaryCalc.TargetUpPrice,
                            color: '#ef4444',
                            label: `明日看漲門檻: ${primaryCalc.TargetUpPrice.toFixed(2)}`
                        });
                    }
                    if (primaryCalc.TargetDownPrice) {
                        options.refLines.push({
                            price: primaryCalc.TargetDownPrice,
                            color: '#10b981',
                            label: `明日看跌門檻: ${primaryCalc.TargetDownPrice.toFixed(2)}`
                        });
                    }
                }
            }
            
            loadingDiv.classList.add('hidden');
            canvas.classList.remove('hidden');
            legendDiv.classList.remove('hidden');
            
            drawCandlestickChart(canvas, history, options);
            
        } catch (error) {
            console.warn("Live chart failed, using cache data", error);
            try {
                const cacheResponse = await fetch('db/prices_cache.json');
                if (cacheResponse.ok) {
                    const cache = await cacheResponse.json();
                    if (cache[code] && cache[code].prices.length > 0) {
                        const prices = cache[code].prices;
                        
                        if (isDisposed) {
                            // 繪製處置股的歷史基準價與黃金線 (從 targets.json 或動態計算)
                            if (baseline === null || targetPrice === null) {
                                const fallbackTgt = dispositionTargets.find(t => t.code === code);
                                if (fallbackTgt) {
                                    if (fallbackTgt.baseline_price !== "WAITING_FOR_OPEN") baseline = parseFloat(fallbackTgt.baseline_price);
                                    if (fallbackTgt.target_price !== "WAITING_FOR_OPEN") targetPrice = parseFloat(fallbackTgt.target_price);
                                    dispType = fallbackTgt.type || "5分鐘";
                                }
                            }
                            if (baseline) {
                                options.refLines.push({
                                    price: baseline,
                                    color: '#00bfff',
                                    label: `放空基準: ${baseline.toFixed(2)}`
                                });
                            }
                            if (targetPrice) {
                                options.refLines.push({
                                    price: targetPrice,
                                    color: '#ef4444',
                                    label: `黃金目標: ${targetPrice.toFixed(2)}`
                                });
                            }
                            if (baseline && targetPrice) {
                                updateDetailPanelText(baseline, targetPrice, dispType, false);
                            }
                        } else if (!isDisposed && calcs && calcs.length > 0) {
                            const primaryCalc = calcs.find(c => c.IsPrimary) || calcs[0];
                            if (primaryCalc) {
                                if (primaryCalc.TargetUpPrice) {
                                    options.refLines.push({
                                        price: primaryCalc.TargetUpPrice,
                                        color: '#ef4444',
                                        label: `明日看漲: ${primaryCalc.TargetUpPrice.toFixed(2)}`
                                    });
                                }
                                if (primaryCalc.TargetDownPrice) {
                                    options.refLines.push({
                                        price: primaryCalc.TargetDownPrice,
                                        color: '#10b981',
                                        label: `明日看跌: ${primaryCalc.TargetDownPrice.toFixed(2)}`
                                    });
                                }
                            }
                        }
                        
                        loadingDiv.classList.add('hidden');
                        canvas.classList.remove('hidden');
                        drawClosePriceChart(canvas, prices, options);
                        return;
                    }
                }
            } catch (e) {
                console.error("Cache chart fallback failed", e);
            }
            loadingDiv.textContent = "⚠️ 無法載入圖表數據";
        }
    }

    // 6. 更新處置股黃金價格文字區塊
    function updateDetailPanelText(baseline, targetPrice, dispType, isLimitUp) {
        const el = document.getElementById('disp-calc-placeholder');
        if (!el) return;
        
        const discount = dispType === "5分鐘" ? "13% (87折)" : "15% (85折)";
        const pathText = isLimitUp ? "路徑 B (T-1日鎖漲停，以D1開盤價放空)" : "路徑 A (T-1日未漲停，以T-1收盤價放空)";
        
        el.innerHTML = `
            <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; margin-top: 8px;">
                <div style="font-weight: 600; color: #8b5cf6; margin-bottom: 5px; font-size: 0.9rem;">🎯 黃金多方目標價推算 (實戰參數)：</div>
                <div style="font-size: 0.82rem; margin-bottom: 3px; color: var(--fg-secondary);">起點路徑：<strong>${pathText}</strong></div>
                <div style="font-size: 0.82rem; margin-bottom: 3px; color: var(--fg-secondary);">放空基準價：<strong>${baseline.toFixed(2)} 元</strong></div>
                <div style="font-size: 0.82rem; margin-bottom: 3px; color: var(--fg-secondary);">多方折價幅度：<strong>${discount}</strong></div>
                <div style="font-size: 0.9rem; margin-top: 6px; color: #10b981;">黃金多方買點目標價：<strong style="font-size: 1.05rem; text-shadow: 0 0 10px rgba(16, 185, 129, 0.2);">${targetPrice.toFixed(2)} 元</strong></div>
            </div>
        `;
    }

    // 啟動加載
    loadData();
});
