"""多因子评分与趋势预测（基于 yfinance 历史行情）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from watchlist import WATCHLIST_50


def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return float(value) if pd.notna(value) else 50.0


def _clip_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def analyze_symbol(symbol: str, name: str, market: str) -> dict:
    """拉取行情并计算多因子评分与价位参考。"""
    result = {
        "代码": symbol,
        "名称": name,
        "市场": market,
        "现价": None,
        "综合评分": None,
        "趋势判断": "数据不足",
        "动量20日(%)": None,
        "动量60日(%)": None,
        "RSI": None,
        "趋势结构": None,
        "建议买入区间": None,
        "预期目标价": None,
        "止损参考": None,
        "备注": "",
    }

    try:
        hist = yf.Ticker(symbol).history(period="1y", auto_adjust=True)
    except Exception as exc:
        result["备注"] = f"拉取失败: {exc}"
        return result

    if hist is None or hist.empty or "Close" not in hist.columns:
        result["备注"] = "无历史行情"
        return result

    close = hist["Close"].dropna()
    if len(close) < 30:
        result["备注"] = "历史数据过短"
        return result

    price = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50

    ret20 = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0.0
    ret60 = (price / float(close.iloc[-61]) - 1) * 100 if len(close) >= 61 else ret20
    rsi = _calc_rsi(close)
    vol20 = float(close.pct_change().rolling(20).std().iloc[-1] * 100)

    # 多因子打分（0-100）
    momentum_score = _clip_score(50 + ret20 * 1.2 + ret60 * 0.5)
    trend_score = 50.0
    if price > ma20:
        trend_score += 10
    if price > ma50:
        trend_score += 15
    if ma50 > ma200:
        trend_score += 10
    if price > ma200:
        trend_score += 15
    trend_score = _clip_score(trend_score)

    if 45 <= rsi <= 60:
        rsi_score = 80.0
    elif 30 <= rsi < 45:
        rsi_score = 70.0
    elif 60 < rsi <= 70:
        rsi_score = 65.0
    elif rsi < 30:
        rsi_score = 55.0
    else:
        rsi_score = 40.0

    stability_score = _clip_score(100 - vol20 * 8)

    total = _clip_score(
        momentum_score * 0.30
        + trend_score * 0.35
        + rsi_score * 0.20
        + stability_score * 0.15
    )

    if total >= 75:
        trend_view = "强势偏多"
    elif total >= 60:
        trend_view = "震荡偏多"
    elif total >= 45:
        trend_view = "震荡"
    else:
        trend_view = "偏弱"

    recent_low = float(close.tail(20).min())
    recent_high = float(close.tail(60).max())
    buy_low = min(ma20, recent_low) * 0.99
    buy_high = min(price, ma20 * 1.02)
    target = max(recent_high, price * (1.06 if total >= 60 else 1.03))
    stop = min(ma50, recent_low) * 0.97

    if buy_low > buy_high:
        buy_low, buy_high = buy_high * 0.98, buy_high

    result.update({
        "现价": round(price, 4),
        "综合评分": round(total, 1),
        "趋势判断": trend_view,
        "动量20日(%)": round(ret20, 2),
        "动量60日(%)": round(ret60, 2),
        "RSI": round(rsi, 1),
        "趋势结构": (
            f"价{'>' if price > ma20 else '<'}MA20, "
            f"价{'>' if price > ma50 else '<'}MA50, "
            f"MA50{'>' if ma50 > ma200 else '<'}MA200"
        ),
        "建议买入区间": f"{buy_low:.2f} - {buy_high:.2f}",
        "预期目标价": f"{target:.2f}",
        "止损参考": f"{stop:.2f}",
        "备注": "基于K线与均线/动量/RSI的量化参考",
    })
    return result


def analyze_watchlist() -> pd.DataFrame:
    """分析 50 个核心资产并返回评分表。"""
    rows = []
    for item in WATCHLIST_50:
        rows.append(analyze_symbol(item["代码"], item["名称"], item["市场"]))
    df = pd.DataFrame(rows)
    if "综合评分" in df.columns:
        df = df.sort_values("综合评分", ascending=False, na_position="last")
    return df.reset_index(drop=True)


def build_watchlist_summary(df: pd.DataFrame, top_n: int = 15) -> str:
    """生成供 Grok 使用的 Watchlist 摘要。"""
    if df is None or df.empty:
        return "Watchlist 评分数据为空。"

    valid = df.dropna(subset=["综合评分"]).head(top_n)
    lines = [f"50核心资产多因子评分（展示前 {len(valid)} 名）："]
    for _, row in valid.iterrows():
        lines.append(
            f"- {row['名称']} ({row['代码']}) [{row['市场']}]: "
            f"评分 {row['综合评分']}, 趋势 {row['趋势判断']}, "
            f"现价 {row['现价']}, RSI {row['RSI']}, "
            f"买入区间 {row['建议买入区间']}, 目标价 {row['预期目标价']}, "
            f"止损 {row['止损参考']}"
        )
    return "\n".join(lines)
