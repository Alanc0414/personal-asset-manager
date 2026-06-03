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

# ========== 初始化 session_state（用于保存交易记录） ==========
if "transactions" not in st.session_state:
    st.session_state.transactions = []  # 交易列表，持久化到会话中

# ========== 侧边栏导航 ==========
st.sidebar.title("📊 导航菜单")

# 使用 radio 创建单选导航菜单
page = st.sidebar.radio(
    label="请选择功能页面",
    options=["首页", "我的持仓", "交易记录", "AI 智能分析"],
    index=0  # 默认选中首页
)

# ========== 侧边栏底部状态信息 ==========
st.sidebar.divider()
today = datetime.now().strftime("%Y-%m-%d")
st.sidebar.caption(f"📅 当前日期：{today}")
st.sidebar.caption("✅ 数据最后更新：今天")

# ========== 主页面内容 ==========
if page == "首页":
    # 首页：欢迎文字 + 项目简介（使用 Markdown 美化）
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
    # ========== 我的持仓页面 ==========
    st.title("📊 我的持仓")
    st.markdown("---")

    # --- 顶部指标卡片（使用 st.metric）---
    # 用户最新真实持仓：港股 ≈5万HKD + ETH 4.5万USD + USDT 3万USD ≈ 58.6万 RMB
    total_value = 586000.00      # 总资产价值 (CNY)
    today_pnl = 4850.00          # 今日盈亏 (CNY)
    num_assets = 3               # 持仓数量

    # 使用 3 列布局展示美观指标
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="总资产价值 (CNY)",
            value=f"¥{total_value:,.2f}",
            delta="2.1%"
        )
    with col2:
        st.metric(
            label="今日盈亏 (CNY)",
            value=f"¥{today_pnl:,.2f}",
            delta="+1.9%",
            delta_color="normal"
        )
    with col3:
        st.metric(
            label="持仓数量",
            value=num_assets,
            delta="0"
        )

    # --- 当前持仓表格 ---
    st.markdown("### 📋 当前持仓")

    # 创建用户最新真实持仓数据（DataFrame）—— 港股 ≈5万HKD + ETH 4.5万USD + USDT 3万USD
    portfolio_data = {
        "资产代码": ["HK-PORT", "ETH-USD", "USDT-USD"],
        "资产名称": ["港股组合", "以太坊", "泰达币 (USDT)"],
        "类型": ["股票", "加密货币", "加密货币"],
        "持有数量": [1, 18.51, 30000],
        "当前价格": [46000.00, 17500.00, 7.20],
        "市值": [46000.00, 324000.00, 216000.00],
        "盈亏比例 (%)": [2.5, 5.2, 0.0]
    }
    df = pd.DataFrame(portfolio_data)

    # 使用 st.dataframe 美化显示表格
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "当前价格": st.column_config.NumberColumn(format="¥%.2f"),
            "市值": st.column_config.NumberColumn(format="¥%.2f"),
            "盈亏比例 (%)": st.column_config.NumberColumn(format="%.1f%%")
        }
    )

    # 表格下方说明文字
    st.caption("📌 以上数据为模拟示例，仅用于功能演示。实际使用时可接入 yfinance 等真实数据源。")

elif page == "交易记录":
    # ========== 交易记录页面 ==========
    st.title("📝 交易记录")
    st.markdown("---")

    # --- 添加新交易表单 ---
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
            # 构造交易记录字典并保存到 session_state
            new_trade = {
                "交易日期": str(trade_date),
                "资产代码": symbol,
                "资产名称": name,
                "类型": asset_type,
                "交易类型": trade_type,
                "数量": quantity,
                "价格": price,
                "金额": round(quantity * price, 2)  # 自动计算总金额
            }
            st.session_state.transactions.append(new_trade)
            st.success("✅ 交易记录已添加！")

    # --- 交易历史表格 ---
    st.subheader("📜 交易历史")

    if len(st.session_state.transactions) == 0:
        st.info("暂无交易记录，请在上方表单添加第一条交易。")
    else:
        # 将列表转为 DataFrame 并显示
        df_trades = pd.DataFrame(st.session_state.transactions)
        st.dataframe(
            df_trades,
            use_container_width=True,
            hide_index=True,
            column_config={
                "价格": st.column_config.NumberColumn(format="¥%.2f"),
                "金额": st.column_config.NumberColumn(format="¥%.2f")
            }
        )
        st.caption(f"共 {len(st.session_state.transactions)} 条交易记录（数据保存在当前会话中，刷新页面后会清空）")

elif page == "AI 智能分析":
    # ========== AI 智能分析页面 ==========
    st.title("🤖 AI 智能分析")
    st.markdown("---")

    st.markdown("""
    基于当前持仓，使用 **Grok** 进行智能分析与洞见生成（仅供参考，非投资建议）。
    """)

    # --- API Key 输入 ---
    st.subheader("🔑 xAI API Key")
    api_key = st.text_input(
        "请输入您的 xAI API Key",
        type="password",
        placeholder="sk-...",
        help="从 https://x.ai 获取 API Key",
        key="xai_api_key_input"
    )

    # 保存到 session_state 以便后续使用
    if api_key:
        st.session_state["xai_api_key"] = api_key

    # --- 生成分析按钮 ---
    st.markdown("### 📊 生成分析报告")
    generate_btn = st.button("🚀 生成 AI 组合分析报告", type="primary", use_container_width=True)

    if generate_btn:
        # 检查是否有 API Key
        if "xai_api_key" not in st.session_state or not st.session_state["xai_api_key"]:
            st.error("❌ 请先输入 xAI API Key！")
        else:
            # 准备用户最新真实持仓数据（与 Portfolio 页面一致）
            portfolio_summary = """
            当前持仓（用户最新真实数据）：
            - 港股组合 (HK-PORT): 1份 @ ¥46,000，市值 ¥46,000，盈亏 +2.5%
            - 以太坊 (ETH-USD): 18.51个 @ ¥17,500，市值 ¥324,000，盈亏 +5.2%
            - 泰达币 (USDT-USD): 30,000个 @ ¥7.20，市值 ¥216,000，盈亏 0.0%
            总资产: ¥586,000，今日盈亏: +¥4,850.00
            """

            # 构建 System Prompt（定义 AI 角色和输出格式）
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

            # User Prompt（提供具体数据）
            user_prompt = f"""请基于以下持仓数据进行专业分析：

{portfolio_summary}

请严格按照 System Prompt 中指定的结构输出报告。"""

            # 调用 Grok API
            try:
                client = OpenAI(
                    api_key=st.session_state["xai_api_key"],
                    base_url="https://api.x.ai/v1"
                )

                with st.spinner("🧠 Grok 正在分析您的组合，请稍候..."):
                    response = client.chat.completions.create(
                        model="grok-3",  # 或 grok-3-latest，根据 xAI 文档
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=1500
                    )

                # 获取返回内容
                analysis_result = response.choices[0].message.content

                # 用 st.markdown 美化显示
                st.success("✅ 分析完成！")
                st.markdown("---")
                st.markdown(analysis_result)

            except Exception as e:
                st.error(f"❌ 调用 Grok API 时出错：{str(e)}")
                st.info("请检查 API Key 是否正确、网络是否正常，或稍后重试。")