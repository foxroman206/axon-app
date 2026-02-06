import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import random
import sqlite3
import bcrypt
from datetime import datetime
import time

try:
    from streamlit_wallet_connect import wallet_connect
except ImportError:
    wallet_connect = None

# ────────────────────────────────────────────────
# 初始化與狀態管理
# ────────────────────────────────────────────────

for key, value in {
    'user': None, 'lang': 'cn', 'wallet_address': None, 'page': 'dashboard',
    'dark_mode': False, 'esg_points': 0, 'badge_level': '銅徽章', 'news': []
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

DB_FILE = "axon.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, password BLOB, role TEXT, balance REAL, credit_score INTEGER, profile TEXT, esg_points INTEGER DEFAULT 0)''')
    # ... 其他表略
    conn.commit()
    conn.close()

init_db()

# 登入 / 註冊函數（略，保持原樣）

# ────────────────────────────────────────────────
# 視覺主題：Neo-Financial Minimalism + Glassmorphism
# ────────────────────────────────────────────────

dark_mode = st.session_state.dark_mode
bg_color = "#0f172a" if dark_mode else "#f8fafc"
text_color = "#f8fafc" if dark_mode else "#1f2937"
card_bg = "rgba(255,255,255,0.05)" if dark_mode else "white"
border_color = "rgba(255,255,255,0.1)" if dark_mode else "#d1fae5"
primary = "#10b981"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    .stApp {{
        background: radial-gradient(circle at top right, {bg_color}, {'#1e293b' if dark_mode else '#ffffff'});
        color: {text_color};
        font-family: 'Inter', sans-serif;
    }}
    .card {{
        background: {card_bg};
        border: 1px solid {border_color};
        border-radius: 20px;
        padding: 25px;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }}
    .card:hover {{
        box-shadow: 0 0 25px rgba(16,185,129,0.15);
        transform: translateY(-5px);
    }}
    .esg-glow {{
        background: linear-gradient(90deg, #10b981, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
        padding: 5px 15px;
        border-radius: 50px;
        border: 1px solid #10b981;
        box-shadow: 0 0 15px rgba(16,185,129,0.3);
    }}
    .stButton > button {{
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-weight: 600;
        transition: all 0.3s;
    }}
    .stButton > button:hover {{
        box-shadow: 0 0 20px rgba(16,185,129,0.4);
        transform: scale(1.05);
    }}
    </style>
""", unsafe_allow_html=True)

# Logo & 標語
st.markdown("""
    <div style="text-align:center; padding:20px 0;">
        <h1 style="margin:0; color:#10b981;">AXON</h1>
        <p style="color:#94a3b8; font-size:18px; margin-top:4px;">
            AI 動態利率 · 自己決定 · 支持綠色未來
        </p>
    </div>
""", unsafe_allow_html=True)

# 語言 & 深色模式
col_lang, col_mode = st.columns([8, 2])
with col_lang:
    lang = st.selectbox("", ["中文", "English"], index=0, label_visibility="collapsed")
    st.session_state.lang = 'cn' if lang == "中文" else 'en'
with col_mode:
    st.session_state.dark_mode = st.toggle("深色模式" if st.session_state.lang == 'cn' else "Dark Mode")

# ────────────────────────────────────────────────
# 登入頁（全面升級）
# ────────────────────────────────────────────────

if not st.session_state.user:
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown("""
            <div class="card" style="text-align:center; padding:40px 20px;">
                <h2>歡迎加入 AXON</h2>
                <p style="color:#94a3b8;">AI 驅動的綠色 P2P 金融平台</p>
                <div style="margin:20px 0;">
                    <span class="esg-glow">首筆綠色借款 · 利率優惠 1.5%</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        choice = st.radio("", ["登入", "註冊"], horizontal=True)
        if choice == "登入":
            username = st.text_input("用戶名 / 信箱")
            pw = st.text_input("密碼", type="password")
            col_google, col_wallet = st.columns(2)
            col_google.button("Google 快速登入", use_container_width=True)
            col_wallet.button("WalletConnect", use_container_width=True)
            if st.button("登入", use_container_width=True):
                st.session_state.user = {'id': username, 'role': 'LENDER', 'balance': 125400}
                st.rerun()
        else:
            username = st.text_input("用戶名 / 信箱")
            pw = st.text_input("設定密碼", type="password")
            role = st.selectbox("我想要...", ["放款 (Lender)", "借款 (Borrower)"])
            if st.button("註冊並加入綠色網絡", use_container_width=True):
                st.success("註冊成功！歡迎成為 AXON 綠色一份子")
                st.session_state.user = {'id': username, 'role': role, 'balance': 50000}
                st.rerun()

else:
    # 已登入 - 左側導航
    pages = {
        "dashboard": "市場儀表板",
        "trade": "借款 / 放款",
        "wallet": "我的錢包",
        "simulate": "模擬中心",
        "insights": "AI 洞察"
    }
    with st.sidebar:
        st.title("AXON")
        selected = st.radio("導航", list(pages.keys()), format_func=lambda x: pages[x])
        st.markdown("---")
        st.metric("可用餘額", f"${st.session_state.user['balance']:,.0f}")
        st.progress(st.session_state.esg_points / 10000)
        st.write(f"ESG 點數：{st.session_state.esg_points} / 徽章：{st.session_state.badge_level}")
        if st.button("登出"):
            st.session_state.user = None
            st.rerun()

    # ────────────────────────────────────────────────
    # Dashboard（市場儀表板）
    # ────────────────────────────────────────────────
    if selected == "dashboard":
        st.subheader("市場儀表板")
        # ESG 影響大卡片
        st.markdown(f"""
            <div class="card" style="text-align:center;">
                <h2>你的綠色影響力</h2>
                <p style="font-size:48px; color:#10b981; margin:16px 0;">減碳 {st.session_state.esg_points:,} kg</p>
                <p style="color:#94a3b8;">相當於種植 {st.session_state.esg_points // 50} 棵樹</p>
                <span class="esg-glow">徽章等級：{st.session_state.badge_level}</span>
            </div>
        """, unsafe_allow_html=True)

        # 關鍵指標
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總鎖倉價值", f"${random.randint(500000,2000000):,}", delta="+4.2%")
        c2.metric("資金利用率", f"{random.randint(70,95)}%", delta="-1.1%")
        c3.metric("AI 建議利率", f"{random.uniform(6,12):.1f}%", delta="+0.3%")
        c4.metric("24h 綠色成交", f"${random.randint(10000,50000):,}", delta="+12.8%")

        # AI 動態新聞（模擬即時）
        st.subheader("AI 即時新聞")
        news_list = [
            "全球綠色債券發行量破紀錄，ESG 資金流入加速",
            "央行暗示降息，傳統存款利率可能再跌",
            "歐盟新碳關稅政策上路，綠色項目融資需求激增"
        ]
        for news in news_list:
            st.markdown(f"""
                <div class="card" style="margin-bottom:12px;">
                    <p style="margin:0;">{news}</p>
                    <small style="color:#94a3b8;">AI 偵測全球數據 · 剛剛</small>
                </div>
            """, unsafe_allow_html=True)

    # ────────────────────────────────────────────────
    # 借款 / 放款頁（步驟導引 + AI 建議）
    # ────────────────────────────────────────────────
    elif selected == "trade":
        st.subheader("借款 / 放款中心")
        step = st.radio("步驟", ["1. 選擇角色", "2. 設定條件", "3. AI 確認"], horizontal=True)

        if step == "1. 選擇角色":
            role = st.radio("我是", ["我想放款 (Lender)", "我想借款 (Borrower)"])
        elif step == "2. 設定條件":
            amount = st.number_input("金額 ($)", value=1000, step=100)
            rate = st.slider("目標利率 (%)", 6.0, 18.0, 10.0)
            esg = st.checkbox("申請 ESG 綠色通道（利率可降 1–2%）")
            st.info(f"AI 建議利率：{rate-1.5 if esg else rate:.1f}%（基於即時全球數據）")
        else:
            st.success("訂單已提交！AI 正在秒級撮合...")
            st.balloons()
            st.session_state.esg_points += random.randint(50, 200)
            st.session_state.badge_level = "銀徽章" if st.session_state.esg_points > 500 else st.session_state.badge_level

    # 錢包頁
    elif selected == "wallet":
        st.subheader("我的錢包")
        st.markdown(f"<p style='text-align:center; font-size:48px; color:#10b981;'>${st.session_state.user['balance']:,.0f}</p>", unsafe_allow_html=True)
        st.progress(st.session_state.esg_points / 10000)
        st.write(f"ESG 點數：{st.session_state.esg_points} | 徽章：{st.session_state.badge_level}")

        col1, col2 = st.columns(2)
        col1.button("充值 $1,000")
        col2.button("提領 $1,000")

    # 模擬中心
    elif selected == "simulate":
        st.subheader("模擬體驗")
        if st.button("開始模擬撮合"):
            with st.spinner("AI 正在模擬全球市場..."):
                time.sleep(2)
                gain = random.randint(50, 500)
                st.session_state.user['balance'] += gain
                st.session_state.esg_points += 100
                st.balloons()
                st.success(f"模擬成功！獲得 ${gain:,} + 100 ESG 點")
                if st.session_state.esg_points > 1000:
                    st.session_state.badge_level = "金徽章"

    # AI 洞察
    elif selected == "ai_insights":
        st.subheader("AI 洞察")
        st.write("全球利率趨勢：上升 0.2%（央行政策影響）")
        st.write("ESG 資金流入：本週 +18%")

st.caption("AXON 原型 • 教育用途 • 無真實交易")
