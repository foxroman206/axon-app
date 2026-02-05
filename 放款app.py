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

# 初始化 session_state
for key, value in {'user': None, 'lang': 'cn', 'wallet_address': None}.items():
    if key not in st.session_state:
        st.session_state[key] = value

DB_FILE = "axon.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, password BLOB, role TEXT, balance REAL, credit_score INTEGER, profile TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS asks (id TEXT PRIMARY KEY, owner TEXT, rate REAL, amount REAL, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS bids (id TEXT PRIMARY KEY, owner TEXT, rate REAL, amount REAL, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trades (id TEXT PRIMARY KEY, rate REAL, amount REAL, timestamp TEXT, lender TEXT, borrower TEXT, rating INTEGER DEFAULT NULL)''')
    conn.commit()
    conn.close()

init_db()

def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt())
def check_password(hashed, pw): return bcrypt.checkpw(pw.encode(), hashed)

def register_user(username, password, role, balance, profile):
    hashed = hash_password(password)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (username, hashed, role, balance, 720, profile))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and check_password(row[1], password):
        return {'id': row[0], 'role': row[2], 'balance': row[3], 'credit_score': row[4], 'profile': row[5]}
    return None

def load_orders():
    conn = sqlite3.connect(DB_FILE)
    asks = pd.read_sql("SELECT * FROM asks ORDER BY rate ASC", conn)
    bids = pd.read_sql("SELECT * FROM bids ORDER BY rate DESC", conn)
    trades = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10", conn)
    conn.close()
    return asks, bids, trades

def render_depth_chart(asks, bids):
    if asks.empty and bids.empty:
        st.info("目前無訂單")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=asks['rate'], y=asks['amount'].cumsum(), fill='tozeroy', fillcolor='rgba(34,197,94,0.2)', line=dict(color='#22c55e'), name='Asks'))
    fig.add_trace(go.Scatter(x=bids['rate'], y=bids['amount'].cumsum(), fill='tozeroy', fillcolor='rgba(239,68,68,0.2)', line=dict(color='#ef4444'), name='Bids'))
    fig.update_layout(title="訂單簿深度圖", height=350)
    st.plotly_chart(fig, use_container_width=True)

def place_order(user, role, amount, rate_range, esg_proof=None):
    min_rate, max_rate = rate_range
    rate = random.randint(min_rate, max_rate)
    if rate > 18:
        st.error("利率超過上限 (18% APR)")
        return
    if user['credit_score'] < 600 and amount > 5000:
        st.error("高風險用戶額度上限為 $5,000")
        return

    split_count = 1
    if role == "LENDER" and amount > 5000:
        split_count = min(10, amount // 1000)
        split_amount = amount // split_count
        st.info(f"系統自動將 ${amount:,} 拆分成 {split_count} 份，每份約 ${split_amount:,}")
        amount = split_amount

    order_id = f"{role}_{datetime.now().timestamp()}"
    table = "asks" if role == "LENDER" else "bids"
    ts = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)", (order_id, user['id'], rate, amount, ts))

    esg_discount = 0
    if esg_proof and role == "BORROWER":
        esg_discount = 1
        rate = max(6, rate - esg_discount)
        st.success("綠色通道驗證成功！利率降低 1%")

    conn.commit()
    conn.close()
    match_orders(rate_range)
    st.toast("訂單已提交，AI 正在撮合中...", icon="🚀")
    st.rerun()

def match_orders(rate_range):
    conn = sqlite3.connect(DB_FILE)
    asks = pd.read_sql("SELECT * FROM asks ORDER BY rate ASC", conn)
    bids = pd.read_sql("SELECT * FROM bids ORDER BY rate DESC", conn)
    c = conn.cursor()
    match_count = 0
    for _, bid in bids.iterrows():
        matching_asks = asks[(asks['rate'] <= bid['rate']) & (asks['amount'] > 0)]
        if not matching_asks.empty:
            ask = matching_asks.iloc[0]
            trade_amt = min(bid['amount'], ask['amount'])
            ts = datetime.now().isoformat()
            trade_id = f"t_{datetime.now().timestamp()}"
            lender = ask['owner']
            borrower = bid['owner']
            c.execute("""
                INSERT INTO trades (id, rate, amount, timestamp, lender, borrower, rating)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
            """, (trade_id, ask['rate'], trade_amt, ts, lender, borrower))
            interest = trade_amt * ask['rate'] / 100
            if rate_range == (6, 10):
                platform_fee = interest * 0.01
            elif rate_range == (10, 14):
                platform_fee = interest * 0.02
            else:
                platform_fee = interest * 0.03
            borrower_info = c.execute("SELECT credit_score FROM users WHERE id=?", (borrower,)).fetchone()
            if borrower_info and borrower_info[0] < 600:
                insurance_fee = interest * 0.005
                platform_fee += insurance_fee
                c.execute("UPDATE insurance_fund SET amount = amount + ?", (insurance_fee,))
            c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (platform_fee / 2, borrower))
            c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (platform_fee / 2, lender))
            if bid['amount'] > trade_amt:
                c.execute("UPDATE bids SET amount = amount - ? WHERE id = ?", (trade_amt, bid['id']))
            else:
                c.execute("DELETE FROM bids WHERE id = ?", (bid['id'],))
            if ask['amount'] > trade_amt:
                c.execute("UPDATE asks SET amount = amount - ? WHERE id = ?", (trade_amt, ask['id']))
            else:
                c.execute("DELETE FROM asks WHERE id = ?", (ask['id'],))
            conn.commit()
            match_count += 1
            st.toast(f"撮合成功！交易金額 ${trade_amt:,.0f} @ {ask['rate']}%", icon="✅")
    if match_count == 0:
        st.toast("目前無匹配，建議調整利率或等待市場變化", icon="⚠️")
    conn.close()

# 白色 ESG 主題 CSS
st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%); color: #1f2937; }
    .card { background: white; border-radius: 16px; border: 1px solid #d1fae5; padding: 24px; margin: 16px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #065f46; }
    .stButton > button { background: #10b981; color: white; border: none; border-radius: 12px; font-weight: 600; padding: 12px 24px; transition: all 0.3s; }
    .stButton > button:hover { background: #059669; transform: scale(1.05); }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: white; border-bottom: 1px solid #d1fae5; }
    .stTabs [data-baseweb="tab"] { background: white; border-radius: 8px 8px 0 0; padding: 12px 24px; color: #065f46; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { background: #d1fae5; color: #047857; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("AXON")
st.caption("AI 動態借貸交易所原型")

st.info("教育原型 • 非真實金融服務 • 無真實資金參與")

# 語言切換
lang = st.selectbox("語言", ["中文", "English"], index=0, label_visibility="collapsed")
st.session_state.lang = 'cn' if lang == "中文" else 'en'

# 側邊欄
with st.sidebar:
    st.header("錢包與控制台" if st.session_state.lang == 'cn' else "Wallet & Controls")
    
    if wallet_connect:
        conn_btn = wallet_connect(label="連接錢包" if st.session_state.lang == 'cn' else "Connect Wallet", key="wallet")
        if conn_btn and conn_btn.get('address'):
            addr = conn_btn['address']
            st.success(f"已連接: {addr[:6]}...{addr[-4:]}")
            st.session_state.wallet_address = addr

    if st.session_state.user is None:
        choice = st.radio("選擇" if st.session_state.lang == 'cn' else "Choose", ["登入", "註冊"] if st.session_state.lang == 'cn' else ["Login", "Register"], horizontal=True)
        if choice == ("註冊" if st.session_state.lang == 'cn' else "Register"):
            username = st.text_input("用戶名" if st.session_state.lang == 'cn' else "Username")
            pw = st.text_input("密碼" if st.session_state.lang == 'cn' else "Password", type="password")
            role = st.selectbox("角色" if st.session_state.lang == 'cn' else "Role", ["LENDER", "BORROWER"])
            bal = st.number_input("初始餘額" if st.session_state.lang == 'cn' else "Initial Balance", value=50000.0)
            profile = st.text_area("個人簡介" if st.session_state.lang == 'cn' else "Profile", height=100)
            if st.button("註冊" if st.session_state.lang == 'cn' else "Register", use_container_width=True):
                if register_user(username, pw, role, bal, profile):
                    st.success("註冊成功，請登入" if st.session_state.lang == 'cn' else "Registered, please login")
                else:
                    st.error("用戶名已存在" if st.session_state.lang == 'cn' else "Username exists")
        else:
            username = st.text_input("用戶名" if st.session_state.lang == 'cn' else "Username")
            pw = st.text_input("密碼" if st.session_state.lang == 'cn' else "Password", type="password")
            if st.button("登入" if st.session_state.lang == 'cn' else "Login", use_container_width=True):
                user = login_user(username, pw)
                if user:
                    st.session_state.user = user
                    st.success("登入成功" if st.session_state.lang == 'cn' else "Logged in")
                    st.rerun()
                else:
                    st.error("登入失敗" if st.session_state.lang == 'cn' else "Login failed")
    else:
        u = st.session_state.user
        st.metric("可用餘額" if st.session_state.lang == 'cn' else "Available Balance", f"${u['balance']:,.0f}")
        st.metric("信用分" if st.session_state.lang == 'cn' else "Credit Score", u['credit_score'])
        st.write(f"角色：{u['role']}" if st.session_state.lang == 'cn' else f"Role: {u['role']}")

        st.subheader("錢包操作" if st.session_state.lang == 'cn' else "Wallet Actions")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("充值 $1,000" if st.session_state.lang == 'cn' else "Deposit $1,000", use_container_width=True):
                st.session_state.user['balance'] += 1000
                st.success("已充值 $1,000" if st.session_state.lang == 'cn' else "Deposited $1,000")
                st.rerun()
        with col2:
            if st.button("提領 $1,000" if st.session_state.lang == 'cn' else "Withdraw $1,000", use_container_width=True):
                if st.session_state.user['balance'] >= 1000:
                    st.session_state.user['balance'] -= 1000
                    st.success("已提領 $1,000" if st.session_state.lang == 'cn' else "Withdrew $1,000")
                else:
                    st.error("餘額不足" if st.session_state.lang == 'cn' else "Insufficient balance")
                st.rerun()

        if st.button("登出" if st.session_state.lang == 'cn' else "Logout", use_container_width=True):
            st.session_state.user = None
            st.rerun()

# Tab 定義
tab1, tab2, tab3 = st.tabs(["首頁" if st.session_state.lang == 'cn' else "Home", 
                            "交易" if st.session_state.lang == 'cn' else "Trade", 
                            "錢包" if st.session_state.lang == 'cn' else "Wallet"])

if st.session_state.user is not None:
    asks, bids, trades = load_orders()

    with tab1:
        st.subheader("市場概覽" if st.session_state.lang == 'cn' else "Market Overview")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("總鎖倉價值 (TVL)" if st.session_state.lang == 'cn' else "TVL", f"${random.randint(500000, 2000000):,.0f}")
        with col2:
            st.metric("資金利用率" if st.session_state.lang == 'cn' else "Utilization Rate", f"{random.randint(65, 95)}%")
        with col3:
            st.metric("平均年化收益率" if st.session_state.lang == 'cn' else "Avg APY", f"{random.uniform(8, 15):.1f}%")

        st.subheader("成交 K線" if st.session_state.lang == 'cn' else "Trade Candlestick")
        trade_data = pd.DataFrame({
            'Date': pd.date_range(start='2025-01-01', periods=30, freq='D'),
            'Open': [random.uniform(6, 18) for _ in range(30)],
            'High': [random.uniform(6, 18) for _ in range(30)],
            'Low': [random.uniform(6, 18) for _ in range(30)],
            'Close': [random.uniform(6, 18) for _ in range(30)],
            'Volume': [random.randint(1000, 100000) for _ in range(30)]
        })
        fig_trade = go.Figure()
        fig_trade.add_trace(go.Candlestick(x=trade_data['Date'], open=trade_data['Open'], high=trade_data['High'], low=trade_data['Low'], close=trade_data['Close'], name='K線'))
        fig_trade.add_trace(go.Bar(x=trade_data['Date'], y=trade_data['Volume'], name='成交量', yaxis='y2', opacity=0.5))
        fig_trade.update_layout(title="成交 K線圖", yaxis2=dict(title='成交量', overlaying='y', side='right'), height=500, xaxis_rangeslider_visible=True)
        st.plotly_chart(fig_trade, use_container_width=True)
        st.metric("總成交量" if st.session_state.lang == 'cn' else "Total Volume", f"{trade_data['Volume'].sum():,.0f}")

    with tab2:
        st.subheader("快速交易" if st.session_state.lang == 'cn' else "Quick Trade")
        role = st.session_state.user['role']
        if role == "BORROWER":
            mode = st.selectbox("借款模式" if st.session_state.lang == 'cn' else "Borrow Mode", [
                "穩健模式 (6-10% APR)",
                "平衡模式 (10-14% APR)",
                "高收益模式 (14-18% APR)"
            ])
            amount = st.number_input("借款金額 ($)" if st.session_state.lang == 'cn' else "Amount ($)", value=1000, step=100)
            if st.button("立即借款" if st.session_state.lang == 'cn' else "Borrow Now", type="primary"):
                st.success("借款申請已提交！")
        else:
            amount = st.number_input("放款金額 ($)" if st.session_state.lang == 'cn' else "Lend Amount ($)", value=1000, step=100)
            rate = st.number_input("目標利率 (%)" if st.session_state.lang == 'cn' else "Target Rate (%)", min_value=6, max_value=18, value=10)
            if st.button("立即放款" if st.session_state.lang == 'cn' else "Lend Now", type="primary"):
                st.success("放款訂單已提交！")

    with tab3:
        st.subheader("我的錢包" if st.session_state.lang == 'cn' else "My Wallet")
        st.metric("可用餘額" if st.session_state.lang == 'cn' else "Balance", f"${st.session_state.user['balance']:,.2f}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("充值 $1,000" if st.session_state.lang == 'cn' else "Deposit $1,000"):
                st.session_state.user['balance'] += 1000
                st.success("已充值 $1,000")
                st.rerun()
        with col2:
            if st.button("提領 $1,000" if st.session_state.lang == 'cn' else "Withdraw $1,000"):
                if st.session_state.user['balance'] >= 1000:
                    st.session_state.user['balance'] -= 1000
                    st.success("已提領 $1,000")
                else:
                    st.error("餘額不足")
                st.rerun()

        st.subheader("參與模擬市場" if st.session_state.lang == 'cn' else "Simulate Market")
        if st.button("點我參與！（隨機收益/風險）" if st.session_state.lang == 'cn' else "Join Simulation"):
            with st.spinner("模擬中..."):
                time.sleep(1.2)
                result = random.choice(["成功", "部分成功", "失敗"])
                if result == "成功":
                    gain = random.randint(50, 500)
                    st.session_state.user['balance'] += gain
                    st.balloons()
                    st.success(f"成功！獲得 ${gain}")
                elif result == "部分成功":
                    gain = random.randint(20, 120)
                    st.session_state.user['balance'] += gain
                    st.success(f"部分成功！獲得 ${gain}")
                else:
                    loss = random.randint(30, 200)
                    st.session_state.user['balance'] = max(0, st.session_state.user['balance'] - loss)
                    st.error(f"失敗，損失 ${loss}")
                st.rerun()

st.caption("AXON 原型 • 教育用途 • 無真實交易")