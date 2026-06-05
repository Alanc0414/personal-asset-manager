import streamlit as st
from datetime import datetime, date
import pandas as pd
from openai import OpenAI  # 用于兼容方式调用 Grok API

# 设置页面配置：标题、图标和布局
st.set_page_config(
    page_title="个人资产管理平台",
    page_icon="📈",
    layout="wide"
)

def get_default_portfolio_df() -> pd.DataFrame:
    """返回默认持仓数据，供初始化和「重置为默认数据」使用。"""
    return pd.DataFrame([
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
            "资产名称": "泰达币 (USDT)",
            "类型": "稳定币",
            "持有数量": 30000.0,
            "当前价格": 7.2,
            "市值": 216000.0,
            "盈亏比例 (%)": 0.0,
            "备注": "稳定币对冲",
        },
    ])


def recalculate_market_value(df: pd.DataFrame) -> pd.DataFrame:
    """根据「持有数量 × 当前价格」重新计算市值。"""
    result = df.copy()
    if not result.empty:
        result["市值"] = result["持有数量"] * result["当前价格"]
    return result


def build_portfolio_summary(df: pd.DataFrame) -> str:
    """把持仓 DataFrame 转成 AI 分析用的文本摘要。"""
    if df.empty:
        return "当前没有持仓数据。"

    lines = ["当前持仓（用户保存的数据）："]
    total_value = 0.0

    for _, row in df.iterrows():
        market_value = float(row["市值"])
        total_value += market_value
        pnl = row.get("盈亏比例 (%)", 0.0)
        lines.append(
            f"- {row['资产名称']} ({row['资产代码']}): "
            f"{row['持有数量']} @ ¥{row['当前价格']:,.2f}，"
            f"市值 ¥{market_value:,.2f}，盈亏 {pnl}%"
        )

    lines.append(f"总资产: ¥{total_value:,.2f}")
    return "\n".join(lines)


# ========== 初始化 session_state ==========
if "transactions" not in st.session_state:
    st.session_state.transactions = []

if "portfolio_df" not in st.session_state:
    st.session_state.portfolio_df = get_default_portfolio_df()

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

    # 展示前先确保市值与数量、价格一致
    display_df = recalculate_market_value(st.session_state.portfolio_df)

    edited_df = st.data_editor(
        display_df,
        key="portfolio_editor",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "持有数量": st.column_config.NumberColumn(
                min_value=0.0,
                step=0.01,
                format="%.2f",
            ),
            "当前价格": st.column_config.NumberColumn(
                min_value=0.0,
                step=0.01,
                format="¥%.2f",
            ),
            "市值": st.column_config.NumberColumn(disabled=True, format="¥%.2f"),
            "盈亏比例 (%)": st.column_config.NumberColumn(
                disabled=True,
                format="%.1f%%",
            ),
            "资产代码": st.column_config.TextColumn(disabled=True),
            "资产名称": st.column_config.TextColumn(disabled=True),
            "类型": st.column_config.SelectboxColumn(
                options=["股票", "加密货币", "稳定币"],
                disabled=True,
            ),
            "备注": st.column_config.TextColumn(disabled=True),
        },
    )

    # 用户修改数量或价格后，自动重算市值并写回 session_state
    st.session_state.portfolio_df = recalculate_market_value(edited_df)

    st.markdown("### ➕ 添加新持仓")
    with st.form(key="add_holding_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_symbol = st.text_input("资产代码", placeholder="例如：0700.HK")
            new_name = st.text_input("资产名称", placeholder="例如：腾讯控股")
            new_type = st.selectbox("类型", ["股票", "加密货币", "稳定币"])
        with col2:
            new_qty = st.number_input(
                "持有数量",
                min_value=0.0,
                step=0.01,
                format="%.2f",
            )
            new_price = st.number_input(
                "当前价格",
                min_value=0.0,
                step=0.01,
                format="%.2f",
            )

        if st.form_submit_button("添加持仓"):
            if new_symbol.strip() and new_name.strip() and new_qty > 0:
                new_row = pd.DataFrame([{
                    "资产代码": new_symbol.strip(),
                    "资产名称": new_name.strip(),
                    "类型": new_type,
                    "持有数量": new_qty,
                    "当前价格": new_price,
                    "市值": new_qty * new_price,
                    "盈亏比例 (%)": 0.0,
                    "备注": "",
                }])
                st.session_state.portfolio_df = pd.concat(
                    [st.session_state.portfolio_df, new_row],
                    ignore_index=True,
                )
                st.success("✅ 新持仓已添加！")
                st.rerun()
            else:
                st.warning("请填写资产代码、资产名称，且持有数量需大于 0。")

    st.markdown("---")
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("保存持仓数据", type="primary", use_container_width=True):
            st.session_state["my_portfolio"] = st.session_state.portfolio_df.copy()
            st.success("✅ 持仓数据已保存，AI 智能分析页面将使用这份数据。")

    with btn_col2:
        if st.button("重置为默认数据", use_container_width=True):
            st.session_state.portfolio_df = get_default_portfolio_df()
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

        submitted = st.form_submit_button("提交交易")

        if submitted:
            new_trade = {
                "交易日期": str(trade_date),
                "资产代码": symbol,
                "资产名称": name,
                "类型": asset_type,
                "交易类型": trade_type,
                "数量": quantity,
                "价格": price,
                "金额": round(quantity * price, 2),
            }
            st.session_state.transactions.append(new_trade)
            st.success("✅ 交易记录已添加！")

    st.subheader("📜 交易历史")

    if len(st.session_state.transactions) == 0:
        st.info("暂无交易记录，请在上方表单添加第一条交易。")
    else:
        df_trades = pd.DataFrame(st.session_state.transactions)
        st.dataframe(
            df_trades,
            use_container_width=True,
            hide_index=True,
            column_config={
                "价格": st.column_config.NumberColumn(format="¥%.2f"),
                "金额": st.column_config.NumberColumn(format="¥%.2f"),
            },
        )
        st.caption(
            f"共 {len(st.session_state.transactions)} 条交易记录"
            "（数据保存在当前会话中，刷新页面后会清空）"
        )

elif page == "AI 智能分析":
    st.title("🤖 AI 智能分析")
    st.markdown("---")

    st.markdown("""
    基于当前持仓，使用 **Grok** 进行智能分析与洞见生成（仅供参考，非投资建议）。
    """)

    if "my_portfolio" in st.session_state:
        st.info("当前将使用你在「我的持仓」页面保存的数据进行分析。")
        preview_df = st.session_state["my_portfolio"]
    else:
        st.warning(
            "你还未点击「保存持仓数据」。将暂时使用「我的持仓」中的当前表格数据。"
        )
        preview_df = st.session_state.portfolio_df

    if not preview_df.empty:
        st.dataframe(
            preview_df,
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### 📊 生成分析报告")
    generate_btn = st.button(
        "🚀 生成 AI 组合分析报告",
        type="primary",
        use_container_width=True,
    )

    if generate_btn:
        try:
            xai_api_key = st.secrets["XAI_API_KEY"]
            if not xai_api_key or xai_api_key == "在这里填你的xAI API Key":
                st.error("❌ 未检测到有效的 xAI API Key，请在 .streamlit/secrets.toml 中配置！")
            else:
                portfolio_summary = build_portfolio_summary(preview_df)

                system_prompt = """你是一位专业的投资组合分析师，擅长风险评估和市场洞察。
请严格按照以下结构输出分析报告，使用 Markdown 格式（支持 # ## - ** 等）：

## 1. 组合整体健康度评估
（用 2-3 句话总结当前组合的整体表现和分散度）

## 2. 主要风险点
（列出 3-4 个主要风险，包括集中度、波动性、币种暴露等，用 bullet points）

## 3. 各资产简要点评
（对每只资产给出 1 句简短点评）

## 4. 潜在关注点与情景分析
（分析 2-3 个未来可能情景及应对建议）

最后必须加上：
> **免责声明**：以上分析由 AI 生成，仅供参考，不构成投资建议。投资有风险，决策需谨慎。"""

                user_prompt = f"""请基于以下持仓数据进行专业分析：

{portfolio_summary}

请严格按照 System Prompt 中指定的结构输出报告。"""

                try:
                    client = OpenAI(
                        api_key=xai_api_key,
                        base_url="https://api.x.ai/v1",
                    )

                    with st.spinner("🧠 Grok 正在分析您的组合，请稍候..."):
                        response = client.chat.completions.create(
                            model="grok-3",
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.7,
                            max_tokens=1500,
                        )

                    analysis_result = response.choices[0].message.content

                    st.success("✅ 分析完成！")
                    st.markdown("---")
                    st.markdown(analysis_result)

                except Exception as e:
                    st.error(f"❌ 调用 Grok API 时出错：{str(e)}")
                    st.info("请检查 API Key 是否正确、网络是否正常，或稍后重试。")

        except (KeyError, FileNotFoundError):
            st.error(
                "❌ 无法读取 st.secrets 中的 XAI_API_KEY，"
                "请确保 .streamlit/secrets.toml 文件存在且配置正确！"
            )
            st.info(
                "提示：在项目根目录创建 .streamlit/secrets.toml 文件，"
                "并填入你的 xAI API Key。"
            )
