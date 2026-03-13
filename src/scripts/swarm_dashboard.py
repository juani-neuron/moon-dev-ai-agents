"""
Moon Dev AI Swarm Dashboard (Dash + Plotly)

Real-time dashboard that shows backtest progress as it runs:
- Price chart with trades growing candle-by-candle
- Equity curve
- Live terminal showing each AI vote as it arrives
- Summary metrics updating in real-time

Run:  ./venv/bin/python3 src/scripts/swarm_dashboard.py
Then: open http://localhost:8050

To run a backtest simultaneously:
  PYTHONPATH=. ./venv/bin/python3 src/scripts/swarm_backtester.py --start 2026-02-20 --end 2026-03-01
"""

import os
import json
import glob
import subprocess
import signal
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dash import Dash, html, dcc, callback, Input, Output, State, ctx, no_update

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / 'src' / 'data' / 'swarm_backtester'
VENV_PYTHON = str(PROJECT_ROOT / 'venv' / 'bin' / 'python3')
BACKTESTER_SCRIPT = str(PROJECT_ROOT / 'src' / 'scripts' / 'swarm_backtester.py')
LIVE_FEED = DATA_DIR / 'live_feed.jsonl'

# Track backtest subprocess
_backtest_proc = None

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def get_completed_runs():
    """Return dict of label -> run_id for completed backtests."""
    runs = {}
    if not DATA_DIR.exists():
        return runs
    for f in sorted(DATA_DIR.glob('summary_*.json')):
        name = f.stem.replace('summary_', '')
        parts = name.split('_')
        sym = parts[0]
        s = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:]}"
        e = f"{parts[2][:4]}-{parts[2][4:6]}-{parts[2][6:]}"
        runs[f"{sym}  {s} -> {e}"] = name
    return runs


def load_completed_run(run_id):
    """Load candle_log, trades, summary from a completed run."""
    with open(DATA_DIR / f'summary_{run_id}.json') as f:
        summary = json.load(f)

    candle_log = pd.read_csv(DATA_DIR / f'candle_log_{run_id}.csv')
    candle_log['timestamp'] = pd.to_datetime(candle_log['timestamp'])

    trades_file = DATA_DIR / f'trades_{run_id}.csv'
    trades = pd.read_csv(trades_file) if trades_file.exists() else pd.DataFrame()
    if not trades.empty:
        trades['entry_time'] = pd.to_datetime(trades['entry_time'])
        trades['exit_time'] = pd.to_datetime(trades['exit_time'])

    return candle_log, trades, summary


def load_live_feed():
    """Load the live feed JSONL file written by the backtester in real-time."""
    if not LIVE_FEED.exists():
        return pd.DataFrame(), pd.DataFrame(), {}

    entries = []
    with open(LIVE_FEED) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not entries:
        return pd.DataFrame(), pd.DataFrame(), {}

    # Build candle_log DataFrame
    rows = []
    for e in entries:
        row = {
            'candle_num': e['candle_num'],
            'timestamp': e['timestamp'],
            'close': e['close'],
            'open': e.get('open', e['close']),
            'high': e.get('high', e['close']),
            'low': e.get('low', e['close']),
            'action': e['action'],
            'confidence': e['confidence'],
            'event': e['event'],
            'equity': e['equity'],
            'total_candles': e.get('total_candles', '?'),
        }
        for prov, vote in e.get('votes', {}).items():
            row[f'vote_{prov}'] = vote
        rows.append(row)

    df = pd.DataFrame(rows)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Extract trades from events
    trades_list = []
    entry_data = None
    for _, r in df.iterrows():
        ev = str(r['event'])
        if 'OPEN LONG' in ev:
            entry_data = {'entry_time': r['timestamp'], 'entry_price': r['close']}
        elif entry_data and ('CLOSE' in ev or 'SL' in ev or 'TP' in ev):
            reason = 'TP' if 'TP' in ev else 'SL' if 'SL' in ev else 'SIGNAL'
            trades_list.append({
                'entry_time': entry_data['entry_time'],
                'entry_price': entry_data['entry_price'],
                'exit_time': r['timestamp'],
                'exit_price': r['close'],
                'pnl_pct': 0,  # approximate
                'pnl_usd': 0,
                'reason': reason,
                'size_usd': 0,
            })
            entry_data = None

    trades = pd.DataFrame(trades_list) if trades_list else pd.DataFrame()

    # Summary
    last_eq = df['equity'].iloc[-1]
    ret = (last_eq - 10000) / 10000 * 100
    total_candles = entries[-1].get('total_candles', len(entries))

    summary = {
        'return_pct': round(ret, 2),
        'final_equity': round(last_eq, 2),
        'total_trades': len(trades_list),
        'candles_done': len(entries),
        'total_candles': total_candles,
        'profit_factor': 0,
        'max_drawdown_pct': 0,
        'win_rate': 0,
    }

    return df, trades, summary


# ═══════════════════════════════════════════════════════════════════════════════
# CHART BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def build_chart(candle_log, trades):
    """Build the main 3-panel chart."""
    if candle_log.empty:
        fig = go.Figure()
        fig.update_layout(
            template='plotly_dark', paper_bgcolor='#0E1117', plot_bgcolor='#0E1117',
            height=600,
            annotations=[dict(text="Waiting for data...", x=0.5, y=0.5,
                              xref='paper', yref='paper', showarrow=False,
                              font=dict(size=24, color='#636EFA'))]
        )
        return fig

    vote_cols = [c for c in candle_log.columns if c.startswith('vote_')]
    model_names = [c.replace('vote_', '').title() for c in vote_cols]

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=("Price & Trades", "Equity Curve", "AI Votes")
    )

    # Candlestick chart
    fig.add_trace(go.Candlestick(
        x=candle_log['timestamp'],
        open=candle_log['open'], high=candle_log['high'],
        low=candle_log['low'], close=candle_log['close'],
        name='Price', increasing_line_color='#00CC96', decreasing_line_color='#EF553B',
    ), row=1, col=1)

    # Trade markers
    if not trades.empty and 'entry_time' in trades.columns:
        fig.add_trace(go.Scatter(
            x=trades['entry_time'], y=trades['entry_price'],
            mode='markers', name='Entry',
            marker=dict(symbol='triangle-up', size=14, color='#00CC96',
                        line=dict(width=1, color='white')),
            hovertemplate='<b>ENTRY</b><br>%{x}<br>$%{y:,.0f}<extra></extra>',
        ), row=1, col=1)

        if 'exit_time' in trades.columns:
            colors = ['#00CC96' if p > 0 else '#EF553B'
                      for p in trades.get('pnl_usd', [0]*len(trades))]
            fig.add_trace(go.Scatter(
                x=trades['exit_time'], y=trades['exit_price'],
                mode='markers', name='Exit',
                marker=dict(symbol='triangle-down', size=14, color=colors,
                            line=dict(width=1, color='white')),
                hovertemplate='<b>EXIT</b><br>%{x}<br>$%{y:,.0f}<extra></extra>',
            ), row=1, col=1)

            for _, t in trades.iterrows():
                color = '#00CC96' if t.get('pnl_usd', 0) > 0 else '#EF553B'
                fig.add_trace(go.Scatter(
                    x=[t['entry_time'], t['exit_time']],
                    y=[t['entry_price'], t['exit_price']],
                    mode='lines', line=dict(color=color, width=1, dash='dot'),
                    showlegend=False, hoverinfo='skip',
                ), row=1, col=1)

    # Equity
    fig.add_trace(go.Scatter(
        x=candle_log['timestamp'], y=candle_log['equity'],
        mode='lines', name='Equity', line=dict(color='#FFA15A', width=2),
        fill='tozeroy', fillcolor='rgba(255,161,90,0.08)',
        hovertemplate='$%{y:,.0f}<extra></extra>',
    ), row=2, col=1)

    # Vote bars
    vote_map = {'Buy': 1, 'Strong Buy': 1.5, 'Sell': -1, 'Strong Sell': -1.5,
                'Do Nothing': 0, 'Hold': 0}
    for i, (vcol, mname) in enumerate(zip(vote_cols, model_names)):
        nums = candle_log[vcol].map(lambda v: vote_map.get(v, 0))
        colors = ['#00CC96' if v > 0 else '#EF553B' if v < 0 else '#636EFA' for v in nums]
        fig.add_trace(go.Bar(
            x=candle_log['timestamp'], y=[1]*len(candle_log),
            name=mname, marker_color=colors, text=candle_log[vcol],
            hovertemplate=f'<b>{mname}</b><br>%{{x}}<br>%{{text}}<extra></extra>',
            opacity=0.8, offsetgroup=i,
        ), row=3, col=1)

    fig.update_layout(
        height=700, template='plotly_dark',
        paper_bgcolor='#0E1117', plot_bgcolor='#0E1117',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=50, r=20, t=30, b=20),
        barmode='group', hovermode='x unified',
        xaxis_rangeslider_visible=False,
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Equity ($)", row=2, col=1)
    fig.update_yaxes(visible=False, row=3, col=1)

    return fig


def build_terminal_lines(candle_log):
    """Build terminal-style log lines from candle_log."""
    if candle_log.empty:
        return [html.Div("Waiting for backtest to start...",
                         style={'color': '#636EFA', 'padding': '10px'})]

    vote_cols = [c for c in candle_log.columns if c.startswith('vote_')]
    lines = []

    for _, r in candle_log.iterrows():
        ts = pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')
        price = f"${r['close']:,.0f}"
        action = r['action']
        conf = r['confidence']
        event = r['event']
        equity = f"${r['equity']:,.0f}"

        # Vote details
        votes = []
        for vc in vote_cols:
            name = vc.replace('vote_', '')[:6].upper()
            vote = r.get(vc, '?')
            color = '#00CC96' if 'Buy' in str(vote) else '#EF553B' if 'Sell' in str(vote) else '#888'
            votes.append(html.Span(f"{name}:{vote}", style={'color': color}))
            votes.append(html.Span(" | ", style={'color': '#444'}))
        if votes:
            votes.pop()  # remove trailing separator

        # Event color
        ev_color = '#00CC96' if 'OPEN' in event or 'TP' in event else \
                   '#EF553B' if 'CLOSE' in event or 'SL' in event else '#aaa'

        # Consensus color
        cons_color = '#00CC96' if action == 'BUY' else '#EF553B' if action == 'SELL' else '#636EFA'

        candle_num = int(r.get('candle_num', 0))
        total = r.get('total_candles', '?')

        line = html.Div([
            html.Span(f"[{candle_num}/{total}] ", style={'color': '#555', 'fontSize': '12px'}),
            html.Span(f"{ts} ", style={'color': '#888'}),
            html.Span(f"{price} ", style={'color': '#ddd', 'fontWeight': 'bold'}),
            html.Span(" | ", style={'color': '#444'}),
            *votes,
            html.Span(" | ", style={'color': '#444'}),
            html.Span(f"{action} {conf}%", style={'color': cons_color, 'fontWeight': 'bold'}),
            html.Span(" | ", style={'color': '#444'}),
            html.Span(event, style={'color': ev_color}),
            html.Span(f" | Eq: {equity}", style={'color': '#FFA15A'}),
        ], style={'fontFamily': 'monospace', 'fontSize': '13px', 'padding': '2px 8px',
                  'borderBottom': '1px solid #1a1a2e'})
        lines.append(line)

    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# DASH APP
# ═══════════════════════════════════════════════════════════════════════════════

app = Dash(__name__)

app.layout = html.Div([
    # Interval for auto-refresh
    dcc.Interval(id='interval', interval=3000, n_intervals=0),

    # Store for current view mode
    dcc.Store(id='view-mode', data='live'),
    dcc.Store(id='backtest-pid', data=None),

    # Header
    html.Div([
        html.H1("🌙 Moon Dev AI Swarm", style={'margin': '0', 'fontSize': '24px'}),
    ], style={'padding': '15px 20px', 'borderBottom': '1px solid #1a1a2e'}),

    # Main layout: sidebar + content
    html.Div([
        # ── Sidebar ───────────────────────────────────────────────────────
        html.Div([
            # Run backtest section
            html.H3("🚀 Run Backtest", style={'marginTop': '0', 'fontSize': '16px'}),
            html.Div([
                html.Label("Symbol", style={'fontSize': '12px', 'color': '#888'}),
                dcc.Dropdown(
                    id='symbol-input',
                    options=[{'label': s, 'value': s} for s in ['BTC', 'ETH', 'SOL']],
                    value='BTC',
                    style={'backgroundColor': '#1a1a2e', 'color': '#ddd', 'marginBottom': '8px'},
                ),
                html.Label("Start Date", style={'fontSize': '12px', 'color': '#888'}),
                dcc.Input(id='start-date', type='text', value='2026-02-20',
                          placeholder='YYYY-MM-DD',
                          style={'width': '100%', 'padding': '6px', 'marginBottom': '8px',
                                 'backgroundColor': '#1a1a2e', 'color': '#ddd', 'border': '1px solid #333'}),
                html.Label("End Date", style={'fontSize': '12px', 'color': '#888'}),
                dcc.Input(id='end-date', type='text', value='2026-03-01',
                          placeholder='YYYY-MM-DD',
                          style={'width': '100%', 'padding': '6px', 'marginBottom': '8px',
                                 'backgroundColor': '#1a1a2e', 'color': '#ddd', 'border': '1px solid #333'}),
                html.Div(id='cost-estimate', style={'fontSize': '11px', 'color': '#888', 'marginBottom': '10px'}),
                html.Button("▶ Start Backtest", id='start-btn', n_clicks=0,
                            style={'width': '100%', 'padding': '10px', 'marginBottom': '5px',
                                   'backgroundColor': '#00CC96', 'color': 'white', 'border': 'none',
                                   'cursor': 'pointer', 'fontWeight': 'bold', 'borderRadius': '4px'}),
                html.Button("⏹ Stop", id='stop-btn', n_clicks=0,
                            style={'width': '100%', 'padding': '8px', 'marginBottom': '10px',
                                   'backgroundColor': '#EF553B', 'color': 'white', 'border': 'none',
                                   'cursor': 'pointer', 'borderRadius': '4px'}),
                html.Div(id='backtest-status', style={'fontSize': '12px', 'color': '#888'}),
            ]),

            html.Hr(style={'borderColor': '#1a1a2e'}),

            # View completed runs
            html.H3("📂 Completed Runs", style={'fontSize': '16px'}),
            dcc.Dropdown(id='run-selector', style={'backgroundColor': '#1a1a2e', 'color': '#ddd'}),
            html.Button("📊 Load Run", id='load-btn', n_clicks=0,
                        style={'width': '100%', 'padding': '8px', 'marginTop': '8px',
                               'backgroundColor': '#636EFA', 'color': 'white', 'border': 'none',
                               'cursor': 'pointer', 'borderRadius': '4px'}),

            html.Hr(style={'borderColor': '#1a1a2e'}),

            html.Button("🔴 Live Feed", id='live-btn', n_clicks=0,
                        style={'width': '100%', 'padding': '8px',
                               'backgroundColor': '#EF553B33', 'color': '#EF553B', 'border': '1px solid #EF553B',
                               'cursor': 'pointer', 'borderRadius': '4px'}),

        ], style={'width': '220px', 'padding': '15px', 'borderRight': '1px solid #1a1a2e',
                  'overflowY': 'auto', 'flexShrink': '0'}),

        # ── Main content ──────────────────────────────────────────────────
        html.Div([
            # Metrics bar
            html.Div(id='metrics-bar', style={
                'display': 'flex', 'gap': '20px', 'padding': '12px 20px',
                'borderBottom': '1px solid #1a1a2e', 'flexWrap': 'wrap',
            }),

            # Progress bar (for live mode)
            html.Div(id='progress-container', style={'padding': '0 20px'}),

            # Chart
            dcc.Graph(id='main-chart', config={'displayModeBar': False},
                      style={'height': '700px'}),

            # Terminal
            html.Div([
                html.H3("🖥 Agent Terminal", style={'fontSize': '14px', 'margin': '0 0 8px 0',
                                                     'padding': '10px 10px 0 10px'}),
                html.Div(id='terminal', style={
                    'height': '300px', 'overflowY': 'auto', 'backgroundColor': '#0a0a15',
                    'borderTop': '1px solid #1a1a2e', 'padding': '5px 0',
                }),
            ]),

        ], style={'flex': '1', 'overflow': 'hidden', 'display': 'flex', 'flexDirection': 'column'}),

    ], style={'display': 'flex', 'height': 'calc(100vh - 60px)'}),

], style={
    'backgroundColor': '#0E1117', 'color': '#ddd', 'fontFamily': 'Inter, sans-serif',
    'height': '100vh', 'overflow': 'hidden',
})


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

# Populate completed runs dropdown
@callback(Output('run-selector', 'options'), Input('interval', 'n_intervals'))
def update_run_list(_):
    runs = get_completed_runs()
    return [{'label': k, 'value': v} for k, v in runs.items()]


# Cost estimate
@callback(Output('cost-estimate', 'children'),
          Input('start-date', 'value'), Input('end-date', 'value'))
def update_cost(start, end):
    try:
        s = datetime.strptime(start, '%Y-%m-%d')
        e = datetime.strptime(end, '%Y-%m-%d')
        days = max((e - s).days, 1)
        candles = days * 24
        cost = candles * 0.03
        mins = candles * 0.4 / 60
        return f"~{candles} candles, ~{mins:.0f} min, ~${cost:.2f}"
    except Exception:
        return ""


# Start backtest
@callback(
    Output('backtest-status', 'children'),
    Output('backtest-pid', 'data'),
    Input('start-btn', 'n_clicks'),
    State('start-date', 'value'), State('end-date', 'value'),
    State('symbol-input', 'value'), State('backtest-pid', 'data'),
    prevent_initial_call=True,
)
def start_backtest(n, start, end, symbol, current_pid):
    global _backtest_proc
    if not n:
        return no_update, no_update

    # Check if already running
    if current_pid and _is_running(current_pid):
        return "Already running!", current_pid

    cmd = [VENV_PYTHON, BACKTESTER_SCRIPT,
           '--start', start, '--end', end, '--symbol', symbol]

    # Check for checkpoint
    try:
        s = datetime.strptime(start, '%Y-%m-%d')
        e = datetime.strptime(end, '%Y-%m-%d')
        ckpt = DATA_DIR / f"checkpoint_{symbol}_{s:%Y%m%d}_{e:%Y%m%d}.json"
        if ckpt.exists():
            cmd.append('--resume')
    except Exception:
        pass

    env = os.environ.copy()
    env['PYTHONPATH'] = str(PROJECT_ROOT)

    log_path = DATA_DIR / 'backtest_stdout.log'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, 'w')

    _backtest_proc = subprocess.Popen(
        cmd, stdout=log_file, stderr=subprocess.STDOUT,
        env=env, start_new_session=True,
    )
    return f"Started (PID {_backtest_proc.pid})", _backtest_proc.pid


def _is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, TypeError):
        return False


# Stop backtest
@callback(
    Output('backtest-status', 'children', allow_duplicate=True),
    Output('backtest-pid', 'data', allow_duplicate=True),
    Input('stop-btn', 'n_clicks'),
    State('backtest-pid', 'data'),
    prevent_initial_call=True,
)
def stop_backtest(n, pid):
    global _backtest_proc
    if not n or not pid:
        return no_update, no_update
    try:
        os.kill(pid, signal.SIGINT)
        _backtest_proc = None
        return "Stopped (checkpoint saved)", None
    except Exception as e:
        return f"Error: {e}", None


# Switch to live view
@callback(Output('view-mode', 'data', allow_duplicate=True),
          Input('live-btn', 'n_clicks'), prevent_initial_call=True)
def switch_live(_):
    return 'live'


# Switch to completed run view
@callback(Output('view-mode', 'data', allow_duplicate=True),
          Input('load-btn', 'n_clicks'), prevent_initial_call=True)
def switch_completed(_):
    return 'completed'


# ── Main update (every 3s) ────────────────────────────────────────────────────
@callback(
    Output('metrics-bar', 'children'),
    Output('main-chart', 'figure'),
    Output('terminal', 'children'),
    Output('progress-container', 'children'),
    Input('interval', 'n_intervals'),
    Input('view-mode', 'data'),
    State('run-selector', 'value'),
    State('backtest-pid', 'data'),
)
def update_dashboard(_, view_mode, selected_run, pid):
    # Determine data source
    if view_mode == 'live':
        candle_log, trades, summary = load_live_feed()
        is_live = True
    elif view_mode == 'completed' and selected_run:
        try:
            candle_log, trades, summary = load_completed_run(selected_run)
            is_live = False
        except Exception:
            candle_log, trades, summary = pd.DataFrame(), pd.DataFrame(), {}
            is_live = False
    else:
        candle_log, trades, summary = load_live_feed()
        is_live = True

    # Metrics
    ret = summary.get('return_pct', 0)
    ret_color = '#00CC96' if ret > 0 else '#EF553B' if ret < 0 else '#888'
    running = pid and _is_running(pid)
    status_dot = html.Span("● ", style={'color': '#00CC96' if running else '#555', 'fontSize': '18px'})

    metrics = [
        html.Div([status_dot, html.Span("LIVE" if running else "IDLE",
                  style={'fontSize': '12px', 'color': '#888'})]),
        _metric("Return", f"{ret:+.2f}%", ret_color),
        _metric("Equity", f"${summary.get('final_equity', 10000):,.0f}", '#FFA15A'),
        _metric("Trades", str(summary.get('total_trades', 0)), '#ddd'),
        _metric("Win Rate", f"{summary.get('win_rate', 0):.0f}%", '#ddd'),
        _metric("PF", f"{summary.get('profit_factor', 0):.2f}", '#ddd'),
        _metric("Max DD", f"{summary.get('max_drawdown_pct', 0):.1f}%", '#EF553B'),
    ]

    # Chart
    fig = build_chart(candle_log, trades)

    # Terminal
    terminal_lines = build_terminal_lines(candle_log)

    # Progress
    progress = []
    if is_live and not candle_log.empty:
        done = summary.get('candles_done', 0)
        total = summary.get('total_candles', done)
        if total and total != '?':
            pct = min(done / int(total) * 100, 100)
            progress = [html.Div([
                html.Div(style={
                    'width': f'{pct}%', 'height': '4px', 'backgroundColor': '#00CC96',
                    'borderRadius': '2px', 'transition': 'width 0.5s',
                }),
            ], style={
                'width': '100%', 'height': '4px', 'backgroundColor': '#1a1a2e',
                'borderRadius': '2px', 'marginTop': '8px',
            }),
            html.Div(f"{done}/{total} candles ({pct:.0f}%)",
                     style={'fontSize': '11px', 'color': '#888', 'marginTop': '4px'})]

    return metrics, fig, terminal_lines, progress


def _metric(label, value, color):
    return html.Div([
        html.Div(label, style={'fontSize': '11px', 'color': '#888'}),
        html.Div(value, style={'fontSize': '18px', 'fontWeight': 'bold', 'color': color}),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n🌙 Moon Dev AI Swarm Dashboard")
    print("   Open: http://localhost:8050\n")
    app.run(debug=False, host='0.0.0.0', port=8050)
