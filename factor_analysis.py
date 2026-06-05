"""多因子评分与趋势预测（基于 yfinance 历史行情）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_data import fetch_histories_batch, fetch_symbol_history
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


def _empty_symbol_result(symbol: str, name: str, market: str, note: str = "") -> dict:
    return {
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
        "备注": note,
    }


def analyze_symbol_from_history(
    symbol: str,
    name: str,
    market: str,
    hist: pd.DataFrame | None,
    fetch_note: str = "",
) -> dict:
    """基于已拉取的历史行情计算多因子评分，不发起网络请求。"""
    result = _empty_symbol_result(symbol, name, market)

    if hist is None or hist.empty or "Close" not in hist.columns:
        result["备注"] = fetch_note or "无历史行情（可能停牌或数据源暂不可用）"
        return result

    close = hist["Close"].dropna()
    if len(close) < 30:
        result["备注"] = fetch_note or "历史数据过短"
        return result

    price = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50

    ret20 = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0.0
    ret60 = (price / float(close.iloc[-61]) - 1) * 100 if len(close) >= 61 else ret20
    rsi = _calc_rsi(close)
    vol20 = float(close.pct_change().rolling(20).std().iloc[-1] * 100)

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


def analyze_symbol(symbol: str, name: str, market: str) -> dict:
    """拉取行情并计算多因子评分与价位参考。"""
    hist, fetch_note = fetch_symbol_history(symbol)
    return analyze_symbol_from_history(symbol, name, market, hist, fetch_note)


def _analyze_records_with_batch(records: list[dict]) -> list[dict]:
    symbols = []
    meta_by_symbol: dict[str, tuple[str, str]] = {}
    for item in records:
        symbol = item.get("资产代码") or item.get("代码")
        name = item.get("资产名称") or item.get("名称")
        market = item.get("类型") or item.get("市场")
        if not symbol:
            continue
        symbols.append(symbol)
        meta_by_symbol[symbol] = (name, market)

    histories = fetch_histories_batch(symbols)
    rows = []
    for symbol in symbols:
        name, market = meta_by_symbol[symbol]
        hist, fetch_note = histories.get(symbol, (None, "未请求"))
        rows.append(analyze_symbol_from_history(symbol, name, market, hist, fetch_note))
    return rows


def analyze_watchlist() -> pd.DataFrame:
    """分析 50 个核心资产并返回评分表。"""
    records = [
        {"资产代码": item["代码"], "资产名称": item["名称"], "类型": item["市场"]}
        for item in WATCHLIST_50
    ]
    rows = _analyze_records_with_batch(records)
    df = pd.DataFrame(rows)
    if "综合评分" in df.columns:
        df = df.sort_values("综合评分", ascending=False, na_position="last")
    return df.reset_index(drop=True)


def analyze_selected_assets(records: list[dict]) -> pd.DataFrame:
    """对选中的资产进行多因子评分（批量预取行情）。"""
    rows = _analyze_records_with_batch(records)
    df = pd.DataFrame(rows)
    if "综合评分" in df.columns:
        df = df.sort_values("综合评分", ascending=False, na_position="last")
    return df.reset_index(drop=True)


def build_selected_assets_summary(df: pd.DataFrame) -> str:
    """生成选中资产的多因子数据摘要，供 Grok 深度分析。"""
    if df is None or df.empty:
        return "未选中任何资产或评分数据为空。"

    lines = [f"用户选中了 {len(df)} 支资产，以下是量化多因子评分结果："]
    for _, row in df.iterrows():
        lines.append(
            f"\n### {row['名称']} ({row['代码']}) [{row['市场']}]\n"
            f"- 综合评分: {row.get('综合评分', 'N/A')}/100\n"
            f"- 趋势判断: {row.get('趋势判断', 'N/A')}\n"
            f"- 现价: {row.get('现价', 'N/A')}\n"
            f"- 动量20日: {row.get('动量20日(%)', 'N/A')}%, 动量60日: {row.get('动量60日(%)', 'N/A')}%\n"
            f"- RSI: {row.get('RSI', 'N/A')}\n"
            f"- 趋势结构: {row.get('趋势结构', 'N/A')}\n"
            f"- 建议关注/买入区间: {row.get('建议买入区间', 'N/A')}\n"
            f"- 预期目标价: {row.get('预期目标价', 'N/A')}\n"
            f"- 止损参考: {row.get('止损参考', 'N/A')}\n"
            f"- 备注: {row.get('备注', '')}"
        )
    return "\n".join(lines)


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
