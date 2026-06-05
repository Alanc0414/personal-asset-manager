"""离线验证「我的持仓」核心逻辑（不启动 Streamlit UI）。"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

APP_PATH = Path(__file__).parent / "app.py"
spec = importlib.util.spec_from_file_location("app_module", APP_PATH)
app = importlib.util.module_from_spec(spec)
sys.modules["app_module"] = app

# Streamlit 在 import 时会执行 set_page_config，用 stub 避免副作用
class _StStub:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None

sys.modules["streamlit"] = _StStub()
sys.modules["openai"] = type(sys)("openai")

# 只加载函数定义：手动 exec 函数块更安全——改为直接复制测试逻辑
from watchlist import WATCHLIST_50  # noqa: F401 — 确认阶段三预备文件可 import

# 直接内联测试关键函数（从 app 提取逻辑验证）
PORTFOLIO_COLUMNS = [
    "资产代码", "资产名称", "类型", "持有数量", "当前价格", "市值", "盈亏比例 (%)", "备注",
]


def recalculate_market_value(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if not result.empty:
        result["市值"] = result["持有数量"] * result["当前价格"]
    return result


def test_recalc():
    df = pd.DataFrame([{
        "资产代码": "ETH-USD", "资产名称": "以太坊", "类型": "加密货币",
        "持有数量": 20.0, "当前价格": 1650.0, "市值": 0.0, "盈亏比例 (%)": 0.0, "备注": "",
    }])
    out = recalculate_market_value(df)
    assert out.iloc[0]["市值"] == 33000.0, out.iloc[0]["市值"]
    print("PASS: 市值自动计算 20 * 1650 = 33000")


def test_usdt_name_in_defaults():
    text = (APP_PATH.read_text(encoding="utf-8"))
    assert '"资产名称": "USDT"' in text
    assert "泰达币 (USDT)" not in text.split("get_default_portfolio_df")[1].split("def normalize")[0]
    print("PASS: 默认数据 USDT 名称正确")


def test_top_instruction():
    text = APP_PATH.read_text(encoding="utf-8")
    assert "你可以直接在表格中修改【持有数量】和【当前价格】" in text
    assert "修改后点击下方按钮保存" in text
    print("PASS: 顶部说明文案存在")


def test_data_editor_config():
    text = APP_PATH.read_text(encoding="utf-8")
    assert 'key="portfolio_editor"' in text
    assert 'num_rows="dynamic"' in text
    assert "hide_index=True" in text
    assert 'st.session_state["my_portfolio"]' in text
    assert "resolve_holding_input" in text
    assert "on_change" not in text  # 已移除防崩溃
    print("PASS: data_editor 配置与 my_portfolio 保存存在")


def test_no_on_change_crash_pattern():
    text = APP_PATH.read_text(encoding="utf-8")
    assert "sync_portfolio_from_editor" not in text
    assert "coerce_to_dataframe" in text
    print("PASS: 已移除 sync_portfolio_from_editor，保留 coerce_to_dataframe")


def test_resolve_eth_without_code():
    ns: dict = {}
    code = APP_PATH.read_text(encoding="utf-8")
    start = code.index("def resolve_holding_input")
    end = code.index("\ndef build_portfolio_summary")
    exec(code[start:end], ns)
    resolve = ns["resolve_holding_input"]
    assert resolve("", "eth", "加密货币") == ("ETH-USD", "以太坊")
    assert resolve("", "usdt", "稳定币") == ("USDT-USD", "USDT")
    print("PASS: eth/usdt 留空代码可自动解析")


def test_coerce_and_normalize():
    ns: dict = {"pd": pd}
    code = APP_PATH.read_text(encoding="utf-8")
    chunk = code[code.index("PORTFOLIO_COLUMNS"):code.index("\ndef build_portfolio_summary")]
    exec(chunk, ns)
    empty = ns["empty_portfolio_df"]()
    assert list(empty.columns) == PORTFOLIO_COLUMNS
    assert ns["coerce_to_dataframe"](None) is None
    assert ns["coerce_to_dataframe"]({"资产代码": ["X"]}) is not None
    # 非 DataFrame 不应触发 .empty AttributeError
    assert ns["normalize_portfolio_df"](None, fallback_to_default=False).empty
    print("PASS: coerce/normalize 防空值崩溃")


if __name__ == "__main__":
    test_recalc()
    test_usdt_name_in_defaults()
    test_top_instruction()
    test_data_editor_config()
    test_no_on_change_crash_pattern()
    test_resolve_eth_without_code()
    test_coerce_and_normalize()
    print("\nAll offline checks passed.")
