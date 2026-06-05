import streamlit as st
from datetime import datetime, date
import pandas as pd
from openai import OpenAI

from factor_analysis import analyze_selected_assets, build_selected_assets_summary
from watchlist import get_watchlist_df

st.set_page_config(
    page_title="个人资产管理平台",
    page_icon="📈",
    layout="wide",
)

PORTFOLIO_COLUMNS = [
    "资产代码",
    "资产名称",
    "类型",
    "持有数量",
    "当前价格",
    "市值",
    "盈亏比例 (%)",
    "备注",
]


def empty_portfolio_df() -> pd.DataFrame:
    """返回带正确列名的空持仓表。"""
    return pd.DataFrame(columns=PORTFOLIO_COLUMNS)


def coerce_to_dataframe(value) -> pd.DataFrame | None:
    """把任意输入安全转换为 DataFrame，失败时返回 None。"""
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, dict):
        try:
            return pd.DataFrame(value)
        except (ValueError, TypeError):
            return None
    try:
        return pd.DataFrame(value)
    except (ValueError, TypeError):
        return None


def get_default_portfolio_df() -> pd.DataFrame:
    """返回默认持仓数据。"""
    raw = pd.DataFrame([
        {
            "资产代码": "HK-PORT",
            "资产名称": "港股组合",
            "类型": "股票",
            "持有数量": 1.0,
            "当前价格": 46000.0,
            "市值": 46000.0,
            "盈亏比例 (%)": 2.5,
            "备注": "腾讯+阿里等港股持仓",
        },
        {
            "资产代码": "ETH-USD",
            "资产名称": "以太坊",
            "类型": "加密货币",
            "持有数量": 18.51,
            "当前价格": 17500.0,
            "市值": 324000.0,
            "盈亏比例 (%)": 5.2,
            "备注": "",
        },
        {
            "资产代码": "USDT-USD",
            "资产名称": "USDT",
            "类型": "稳定币",
            "持有数量": 30000.0,
            "当前价格": 7.2,
            "市值": 216000.0,
            "盈亏比例 (%)": 0.0,
            "备注": "稳定币对冲",
        },
    ])
    return normalize_portfolio_df(raw, fallback_to_default=False)


def normalize_portfolio_df(df, fallback_to_default: bool = True) -> pd.DataFrame:
    """统一列类型、清理空行，并修正 USDT 显示名称。"""
    coerced = coerce_to_dataframe(df)
    if coerced is None:
        return get_default_portfolio_df() if fallback_to_default else empty_portfolio_df()

    result = coerced.copy()
    for col in PORTFOLIO_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA

    result = result[PORTFOLIO_COLUMNS].copy()
    if result.empty:
        return empty_portfolio_df()

    result["资产代码"] = result["资产代码"].fillna("").astype(str).str.strip()
    result["资产名称"] = result["资产名称"].fillna("").astype(str).str.strip()
    result["类型"] = result["类型"].fillna("").astype(str).str.strip()
    result["备注"] = result["备注"].fillna("").astype(str)

    result.loc[result["资产代码"] == "USDT-USD", "资产名称"] = "USDT"
    result.loc[result["资产名称"] == "泰达币 (USDT)", "资产名称"] = "USDT"

    # 去掉点 + 号误添加的空行（资产代码为空的行）
    result = result[result["资产代码"] != ""].reset_index(drop=True)
    if result.empty:
        return empty_portfolio_df()

    for col in ["持有数量", "当前价格", "市值", "盈亏比例 (%)"]:
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0.0)

    return result


def recalculate_market_value(df) -> pd.DataFrame:
    """市值 = 持有数量 × 当前价格。"""
    result = normalize_portfolio_df(df, fallback_to_default=False)
    if result.empty:
        return result
    result["市值"] = result["持有数量"] * result["当前价格"]
    return result


def prepare_editor_df(df: pd.DataFrame) -> pd.DataFrame:
    """为 data_editor 准备数值类型，便于双击/单击编辑。"""
    prepared = recalculate_market_value(df)
    if prepared.empty:
        return prepared
    for col in ["持有数量", "当前价格", "市值", "盈亏比例 (%)"]:
        prepared[col] = prepared[col].astype(float)
    return prepared


def clear_portfolio_editor_state() -> None:
    """清除编辑器缓存，避免添加/删除后表格状态不同步。"""
    if "portfolio_editor" in st.session_state:
        del st.session_state["portfolio_editor"]


def resolve_holding_input(symbol: str, name: str, asset_type: str) -> tuple[str, str] | None:
    """根据用户输入解析资产代码和名称；代码可留空，只填名称也行。"""
    symbol = symbol.strip()
    name = name.strip()

    if not symbol and not name:
        return None

    alias_map = {
        "eth": ("ETH-USD", "以太坊"),
        "以太坊": ("ETH-USD", "以太坊"),
        "btc": ("BTC-USD", "比特币"),
        "比特币": ("BTC-USD", "比特币"),
        "usdt": ("USDT-USD", "USDT"),
        "泰达币": ("USDT-USD", "USDT"),
        "bnb": ("BNB-USD", "BNB"),
        "sol": ("SOL-USD", "Solana"),
        "xrp": ("XRP-USD", "瑞波币"),
        "doge": ("DOGE-USD", "狗狗币"),
    }

    lookup = (symbol or name).lower().replace(" ", "")
    if lookup in alias_map:
        return alias_map[lookup]

    if asset_type in ("加密货币", "稳定币"):
        base = (symbol or name).upper().replace(" ", "")
        if "USDT" in base:
            return "USDT-USD", "USDT"
        code = base if base.endswith("-USD") else f"{base}-USD"
        display = name or base.replace("-USD", "")
        return code, display

    code = symbol or name.upper()
    display = name or symbol
    return code, display


def build_portfolio_summary(df: pd.DataFrame) -> str:
    """把持仓 DataFrame 转成 AI 分析用的文本摘要。"""
    df = recalculate_market_value(df)
    if df.empty:
        return "当前没有持仓数据。"

    lines = ["当前持仓（用户保存的数据）："]
    total_value = 0.0

    for _, row in df.iterrows():
        market_value = float(row["市值"])
        total_value += market_value
        pnl = row["盈亏比例 (%)"]
        pnl_text = "未填写" if pd.isna(pnl) else f"{pnl}%"
        lines.append(
            f"- {row['资产名称']} ({row['资产代码']}) [{row['类型']}]: "
            f"数量 {row['持有数量']}，现价 ¥{row['当前价格']:,.2f}，"
            f"市值 ¥{market_value:,.2f}，盈亏 {pnl_text}"
        )

    lines.append(f"总资产: ¥{total_value:,.2f}")
    return "\n".join(lines)


def call_grok_analysis(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """调用 Grok API 并返回分析文本。"""
    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    response = client.chat.completions.create(
        model="grok-3",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def build_analysis_cache_key(records: list[dict]) -> tuple[tuple[str, str, str], ...]:
    """将选中资产转为可缓存的 hashable key。"""
    key_items = []
    for item in records:
        symbol = item.get("资产代码") or item.get("代码") or ""
        name = item.get("资产名称") or item.get("名称") or ""
        market = item.get("类型") or item.get("市场") or ""
        key_items.append((symbol, name, market))
    return tuple(key_items)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_analyze_selected(records_key: tuple[tuple[str, str, str], ...]) -> pd.DataFrame:
    """缓存 30 分钟内的多因子评分结果，减少重复行情请求。"""
    records = [
        {"资产代码": code, "资产名称": name, "类型": market}
        for code, name, market in records_key
    ]
    return analyze_selected_assets(records)


def show_watchlist_analysis_summary(score_df: pd.DataFrame) -> int:
    """展示行情拉取成功/失败汇总，返回成功数量。"""
    total = len(score_df)
    if total == 0:
        st.error("未生成任何评分结果，请稍后重试。")
        return 0

    success_mask = score_df["综合评分"].notna()
    success_count = int(success_mask.sum())
    failed_df = score_df[~success_mask]

    if success_count == total:
        st.success(f"行情拉取成功：{success_count} / {total} 只")
    elif success_count > 0:
        st.success(f"行情拉取成功：{success_count} / {total} 只")
        st.warning(f"有 {len(failed_df)} 只资产未能获取完整行情，其余结果仍可参考。")
        with st.expander("查看失败详情"):
            for _, row in failed_df.iterrows():
                st.markdown(f"- **{row['名称']} ({row['代码']})**：{row.get('备注', '未知错误')}")
    else:
        st.error(f"行情拉取失败：0 / {total} 只。请等待 1-2 分钟后重试，或先在本地验证网络。")
        with st.expander("查看失败详情"):
            for _, row in failed_df.iterrows():
                st.markdown(f"- **{row['名称']} ({row['代码']})**：{row.get('备注', '未知错误')}")

    return success_count


def get_analysis_portfolio_df() -> pd.DataFrame:
    """获取 AI 分析使用的持仓数据。"""
    if "my_portfolio" in st.session_state:
        return recalculate_market_value(st.session_state["my_portfolio"])
    return recalculate_market_value(st.session_state.portfolio_df)


def safe_init_portfolio_df() -> pd.DataFrame:
    """安全初始化 portfolio_df，避免 None 或非 DataFrame 导致崩溃。"""
    try:
        current = st.session_state.get("portfolio_df")
        normalized = recalculate_market_value(current)
        if normalized.empty:
            return get_default_portfolio_df()
        return normalized
    except Exception:
        return get_default_portfolio_df()


# ========== 初始化 session_state ==========
if "transactions" not in st.session_state:
    st.session_state.transactions = []

st.session_state.portfolio_df = safe_init_portfolio_df()

# ========== 侧边栏导航 ==========
st.sidebar.title("📊 导航菜单")

page = st.sidebar.radio(
    label="请选择功能页面",
    options=["首页", "我的持仓", "核心资产观察", "交易记录", "AI 智能分析"],
    index=0,
)

st.sidebar.divider()
today = datetime.now().strftime("%Y-%m-%d")
st.sidebar.caption(f"📅 当前日期：{today}")
st.sidebar.caption("✅ 数据最后更新：今天")

# ========== 主页面内容 ==========
if page == "首页":
    st.title("👋 欢迎来到个人资产管理平台")
    st.markdown("---")
    st.markdown("""
    ## 📌 项目简介

    **Personal Asset Manager** 是一个简洁高效的个人资产管理工具，帮助您：

    - 📈 **实时追踪持仓**：查看股票、基金等资产的最新表现
    - 📝 **记录交易明细**：轻松管理买入、卖出和分红记录
    - 🤖 **AI 智能分析**：获取基于数据的投资洞察与建议

    ---

    ### 🚀 开始使用
    请从左侧边栏选择对应页面，即可开始管理您的个人资产。

    > 💡 **小贴士**：数据来源于公开市场，投资需谨慎！
    """)

elif page == "我的持仓":
    st.title("📊 我的持仓")
    st.markdown("---")

    st.markdown(
        "你可以直接在表格中修改【持有数量】和【当前价格】，"
        "市值会自动更新。修改后点击下方按钮保存。"
    )
    st.caption(
        "💡 单击或双击【持有数量】【当前价格】单元格即可编辑；"
        "删除行可用表格左侧勾选后点删除，或用下方「删除持仓」。"
        "新增请用下方表单。"
    )

    editor_input = prepare_editor_df(st.session_state.portfolio_df)

    edited_df = st.data_editor(
        editor_input,
        key="portfolio_editor",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "持有数量": st.column_config.NumberColumn(
                "持有数量",
                help="单击单元格即可编辑",
                min_value=0.0,
                step=0.0001,
            ),
            "当前价格": st.column_config.NumberColumn(
                "当前价格",
                help="单击单元格即可编辑",
                min_value=0.0,
                step=0.0001,
            ),
            "市值": st.column_config.NumberColumn(
                "市值",
                help="自动计算 = 持有数量 × 当前价格",
                disabled=True,
                format="%.2f",
            ),
            "盈亏比例 (%)": st.column_config.NumberColumn(
                "盈亏比例 (%)",
                disabled=True,
                format="%.2f",
            ),
            "资产代码": st.column_config.TextColumn("资产代码", disabled=True),
            "资产名称": st.column_config.TextColumn("资产名称", disabled=True),
            "类型": st.column_config.TextColumn("类型", disabled=True),
            "备注": st.column_config.TextColumn("备注", disabled=True),
        },
    )

    # 同步编辑结果并重算市值（每次交互后 Streamlit 会自动 rerun）
    st.session_state.portfolio_df = recalculate_market_value(edited_df)
    current_df = st.session_state.portfolio_df

    if not current_df.empty:
        total_value = float(current_df["市值"].sum())
        holding_count = len(current_df)
        m1, m2 = st.columns(2)
        m1.metric("持仓数量", f"{holding_count} 个")
        m2.metric("总市值（实时）", f"¥{total_value:,.2f}")

    st.markdown("### ➕ 添加新持仓")
    with st.form(key="add_holding_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_symbol = st.text_input(
                "资产代码（可留空）",
                placeholder="不知道可留空，例如：ETH-USD / 0700.HK",
            )
            new_name = st.text_input(
                "资产名称",
                placeholder="例如：eth、以太坊、USDT",
            )
            new_type = st.selectbox("类型", ["股票", "加密货币", "稳定币"])
        with col2:
            new_qty = st.number_input("持有数量", min_value=0.0, step=0.01, format="%.2f")
            new_price = st.number_input("当前价格", min_value=0.0, step=0.01, format="%.2f")

        st.caption("💡 不知道代码也没关系：填名称即可，如输入 eth 会自动识别为 ETH-USD。")

        if st.form_submit_button("添加持仓", use_container_width=True):
            resolved = resolve_holding_input(new_symbol, new_name, new_type)
            if resolved and new_qty > 0:
                asset_code, asset_name = resolved
                new_row = pd.DataFrame([{
                    "资产代码": asset_code,
                    "资产名称": asset_name,
                    "类型": new_type,
                    "持有数量": float(new_qty),
                    "当前价格": float(new_price),
                    "市值": float(new_qty) * float(new_price),
                    "盈亏比例 (%)": 0.0,
                    "备注": "",
                }])
                st.session_state.portfolio_df = recalculate_market_value(
                    pd.concat([current_df, new_row], ignore_index=True)
                )
                clear_portfolio_editor_state()
                st.success(f"✅ 已添加 {asset_name}（{asset_code}）！")
                st.rerun()
            else:
                st.warning("请至少填写【资产名称】或【资产代码】，且持有数量需大于 0。")

    st.markdown("### 🗑️ 删除持仓")
    if current_df.empty:
        st.info("当前没有可删除的持仓。")
    else:
        delete_options = [
            f"{row['资产名称']} ({row['资产代码']})"
            for _, row in current_df.iterrows()
        ]
        label_to_code = {
            f"{row['资产名称']} ({row['资产代码']})": row["资产代码"]
            for _, row in current_df.iterrows()
        }
        to_delete_labels = st.multiselect(
            "选择要删除的持仓",
            options=delete_options,
            placeholder="选择一项或多项",
        )
        if st.button("删除选中持仓", use_container_width=True):
            if not to_delete_labels:
                st.warning("请先选择要删除的持仓。")
            else:
                codes = [label_to_code[label] for label in to_delete_labels]
                st.session_state.portfolio_df = current_df[
                    ~current_df["资产代码"].isin(codes)
                ].reset_index(drop=True)
                clear_portfolio_editor_state()
                st.success(f"✅ 已删除 {len(codes)} 条持仓。")
                st.rerun()

    st.markdown("---")
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("保存持仓数据", type="primary", use_container_width=True):
            saved = recalculate_market_value(st.session_state.portfolio_df)
            st.session_state["my_portfolio"] = saved.copy()
            st.session_state.portfolio_df = saved
            st.success("✅ 持仓数据已保存，AI 智能分析页面将使用这份数据。")

    with btn_col2:
        if st.button("重置为默认数据", use_container_width=True):
            st.session_state.portfolio_df = get_default_portfolio_df()
            clear_portfolio_editor_state()
            st.success("✅ 已恢复为默认持仓数据。")
            st.rerun()

    st.caption("📌 数据保存在当前浏览器会话中，刷新页面后会恢复为默认数据。")

elif page == "核心资产观察":
    st.title("核心资产观察")
    st.markdown("---")

    st.markdown(
        "这是我们筛选的 **50 支长期关注核心资产**（20 美股 + 20 港股 + 10 加密货币）。"
        "你可以多选资产，结合 **多因子量化评分** 与 **Grok 趋势分析**，判断值得关注的机会。"
    )
    st.caption(
        "在下方多选资产后点击「分析选中资产」，将先展示量化评分，再由 Grok 生成趋势判断与关注建议。"
    )

    watchlist_df = get_watchlist_df()
    MAX_ANALYZE_COUNT = 10

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search_text = st.text_input(
            "搜索",
            placeholder="输入代码或名称，例如：AAPL、腾讯、ETH",
            key="watchlist_search",
        )
    with f2:
        type_filter = st.selectbox(
            "类型筛选",
            ["全部", "美股", "港股", "加密货币"],
            key="watchlist_type_filter",
        )
    with f3:
        market_filter = st.selectbox(
            "市场筛选",
            ["全部", "US", "HK", "Crypto"],
            key="watchlist_market_filter",
        )

    filtered_df = watchlist_df.copy()

    if type_filter != "全部":
        filtered_df = filtered_df[filtered_df["类型"] == type_filter]

    if market_filter != "全部":
        filtered_df = filtered_df[filtered_df["市场"] == market_filter]

    if search_text.strip():
        keyword = search_text.strip().lower()
        mask = (
            filtered_df["资产代码"].str.lower().str.contains(keyword, na=False)
            | filtered_df["资产名称"].str.lower().str.contains(keyword, na=False)
            | filtered_df["备注"].str.lower().str.contains(keyword, na=False)
        )
        filtered_df = filtered_df[mask]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("列表总数", len(watchlist_df))
    m2.metric("当前显示", len(filtered_df))
    m3.metric("美股", len(watchlist_df[watchlist_df["类型"] == "美股"]))
    m4.metric("港股 / 加密货币", f"{len(watchlist_df[watchlist_df['类型'] == '港股'])} / {len(watchlist_df[watchlist_df['类型'] == '加密货币'])}")

    st.dataframe(
        filtered_df.reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "资产代码": st.column_config.TextColumn("资产代码"),
            "资产名称": st.column_config.TextColumn("资产名称"),
            "类型": st.column_config.TextColumn("类型"),
            "市场": st.column_config.TextColumn("市场"),
            "备注": st.column_config.TextColumn("备注"),
        },
    )

    if filtered_df.empty:
        st.info("没有匹配的资产，请调整搜索或筛选条件。")
    else:
        st.markdown("### 选择要分析的资产")
        option_labels = [
            f"{row['资产名称']} ({row['资产代码']})"
            for _, row in filtered_df.iterrows()
        ]
        label_to_record = {
            f"{row['资产名称']} ({row['资产代码']})": row.to_dict()
            for _, row in filtered_df.iterrows()
        }

        sel1, sel2 = st.columns([3, 1])
        with sel2:
            if st.button("全选当前列表", use_container_width=True, key="watchlist_select_all"):
                st.session_state["watchlist_selected_labels"] = option_labels[:MAX_ANALYZE_COUNT]
                st.rerun()
            if st.button("清空选择", use_container_width=True, key="watchlist_clear_all"):
                st.session_state["watchlist_selected_labels"] = []
                st.rerun()

        with sel1:
            if "watchlist_selected_labels" not in st.session_state:
                st.session_state["watchlist_selected_labels"] = []

            selected_labels = st.multiselect(
                "多选资产（建议一次不超过 10 只，避免等待过久）",
                options=option_labels,
                key="watchlist_selected_labels",
                placeholder="选择要分析的股票或加密货币",
            )

        st.markdown("---")
        analyze_btn = st.button(
            "分析选中资产",
            type="primary",
            use_container_width=True,
            key="btn_analyze_watchlist",
        )

        if analyze_btn:
            if not selected_labels:
                st.warning("请至少选择 1 支资产再分析。")
            elif len(selected_labels) > MAX_ANALYZE_COUNT:
                st.warning(f"一次最多分析 {MAX_ANALYZE_COUNT} 支资产，请减少选择数量。")
            else:
                selected_records = [label_to_record[label] for label in selected_labels]
                cache_key = build_analysis_cache_key(selected_records)

                with st.spinner(
                    f"正在计算 {len(selected_records)} 支资产的多因子评分（拉取行情数据，含自动重试）..."
                ):
                    score_df = cached_analyze_selected(cache_key)

                success_count = show_watchlist_analysis_summary(score_df)

                st.subheader("多因子量化评分")
                st.dataframe(
                    score_df,
                    use_container_width=True,
                    hide_index=True,
                )

                try:
                    xai_api_key = st.secrets["XAI_API_KEY"]
                    if success_count == 0:
                        st.info("量化评分暂无有效数据，已跳过 Grok 分析。请稍后重试行情拉取。")
                    elif not xai_api_key or xai_api_key == "在这里填你的xAI API Key":
                        st.error("未检测到有效的 XAI_API_KEY，请在 Streamlit Secrets 中配置。")
                    else:
                        factor_summary = build_selected_assets_summary(score_df)
                        system_prompt = """你是一位专业的股票与加密货币多因子策略分析师。
请基于用户提供的量化评分数据，对每只资产输出 Markdown 格式分析报告。

对每只资产必须包含：
## 资产名称（代码）
- **综合评分解读**：（说明分数高低意味着什么）
- **未来趋势判断**：强势 / 震荡偏多 / 震荡 / 偏弱（可结合量化结果微调）
- **主要影响因素**：动量、均线结构、RSI、波动率等（2-4 条）
- **建议关注区间**：结合买入区间、目标价、止损给出可操作观察区
- **是否值得关注**：一句话结论（观望 / 可关注 / 谨慎）

最后单独输出：
## 组合层面总结
- 哪些资产相对更强
- 主要风险点

必须附上免责声明：以上分析由 AI 生成，仅供参考，不构成投资建议。"""

                        user_prompt = f"""请对以下选中资产进行多因子趋势分析，给出是否值得关注的专业判断：

{factor_summary}

请用中文输出，结构清晰，便于普通投资者阅读。"""

                        with st.spinner("Grok 正在生成趋势分析与建议..."):
                            ai_result = call_grok_analysis(
                                xai_api_key, system_prompt, user_prompt
                            )

                        st.subheader("Grok 趋势分析与建议")
                        st.markdown(ai_result)

                except (KeyError, FileNotFoundError):
                    st.error("无法读取 XAI_API_KEY，量化评分已生成，但 AI 分析需要配置 API Key。")
                    st.info("请在 .streamlit/secrets.toml 或 Streamlit Cloud Secrets 中配置 XAI_API_KEY。")
                except Exception as e:
                    st.error(f"AI 分析失败：{e}")
                    st.info("量化评分表已展示，可稍后重试 Grok 分析。")

elif page == "交易记录":
    st.title("📝 交易记录")
    st.markdown("---")

    st.subheader("➕ 添加新交易")
    with st.form(key="add_transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("资产代码", placeholder="例如：0700.HK")
            name = st.text_input("资产名称", placeholder="例如：腾讯控股")
            asset_type = st.selectbox("类型", ["股票", "加密货币"])
            trade_type = st.selectbox("交易类型", ["买入", "卖出"])
        with col2:
            quantity = st.number_input("数量", min_value=0.0, step=0.01, format="%.2f")
            price = st.number_input("价格 (CNY)", min_value=0.0, step=0.01, format="%.2f")
            trade_date = st.date_input("交易日期", value=date.today())

        if st.form_submit_button("提交交易"):
            st.session_state.transactions.append({
                "交易日期": str(trade_date),
                "资产代码": symbol,
                "资产名称": name,
                "类型": asset_type,
                "交易类型": trade_type,
                "数量": quantity,
                "价格": price,
                "金额": round(quantity * price, 2),
            })
            st.success("✅ 交易记录已添加！")

    st.subheader("📜 交易历史")
    if not st.session_state.transactions:
        st.info("暂无交易记录，请在上方表单添加第一条交易。")
    else:
        df_trades = pd.DataFrame(st.session_state.transactions)
        st.dataframe(df_trades, use_container_width=True, hide_index=True)

elif page == "AI 智能分析":
    st.title("🤖 AI 智能分析")
    st.markdown("---")
    st.markdown(
        "基于当前持仓，使用 **Grok** 生成分析报告（仅供参考，非投资建议）。"
    )

    preview_df = get_analysis_portfolio_df()

    if "my_portfolio" in st.session_state:
        st.info("当前将使用你在「我的持仓」页面保存的数据进行分析。")
    else:
        st.warning("你还未点击「保存持仓数据」，将暂时使用「我的持仓」中的当前表格数据。")

    if not preview_df.empty:
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

    tab1, tab2 = st.tabs(["📊 持仓组合分析", "📈 未来趋势预测"])

    with tab1:
        st.markdown("### 持仓组合健康度与风险分析")
        portfolio_btn = st.button(
            "🚀 生成持仓分析报告",
            type="primary",
            use_container_width=True,
            key="btn_portfolio_analysis",
        )

        if portfolio_btn:
            try:
                xai_api_key = st.secrets["XAI_API_KEY"]
                if not xai_api_key or xai_api_key == "在这里填你的xAI API Key":
                    st.error("❌ 请在 .streamlit/secrets.toml 中配置有效的 XAI_API_KEY。")
                else:
                    portfolio_summary = build_portfolio_summary(preview_df)
                    system_prompt = """你是一位专业的投资组合分析师。
请用 Markdown 输出，严格按以下结构：

## 1. 组合整体健康度评估
## 2. 主要风险点（bullet points）
## 3. 各资产简要点评
## 4. 潜在关注点与情景分析

最后必须加上免责声明：以上分析由 AI 生成，仅供参考，不构成投资建议。"""

                    user_prompt = f"请分析以下持仓：\n\n{portfolio_summary}"

                    with st.spinner("🧠 正在生成持仓分析..."):
                        result = call_grok_analysis(xai_api_key, system_prompt, user_prompt)

                    st.success("✅ 持仓分析完成！")
                    st.markdown(result)

            except (KeyError, FileNotFoundError):
                st.error("❌ 无法读取 XAI_API_KEY，请检查 .streamlit/secrets.toml。")
            except Exception as e:
                st.error(f"❌ 分析失败：{e}")

    with tab2:
        st.markdown("### 未来走势与趋势预测")
        st.caption("基于持仓资产，给出短中期趋势判断与关注要点（非精确股价预测）。")

        horizon = st.selectbox(
            "预测时间范围",
            ["1-2 周", "1 个月", "3 个月", "6 个月"],
            index=2,
        )

        trend_btn = st.button(
            "🔮 生成未来趋势预测",
            type="primary",
            use_container_width=True,
            key="btn_trend_analysis",
        )

        if trend_btn:
            try:
                xai_api_key = st.secrets["XAI_API_KEY"]
                if not xai_api_key or xai_api_key == "在这里填你的xAI API Key":
                    st.error("❌ 请在 .streamlit/secrets.toml 中配置有效的 XAI_API_KEY。")
                else:
                    portfolio_summary = build_portfolio_summary(preview_df)
                    system_prompt = """你是一位资深股票与加密货币策略分析师，擅长趋势研判。
请用 Markdown 输出，严格按以下结构：

## 1. 宏观与板块环境（简述）
## 2. 各资产未来趋势研判
对每只资产分别给出：
- **趋势方向**：偏多 / 偏空 / 震荡
- **关键驱动因素**（2-3 条）
- **未来时间窗口内的可能情景**（乐观 / 基准 / 悲观）
- **需要关注的价格或事件触发点**（如无法给具体价格，请给观察指标）

## 3. 组合层面建议
- 哪些资产值得重点关注
- 建议的风险控制方式

## 4. 预测不确定性说明
明确说明：趋势预测存在不确定性，不构成买卖建议。

最后必须加上免责声明：以上分析由 AI 生成，仅供参考，不构成投资建议。"""

                    user_prompt = f"""请基于以下持仓，给出「{horizon}」时间范围内的未来趋势预测：

{portfolio_summary}

请结合资产类型（股票/加密货币/稳定币）分别分析，并给出可执行的关注清单。"""

                    with st.spinner(f"🔮 正在生成 {horizon} 趋势预测..."):
                        result = call_grok_analysis(xai_api_key, system_prompt, user_prompt)

                    st.success("✅ 趋势预测完成！")
                    st.markdown(result)

            except (KeyError, FileNotFoundError):
                st.error("❌ 无法读取 XAI_API_KEY，请检查 .streamlit/secrets.toml。")
            except Exception as e:
                st.error(f"❌ 预测失败：{e}")
