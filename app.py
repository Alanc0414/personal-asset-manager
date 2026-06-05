import streamlit as st
from datetime import datetime, date
import pandas as pd
from openai import OpenAI

st.set_page_config(
    page_title="个人资产管理平台",
    page_icon="📈",
    layout="wide",
)

PORTFOLIO_DTYPES = {
    "资产代码": "string",
    "资产名称": "string",
    "类型": "string",
    "持有数量": "float64",
    "当前价格": "float64",
    "市值": "float64",
    "盈亏比例 (%)": "float64",
    "备注": "string",
}


def get_default_portfolio_df() -> pd.DataFrame:
    """返回默认持仓数据。"""
    return normalize_portfolio_df(pd.DataFrame([
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
    ]))


def normalize_portfolio_df(df: pd.DataFrame) -> pd.DataFrame:
    """统一列类型、清理空行，并修正 USDT 显示名称。"""
    if df is None or df.empty:
        return get_default_portfolio_df()

    result = df.copy()

    for col, dtype in PORTFOLIO_DTYPES.items():
        if col not in result.columns:
            if col == "盈亏比例 (%)":
                result[col] = pd.NA
            elif col == "备注":
                result[col] = ""
            else:
                result[col] = 0.0 if dtype == "float64" else ""
        result[col] = result[col].astype(dtype, errors="ignore")

    result["资产代码"] = result["资产代码"].fillna("").astype(str).str.strip()
    result["资产名称"] = result["资产名称"].fillna("").astype(str).str.strip()
    result.loc[result["资产代码"] == "USDT-USD", "资产名称"] = "USDT"
    result.loc[result["资产名称"] == "泰达币 (USDT)", "资产名称"] = "USDT"

    # 去掉点 + 号误添加的空行（资产代码为空的行）
    result = result[result["资产代码"] != ""].reset_index(drop=True)

    for col in ["持有数量", "当前价格", "市值", "盈亏比例 (%)"]:
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0.0)

    return result


def recalculate_market_value(df: pd.DataFrame) -> pd.DataFrame:
    """市值 = 持有数量 × 当前价格。"""
    result = normalize_portfolio_df(df)
    if not result.empty:
        result["市值"] = result["持有数量"] * result["当前价格"]
    return result


def sync_portfolio_from_editor() -> None:
    """data_editor 修改后回调：重算市值并写回 portfolio_df。"""
    edited = st.session_state.get("portfolio_editor")
    if edited is None:
        return
    st.session_state.portfolio_df = recalculate_market_value(edited)


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


def get_analysis_portfolio_df() -> pd.DataFrame:
    """获取 AI 分析使用的持仓数据。"""
    if "my_portfolio" in st.session_state:
        return recalculate_market_value(st.session_state["my_portfolio"])
    return recalculate_market_value(st.session_state.portfolio_df)


# ========== 初始化 session_state ==========
if "transactions" not in st.session_state:
    st.session_state.transactions = []

if "portfolio_df" not in st.session_state:
    st.session_state.portfolio_df = get_default_portfolio_df()
else:
    st.session_state.portfolio_df = recalculate_market_value(st.session_state.portfolio_df)

# ========== 侧边栏导航 ==========
st.sidebar.title("📊 导航菜单")

page = st.sidebar.radio(
    label="请选择功能页面",
    options=["首页", "我的持仓", "交易记录", "AI 智能分析"],
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
        "💡 请只修改【持有数量】【当前价格】两列；"
        "新增持仓请用下方表单，不要用表格工具栏的 + 号。"
    )

    st.data_editor(
        st.session_state.portfolio_df,
        key="portfolio_editor",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        on_change=sync_portfolio_from_editor,
        column_config={
            "持有数量": st.column_config.NumberColumn(
                "持有数量",
                help="可直接修改",
                min_value=0.0,
                step=0.01,
                format="%.4f",
            ),
            "当前价格": st.column_config.NumberColumn(
                "当前价格",
                help="可直接修改",
                min_value=0.0,
                step=0.01,
                format="%.4f",
            ),
            "市值": st.column_config.NumberColumn(
                "市值",
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

    st.markdown("### ➕ 添加新持仓")
    with st.form(key="add_holding_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_symbol = st.text_input("资产代码", placeholder="例如：0700.HK")
            new_name = st.text_input("资产名称", placeholder="例如：腾讯控股")
            new_type = st.selectbox("类型", ["股票", "加密货币", "稳定币"])
        with col2:
            new_qty = st.number_input("持有数量", min_value=0.0, step=0.01, format="%.2f")
            new_price = st.number_input("当前价格", min_value=0.0, step=0.01, format="%.2f")

        if st.form_submit_button("添加持仓"):
            if new_symbol.strip() and new_name.strip() and new_qty > 0:
                new_row = pd.DataFrame([{
                    "资产代码": new_symbol.strip(),
                    "资产名称": new_name.strip(),
                    "类型": new_type,
                    "持有数量": float(new_qty),
                    "当前价格": float(new_price),
                    "市值": float(new_qty) * float(new_price),
                    "盈亏比例 (%)": pd.NA,
                    "备注": "",
                }])
                st.session_state.portfolio_df = pd.concat(
                    [st.session_state.portfolio_df, new_row],
                    ignore_index=True,
                )
                st.session_state.portfolio_df = recalculate_market_value(
                    st.session_state.portfolio_df
                )
                st.success("✅ 新持仓已添加！")
                st.rerun()
            else:
                st.warning("请填写资产代码、资产名称，且持有数量需大于 0。")

    st.markdown("---")
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("保存持仓数据", type="primary", use_container_width=True):
            current = recalculate_market_value(st.session_state.portfolio_df)
            st.session_state["my_portfolio"] = current.copy()
            st.session_state.portfolio_df = current
            st.success("✅ 持仓数据已保存，AI 智能分析页面将使用这份数据。")

    with btn_col2:
        if st.button("重置为默认数据", use_container_width=True):
            st.session_state.portfolio_df = get_default_portfolio_df()
            if "portfolio_editor" in st.session_state:
                del st.session_state["portfolio_editor"]
            st.success("✅ 已恢复为默认持仓数据。")
            st.rerun()

    st.caption("📌 数据保存在当前浏览器会话中，刷新页面后会恢复为默认数据。")

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
