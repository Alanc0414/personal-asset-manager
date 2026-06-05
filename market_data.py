"""健壮行情拉取层：重试、超时、批量下载与友好错误分类。"""

from __future__ import annotations

import pandas as pd
import requests
import yfinance as yf
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_PERIOD = "1y"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (compatible; PersonalAssetManager/1.0; +https://github.com/Alanc0414/personal-asset-manager)"
)

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


class EmptyHistoryError(Exception):
    """yfinance 返回空历史数据，可触发重试。"""


def create_yfinance_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def classify_fetch_error(exc: BaseException | None, symbol: str) -> str:
    if exc is None:
        return "无历史行情（可能停牌或数据源暂不可用）"

    message = str(exc).lower()
    if isinstance(exc, requests.exceptions.Timeout) or "timeout" in message or "timed out" in message:
        return "网络超时，请稍后重试"
    if "429" in message or "rate limit" in message or "too many requests" in message:
        return "行情服务繁忙，已自动重试仍失败"
    if "invalid" in message and "ticker" in message:
        return f"代码无效或 Yahoo 无此标的：{symbol}"
    if isinstance(exc, EmptyHistoryError):
        return "无历史行情（可能停牌或数据源暂不可用）"
    return f"拉取失败: {exc}"


def _normalize_history(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    if close.empty:
        return None
    return df


def _extract_symbol_frame(data: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if data is None or data.empty:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        upper_symbols = {str(level).upper() for level in data.columns.get_level_values(0)}
        symbol_upper = symbol.upper()
        if symbol_upper in upper_symbols:
            try:
                frame = data[symbol_upper]
                if isinstance(frame, pd.DataFrame):
                    return _normalize_history(frame)
            except (KeyError, TypeError):
                pass
        for level in data.columns.get_level_values(0):
            if str(level).upper() == symbol_upper:
                frame = data[level]
                if isinstance(frame, pd.DataFrame):
                    return _normalize_history(frame)
        return None

    return _normalize_history(data)


@retry(
    retry=retry_if_exception_type((*RETRYABLE_EXCEPTIONS, EmptyHistoryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _download_symbol_history(symbol: str, period: str, session: requests.Session) -> pd.DataFrame:
    ticker = yf.Ticker(symbol, session=session)
    hist = ticker.history(period=period, auto_adjust=True, timeout=READ_TIMEOUT)
    normalized = _normalize_history(hist)
    if normalized is None:
        raise EmptyHistoryError(symbol)
    return normalized


def fetch_symbol_history(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame | None, str]:
    """拉取单标的历史行情，失败时返回 (None, 友好备注)。"""
    owns_session = session is None
    if owns_session:
        session = create_yfinance_session()

    try:
        hist = _download_symbol_history(symbol, period, session)
        return hist, ""
    except Exception as exc:
        return None, classify_fetch_error(exc, symbol)
    finally:
        if owns_session:
            session.close()


def _download_batch_history(
    symbols: list[str],
    period: str,
    session: requests.Session,
) -> pd.DataFrame | None:
    if not symbols:
        return None

    if len(symbols) == 1:
        hist, _ = fetch_symbol_history(symbols[0], period=period, session=session)
        return hist

    data = yf.download(
        tickers=" ".join(symbols),
        period=period,
        auto_adjust=True,
        group_by="ticker",
        threads=False,
        progress=False,
        timeout=READ_TIMEOUT,
        session=session,
    )
    if data is None or data.empty:
        return None
    return data


def fetch_histories_batch(
    symbols: list[str],
    period: str = DEFAULT_PERIOD,
) -> dict[str, tuple[pd.DataFrame | None, str]]:
    """批量拉取历史行情；失败标的单独 fallback，不阻断其他标的。"""
    unique_symbols: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol and symbol not in seen:
            unique_symbols.append(symbol)
            seen.add(symbol)

    results: dict[str, tuple[pd.DataFrame | None, str]] = {
        symbol: (None, "未请求") for symbol in unique_symbols
    }
    if not unique_symbols:
        return results

    session = create_yfinance_session()
    try:
        batch_data = _download_batch_history(unique_symbols, period, session)
        pending: list[str] = []

        for symbol in unique_symbols:
            frame = _extract_symbol_frame(batch_data, symbol) if batch_data is not None else None
            if frame is not None:
                results[symbol] = (frame, "")
            else:
                pending.append(symbol)

        for symbol in pending:
            results[symbol] = fetch_symbol_history(symbol, period=period, session=session)
    finally:
        session.close()

    return results
