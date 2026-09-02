import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import websocket
from datetime import datetime

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

# --- Settings ---
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

# Higher Timeframe for Pivot Calculations
pivot_timeframes = {"1 Hour": 3600, "4 Hours": 14400, "8 Hours": 28800, "1 Day": 86400}
selected_pivot_tf = st.sidebar.selectbox("Pivot Timeframe", list(pivot_timeframes.keys()), index=3)
pivot_granularity = pivot_timeframes[selected_pivot_tf]

# Lower Timeframe for Chart Candles
chart_timeframes = {"1 Minute": 60, "5 Minutes": 300, "15 Minutes": 900, "30 Minutes": 1800, "1 Hour": 3600}
selected_tf = st.sidebar.selectbox("Chart Timeframe", list(chart_timeframes.keys()), index=2)
chart_granularity = chart_timeframes[selected_tf]

refresh_rate = st.sidebar.slider("Refresh Interval (s)", 2, 30, 20)

# Calculate optimal fetch counts
candles_per_day = 86400 // chart_granularity
intraday_count = min(candles_per_day * 3 + 20, 3000)
pivot_count = max(6, (86400 * 3) // pivot_granularity + 3)

# --- Live Fragment Container ---
@st.fragment(run_every=refresh_rate)
def live_mobile_view():
    raw_pivots, err_pivots = fetch_deriv_candles(symbol, pivot_granularity, pivot_count)
    raw_intra, err_intra = fetch_deriv_candles(symbol, chart_granularity, intraday_count)

    if err_pivots or err_intra:
        st.error(f"Error: {err_pivots or err_intra}")
        return

    if not raw_pivots or not raw_intra:
        st.warning("No data.")
        return

    # 1. Process Pivot Data (Based on selected Pivot Timeframe)
    df_pivots = pd.DataFrame(raw_pivots)
    df_pivots['datetime'] = pd.to_datetime(df_pivots['epoch'], unit='s', utc=True)

    df_pivots['prev_high'] = df_pivots['high'].shift(1)
    df_pivots['prev_low'] = df_pivots['low'].shift(1)
    df_pivots['prev_close'] = df_pivots['close'].shift(1)
    df_pivots['range'] = df_pivots['prev_high'] - df_pivots['prev_low']

    df_pivots['P'] = (df_pivots['prev_high'] + df_pivots['prev_low'] + df_pivots['prev_close']) / 3
    df_pivots['R1'] = df_pivots['P'] + (0.382 * df_pivots['range'])
    df_pivots['R2'] = df_pivots['P'] + (0.618 * df_pivots['range'])
    df_pivots['R3'] = df_pivots['P'] + (1.000 * df_pivots['range'])
    df_pivots['S1'] = df_pivots['P'] - (0.382 * df_pivots['range'])
    df_pivots['S2'] = df_pivots['P'] - (0.618 * df_pivots['range'])
    df_pivots['S3'] = df_pivots['P'] - (1.000 * df_pivots['range'])
    df_pivots.dropna(inplace=True)

    # 2. Process Intraday Chart Data
    df_intra = pd.DataFrame(raw_intra)
    df_intra['datetime'] = pd.to_datetime(df_intra['epoch'], unit='s', utc=True)

    latest_price = df_intra['close'].iloc[-1]
    current_pivots = df_pivots.iloc[-1]
    chart_start_time = df_intra['datetime'].iloc[0]

    # Metrics Grid
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Live Price", f"{latest_price:,.2f}")
    m_col2.metric(f"Current Pivot (P)", f"{current_pivots['P']:,.2f}")
    
    m_col3, m_col4 = st.columns(2)
    m_col3.metric("Fib R1", f"{current_pivots['R1']:,.2f}")
    m_col4.metric("Fib S1", f"{current_pivots['S1']:,.2f}")

    # 3. Build Plotly Chart
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

    # Plot Pivots by adding exact Timeframe duration to X-axis
    for _, row in df_pivots.iterrows():
        x_start = row['datetime']
        x_end = row['datetime'] + pd.Timedelta(seconds=pivot_granularity)
        
        # Only plot lines that appear within our active intraday window
        if x_end < chart_start_time:
            continue

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

    fig.update_layout(
        uirevision="constant",
        title=dict(
            text=f"<b>{selected_asset_name}</b><br><span style='font-size:12px;'>Pivots: {selected_pivot_tf} | Chart: {selected_tf}</span>",
            font=dict(size=16)
        ),
        yaxis_title="",
        xaxis_title="",
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_dark",
        margin=dict(l=5, r=45, b=10, t=55),
        yaxis=dict(side='right', tickfont=dict(size=10)),
        xaxis=dict(tickfont=dict(size=10)),
        dragmode='zoom'
    )

    st.plotly_chart(
        fig, 
        use_container_width=True, 
        config={
            'scrollZoom': True,
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['lasso2d', 'select2d']
        }
    )

st.markdown("### ⚡ Live Pivots")
live_mobile_view()
