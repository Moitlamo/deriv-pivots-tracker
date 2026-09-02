import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import websocket
from datetime import datetime

# layout="centered" is often better for mobile defaults than "wide"
st.set_page_config(page_title="Mobile Fib Pivots", layout="centered")

# --- Deriv WebSocket Fetcher ---
def fetch_deriv_candles(symbol, granularity, count):
    """Fetches OHLC candle data from Deriv WebSocket API"""
    app_id = 1089  
    url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
    
    try:
        ws = websocket.create_connection(url, timeout=8)
        req = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "style": "candles",
            "granularity": granularity
        }
        ws.send(json.dumps(req))
        response = json.loads(ws.recv())
        ws.close()
        
        if "error" in response:
            return None, response['error']['message']
            
        return response.get("candles", []), None
    except Exception as e:
        return None, str(e)

# --- Settings (Hidden in Sidebar on Mobile) ---
st.sidebar.header("⚙️ Settings")

assets = {
    "Volatility 10 Index": "R_10",
    "Volatility 25 Index": "R_25",
    "Volatility 50 Index": "R_50",
    "Volatility 75 Index": "R_75",
    "Volatility 100 Index": "R_100",
    "Volatility 10 (1s) Index": "1HZ10V",
    "Volatility 25 (1s) Index": "1HZ25V",
    "Volatility 50 (1s) Index": "1HZ50V",
    "Volatility 75 (1s) Index": "1HZ75V",
    "Volatility 100 (1s) Index": "1HZ100V"
}
selected_asset_name = st.sidebar.selectbox("Volatility Index", list(assets.keys()), index=4)
symbol = assets[selected_asset_name]

timeframes = {"1 Minute": 60, "5 Minutes": 300, "15 Minutes": 900, "30 Minutes": 1800, "1 Hour": 3600}
selected_tf = st.sidebar.selectbox("Timeframe", list(timeframes.keys()), index=2)
granularity = timeframes[selected_tf]

refresh_rate = st.sidebar.slider("Refresh Interval (s)", 2, 30, 5)

candles_per_day = 86400 // granularity
intraday_count = min(candles_per_day * 3 + 20, 3000) # Capped slightly lower for mobile performance

# --- Live Fragment Container ---
@st.fragment(run_every=refresh_rate)
def live_mobile_view():
    raw_daily, err_daily = fetch_deriv_candles(symbol, 86400, 6)
    raw_intra, err_intra = fetch_deriv_candles(symbol, granularity, intraday_count)

    if err_daily or err_intra:
        st.error(f"Error: {err_daily or err_intra}")
        return

    if not raw_daily or not raw_intra:
        st.warning("No data.")
        return

    # 1. Process Daily Data & Compute Fibonacci Pivots
    df_daily = pd.DataFrame(raw_daily)
    df_daily['datetime'] = pd.to_datetime(df_daily['epoch'], unit='s', utc=True)
    df_daily['date'] = df_daily['datetime'].dt.date

    df_daily['prev_high'] = df_daily['high'].shift(1)
    df_daily['prev_low'] = df_daily['low'].shift(1)
    df_daily['prev_close'] = df_daily['close'].shift(1)
    df_daily['range'] = df_daily['prev_high'] - df_daily['prev_low']

    df_daily['P'] = (df_daily['prev_high'] + df_daily['prev_low'] + df_daily['prev_close']) / 3
    df_daily['R1'] = df_daily['P'] + (0.382 * df_daily['range'])
    df_daily['R2'] = df_daily['P'] + (0.618 * df_daily['range'])
    df_daily['R3'] = df_daily['P'] + (1.000 * df_daily['range'])
    df_daily['S1'] = df_daily['P'] - (0.382 * df_daily['range'])
    df_daily['S2'] = df_daily['P'] - (0.618 * df_daily['range'])
    df_daily['S3'] = df_daily['P'] - (1.000 * df_daily['range'])
    df_daily.dropna(inplace=True)

    # 2. Process Intraday Data
    df_intra = pd.DataFrame(raw_intra)
    df_intra['datetime'] = pd.to_datetime(df_intra['epoch'], unit='s', utc=True)
    df_intra['date'] = df_intra['datetime'].dt.date

    latest_price = df_intra['close'].iloc[-1]
    today_pivots = df_daily.iloc[-1]

    # Mobile-Optimized Metrics (2x2 Grid)
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Live Price", f"{latest_price:,.2f}")
    m_col2.metric("Pivot (P)", f"{today_pivots['P']:,.2f}")
    
    m_col3, m_col4 = st.columns(2)
    m_col3.metric("Fib R1", f"{today_pivots['R1']:,.2f}")
    m_col4.metric("Fib S1", f"{today_pivots['S1']:,.2f}")

    # 3. Create Candlestick Plot
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_intra['datetime'],
        open=df_intra['open'],
        high=df_intra['high'],
        low=df_intra['low'],
        close=df_intra['close'],
        name="Price",
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350'
    ))

    fib_colors = {'R3': '#ff1744', 'R2': '#ff5252', 'R1': '#ff7961', 'P': '#ffd600', 'S1': '#81c784', 'S2': '#4caf50', 'S3': '#2e7d32'}

    for _, row in df_daily.iterrows():
        df_day = df_intra[df_intra['date'] == row['date']]
        if df_day.empty:
            continue

        x_start = df_day['datetime'].iloc[0]
        x_end = df_day['datetime'].iloc[-1]

        for level, color in fib_colors.items():
            fig.add_trace(go.Scatter(
                x=[x_start, x_end],
                y=[row[level], row[level]],
                mode='lines+text',
                name=level,
                text=["", f" {level}"],
                textposition="top right",
                line=dict(color=color, width=1.5 if level == 'P' else 1, dash='solid' if level == 'P' else 'dot'),
                showlegend=False,
                hoverinfo='skip'
            ))

    # Mobile-Optimized Layout Adjustments
    fig.update_layout(
        title=dict(
            text=f"<b>{selected_asset_name}</b><br><span style='font-size:12px;'>{selected_tf} - Fib Pivots</span>",
            font=dict(size=16)
        ),
        yaxis_title="",
        xaxis_title="",
        xaxis_rangeslider_visible=False,
        height=450, # Shorter height fits perfectly on most modern smartphones
        template="plotly_dark",
        margin=dict(l=5, r=45, b=10, t=55), # Tight margins, extra space on right for y-axis
        yaxis=dict(side='right', tickfont=dict(size=10)), # Y-axis on the right side
        xaxis=dict(tickfont=dict(size=10)),
        dragmode='pan' # Default to panning instead of zooming on mobile
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}) # Hides the plotly toolbar for a cleaner mobile look

# Main Render
st.markdown("### ⚡ Live Pivots")
live_mobile_view()