import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import websocket
from datetime import datetime

st.set_page_config(page_title="Mobile Fib Pivots & Zones", layout="centered")

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

pivot_timeframes = {"1 Hour": 3600, "4 Hours": 14400, "8 Hours": 28800, "1 Day": 86400}
selected_pivot_tf = st.sidebar.selectbox("Pivot Timeframe", list(pivot_timeframes.keys()), index=3)
pivot_granularity = pivot_timeframes[selected_pivot_tf]

chart_timeframes = {"1 Minute": 60, "5 Minutes": 300, "15 Minutes": 900, "30 Minutes": 1800, "1 Hour": 3600}
selected_tf = st.sidebar.selectbox("Chart Timeframe", list(chart_timeframes.keys()), index=2)
chart_granularity = chart_timeframes[selected_tf]

refresh_rate = st.sidebar.slider("Refresh Interval (s)", 2, 30, 20)

st.sidebar.markdown("---")
# NEW SETTING: Controls how tight the zoom is on the chart
default_zoom = st.sidebar.slider("Default Zoom Window (Candles)", min_value=30, max_value=500, value=100)
show_zones = st.sidebar.checkbox("Show Confluence Zones", value=True)
show_sl = st.sidebar.checkbox("Show Stop Loss Lines", value=True)

candles_per_day = 86400 // chart_granularity
intraday_count = min(candles_per_day * 3 + 20, 3000)
pivot_count = max(30, (86400 * 3) // pivot_granularity + 15)

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

    # 1. Process Pivot Data & Confluence
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
    df_pivots['R4'] = df_pivots['P'] + (1.382 * df_pivots['range'])
    df_pivots['R5'] = df_pivots['P'] + (1.618 * df_pivots['range'])
    df_pivots['R6'] = df_pivots['P'] + (2.000 * df_pivots['range'])
    df_pivots['R7'] = df_pivots['P'] + (2.618 * df_pivots['range'])
    
    df_pivots['S1'] = df_pivots['P'] - (0.382 * df_pivots['range'])
    df_pivots['S2'] = df_pivots['P'] - (0.618 * df_pivots['range'])
    df_pivots['S3'] = df_pivots['P'] - (1.000 * df_pivots['range'])
    df_pivots['S4'] = df_pivots['P'] - (1.382 * df_pivots['range'])
    df_pivots['S5'] = df_pivots['P'] - (1.618 * df_pivots['range'])
    df_pivots['S6'] = df_pivots['P'] - (2.000 * df_pivots['range'])
    df_pivots['S7'] = df_pivots['P'] - (2.618 * df_pivots['range'])
    
    df_pivots['avg_range'] = df_pivots['range'].rolling(window=14).mean()
    df_pivots['threshold'] = df_pivots['avg_range'] * 0.15 
    
    df_pivots['res_confluence'] = abs(df_pivots['R1'] - df_pivots['prev_high']) <= df_pivots['threshold']
    df_pivots['sup_confluence'] = abs(df_pivots['S1'] - df_pivots['prev_low']) <= df_pivots['threshold']
    
    df_pivots['sweep_buffer'] = df_pivots['avg_range'] * 0.05
    df_pivots.dropna(inplace=True)

    # 2. Process Intraday Chart Data
    df_intra = pd.DataFrame(raw_intra)
    df_intra['datetime'] = pd.to_datetime(df_intra['epoch'], unit='s', utc=True)

    latest_price = df_intra['close'].iloc[-1]
    current_pivots = df_pivots.iloc[-1]
    chart_start_time = df_intra['datetime'].iloc[0]
    
    res_status = "🔴 ACTIVE" if current_pivots['res_confluence'] else "Inactive"
    sup_status = "🟢 ACTIVE" if current_pivots['sup_confluence'] else "Inactive"

    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Live Price", f"{latest_price:,.2f}")
    m_col2.metric(f"Current Pivot (P)", f"{current_pivots['P']:,.2f}")
    
    m_col3, m_col4 = st.columns(2)
    m_col3.metric("Sell Zone", res_status)
    m_col4.metric("Buy Zone", sup_status)

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

    fib_colors = {
        'R7': 'Maroon', 'S7': 'Maroon',
        'R6': 'DarkGray', 'S6': 'DarkGray',
        'R5': 'Orange', 'S5': 'Orange',
        'R4': 'Aqua',   'S4': 'Aqua',
        'R3': 'Red',    'S3': 'Red',
        'R2': 'LimeGreen', 'S2': 'LimeGreen',
        'R1': 'Magenta', 'S1': 'Magenta',
        'P': 'Yellow'
    }

    # Plot Pivots and Zones
    for _, row in df_pivots.iterrows():
        x_start = row['datetime']
        x_end = row['datetime'] + pd.Timedelta(seconds=pivot_granularity)
        
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
                line=dict(color=color, width=2 if level == 'P' else 1, dash='solid'),
                showlegend=False,
                hoverinfo='skip'
            ))
            
        if show_zones:
            if row['res_confluence']:
                res_high = max(row['R1'], row['prev_high']) + row['sweep_buffer']
                res_low = min(row['R1'], row['prev_high'])
                
                fig.add_shape(
                    type="rect",
                    x0=x_start, y0=res_low, x1=x_end, y1=res_high,
                    fillcolor="rgba(139, 0, 0, 0.2)",
                    line=dict(width=0),
                    layer="below"
                )
                if show_sl:
                    sl_price = res_high + (row['avg_range'] * 0.10)
                    fig.add_trace(go.Scatter(x=[x_start, x_end], y=[sl_price, sl_price], mode='lines', line=dict(color='crimson', width=1, dash='dash'), hoverinfo='skip', showlegend=False))

            if row['sup_confluence']:
                sup_high = max(row['S1'], row['prev_low'])
                sup_low = min(row['S1'], row['prev_low']) - row['sweep_buffer']
                
                fig.add_shape(
                    type="rect",
                    x0=x_start, y0=sup_low, x1=x_end, y1=sup_high,
                    fillcolor="rgba(0, 100, 0, 0.2)",
                    line=dict(width=0),
                    layer="below"
                )
                if show_sl:
                    sl_price = sup_low - (row['avg_range'] * 0.10)
                    fig.add_trace(go.Scatter(x=[x_start, x_end], y=[sl_price, sl_price], mode='lines', line=dict(color='crimson', width=1, dash='dash'), hoverinfo='skip', showlegend=False))

    # Calculate Default Zoom Boundaries based on user slider
    zoom_start = df_intra['datetime'].iloc[-min(default_zoom, len(df_intra))]
    zoom_end = df_intra['datetime'].iloc[-1] + pd.Timedelta(seconds=chart_granularity * 3) # padding on right

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
        
        # Lock the X-axis strictly to the slider's default range setting
        xaxis=dict(
            range=[zoom_start, zoom_end],
            tickfont=dict(size=10)
        ),
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

st.markdown("### ⚡ Live Pivots & Zones")
live_mobile_view()
