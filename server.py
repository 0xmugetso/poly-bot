import asyncio
import json
import random
import time
import ssl
import sys
import os
import re
import urllib.request
import http
from datetime import datetime, timezone, timedelta
import websockets
from backtester import Backtester

# Try using uvloop policy for high performance hosted event loop
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# Set up unverified SSL context for macOS python urllib issues
ssl._create_default_https_context = ssl._create_unverified_context

# Try importing psycopg2 for PostgreSQL support in production
try:
    import psycopg2
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

from decimal import Decimal
from collections import deque

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder handling datetime, Decimal, deque, sets, and custom objects safely."""
    def default(self, obj):
        if isinstance(obj, (datetime, Decimal)):
            return str(obj)
        if isinstance(obj, (set, deque)):
            return list(obj)
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

class DatabaseManager:
    def __init__(self, log_fn):
        self.log_fn = log_fn
        self.db_url = os.environ.get("DATABASE_URL")
        self.conn = None
        self.is_postgres = False
        
        self.connect()
        self.create_tables()
        
    def connect(self):
        if self.db_url:
            try:
                url = self.db_url
                if url.startswith("postgres://"):
                    url = url.replace("postgres://", "postgresql://", 1)
                
                if HAS_POSTGRES:
                    self.conn = psycopg2.connect(url)
                    self.conn.autocommit = True
                    self.is_postgres = True
                    self.log_fn("Connected to PostgreSQL Database.")
                    return
                else:
                    self.log_fn("psycopg2 not installed. Falling back to SQLite.")
            except Exception as e:
                self.log_fn(f"Failed to connect to PostgreSQL: {e}. Falling back to SQLite.")
                
        # Default to SQLite
        try:
            self.conn = sqlite3.connect("poly_bot.db", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.log_fn("Connected to Local SQLite Database (poly_bot.db).")
        except Exception as e:
            self.log_fn(f"Failed to initialize SQLite Database: {e}")

    def create_tables(self):
        if not self.conn:
            return
        
        cursor = self.conn.cursor()
        
        trades_sql = """
        CREATE TABLE IF NOT EXISTS trades (
            id VARCHAR(128) PRIMARY KEY,
            timestamp_utc TIMESTAMP,
            market_slug VARCHAR(128),
            strategy VARCHAR(64),
            outcome_bet VARCHAR(32),
            entry_price DECIMAL(10, 4),
            position_size DECIMAL(10, 4),
            gas_fee_gwei DECIMAL(10, 2),
            pnl_status VARCHAR(32),
            resolved_at TIMESTAMP,
            execution_mode VARCHAR(32) DEFAULT 'MAKER_LIMIT',
            strike_price DECIMAL(12, 4),
            trigger_spot_price DECIMAL(12, 4),
            time_delta_seconds DECIMAL(10, 4),
            block_reason VARCHAR(128),
            rejection_reason VARCHAR(255) DEFAULT 'NONE',
            spot_strike_delta NUMERIC DEFAULT 0.0,
            parent_order_id VARCHAR(255) DEFAULT NULL
        );
        """
        
        stats_sql = """
        CREATE TABLE IF NOT EXISTS daily_stats (
            date_utc VARCHAR(32) PRIMARY KEY,
            wallet_balance DECIMAL(12, 4),
            total_trades INTEGER,
            win_rate DECIMAL(10, 4),
            timestamp_utc TIMESTAMP
        );
        """
        
        try:
            cursor.execute(trades_sql)
            cursor.execute(stats_sql)
            if not self.is_postgres:
                self.conn.commit()
                
            # Migrations for SQLite/PostgreSQL if tables already exist
            for col, col_type in [("execution_mode", "VARCHAR(32) DEFAULT 'MAKER_LIMIT'"),
                                  ("strike_price", "DECIMAL(12, 4)"),
                                  ("trigger_spot_price", "DECIMAL(12, 4)"),
                                  ("time_delta_seconds", "DECIMAL(10, 4)"),
                                  ("block_reason", "VARCHAR(128)"),
                                  ("rejection_reason", "VARCHAR(255) DEFAULT 'NONE'"),
                                  ("spot_strike_delta", "NUMERIC DEFAULT 0.0"),
                                  ("parent_order_id", "VARCHAR(255) DEFAULT NULL")]:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type};")
                    if not self.is_postgres:
                        self.conn.commit()
                except Exception:
                    pass # column already exists
            
            # Mainnet Purge: Clean up mock records on launch under production mode
            if os.environ.get("ENV") == "LIVE_MAINNET_TRADING":
                cursor.execute("DELETE FROM trades;")
                cursor.execute("DELETE FROM daily_stats;")
                if not self.is_postgres:
                    self.conn.commit()
                self.log_fn("Mainnet mode active: Old simulation databases purged successfully.")
        except Exception as e:
            self.log_fn(f"Failed to create/purge database tables: {e}")
            
    def execute(self, query, params=None):
        if not self.conn:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params or ())
            if not self.is_postgres:
                self.conn.commit()
            return cursor
        except Exception as e:
            self.log_fn(f"Database query error: {query} -> {e}")
            return None

    def insert_trade(self, id_, timestamp, slug, strategy, outcome, price, size, gas, status,
                     execution_mode="MAKER_LIMIT", strike_price=None, trigger_spot_price=None,
                     time_delta_seconds=None, block_reason=None, rejection_reason=None, spot_strike_delta=None, parent_order_id=None):
        try:
            query = """
            INSERT INTO trades (id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                                execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason, rejection_reason, spot_strike_delta, parent_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            if self.is_postgres:
                query = query.replace("?", "%s")
            self.execute(query, (id_, timestamp, slug, strategy, outcome, price, size, gas, status,
                                 execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason,
                                 rejection_reason, spot_strike_delta, parent_order_id))
        except Exception as e:
            self.log_fn(f"[DATABASE ERROR] insert_trade exception: {e}")
        
    def resolve_trade(self, id_, status, resolved_at):
        try:
            query = """
            UPDATE trades SET pnl_status = ?, resolved_at = ? WHERE id = ?
            """
            if self.is_postgres:
                query = query.replace("?", "%s")
            self.execute(query, (status, resolved_at, id_))
        except Exception as e:
            self.log_fn(f"[DATABASE ERROR] resolve_trade exception: {e}")
 
    def load_recent_trades(self, limit=50):
        try:
            query = f"SELECT * FROM trades ORDER BY timestamp_utc DESC LIMIT {limit}"
            cursor = self.execute(query)
            if not cursor:
                return []
            
            trades = []
            rows = cursor.fetchall()
            for r in rows:
                if self.is_postgres:
                    trades.append({
                        "id": r[0],
                        "timestamp_utc": r[1].strftime("%Y-%m-%dT%H:%M:%S.000Z") if hasattr(r[1], "strftime") else str(r[1]),
                        "market_slug": r[2],
                        "strategy": r[3],
                        "outcome_bet": r[4],
                        "entry_price": float(r[5]) if r[5] is not None else 0.0,
                        "position_size": float(r[6]) if r[6] is not None else 0.0,
                        "gas_fee_gwei": float(r[7]) if r[7] is not None else 0.0,
                        "pnl_status": r[8],
                        "resolved_at": r[9]
                    })
                else:
                    trades.append({
                        "id": r["id"],
                        "timestamp_utc": r["timestamp_utc"],
                        "market_slug": r["market_slug"],
                        "strategy": r["strategy"],
                        "outcome_bet": r["outcome_bet"],
                        "entry_price": float(r["entry_price"]) if r["entry_price"] is not None else 0.0,
                        "position_size": float(r["position_size"]) if r["position_size"] is not None else 0.0,
                        "gas_fee_gwei": float(r["gas_fee_gwei"]) if r["gas_fee_gwei"] is not None else 0.0,
                        "pnl_status": r["pnl_status"],
                        "resolved_at": r["resolved_at"]
                    })
            return trades[::-1]
        except Exception as e:
            self.log_fn(f"[DATABASE ERROR] load_recent_trades exception: {e}")
            return []
        
    def save_daily_stats(self, date_str, balance, total_trades, win_rate, timestamp):
        check_query = "SELECT date_utc FROM daily_stats WHERE date_utc = ?"
        if self.is_postgres:
            check_query = check_query.replace("?", "%s")
        
        cursor = self.execute(check_query, (date_str,))
        if cursor and cursor.fetchone():
            update_query = """
            UPDATE daily_stats SET wallet_balance = ?, total_trades = ?, win_rate = ?, timestamp_utc = ?
            WHERE date_utc = ?
            """
            if self.is_postgres:
                update_query = update_query.replace("?", "%s")
                self.execute(update_query, (balance, total_trades, win_rate, timestamp, date_str))
            else:
                self.execute(update_query, (balance, total_trades, win_rate, timestamp, date_str))
        else:
            insert_query = """
            INSERT INTO daily_stats (date_utc, wallet_balance, total_trades, win_rate, timestamp_utc)
            VALUES (?, ?, ?, ?, ?)
            """
            if self.is_postgres:
                insert_query = insert_query.replace("?", "%s")
            self.execute(insert_query, (date_str, balance, total_trades, win_rate, timestamp))

import sqlite3

class TradingEngine:
    def __init__(self):
        # Wallet and performance stats
        self.initial_wallet = 1420.55
        self.wallet = self.initial_wallet
        self.net_pnl_usdc = 0.0
        self.net_pnl_pct = 0.0
        self.wins = 0
        self.losses = 0
        self.arbitrage_wins = 0
        self.penny_wins = 0
        self.total_trades_count = 0
        self.resolved_trades_count = 0
        
        # Configuration
        self.max_slippage = 0.01
        self.max_position_size_usdc = float(os.environ.get("MAX_POSITION_SIZE_USDC", 0.10))
        self.min_profit_threshold_usdc = float(os.environ.get("MIN_PROFIT_THRESHOLD_USDC", 0.02))
        self.env = os.environ.get("ENV", "SIMULATION")
        
        # Live market tracking
        self.live_prices = {"BTC": 67250.0, "ETH": 3480.0, "SOL": 142.50, "XRP": 0.58}
        self.spot_prices = self.live_prices
        self.live_obi = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "XRP": 0.0}
        self.price_decimals = {"BTC": 1, "ETH": 2, "SOL": 2, "XRP": 4}
        self.active_markets = {}  # symbol -> market_details
        self.symbols = ["BTC", "ETH", "SOL", "XRP"]
        self.rolling_prices = {sym: [] for sym in self.symbols}
        self.volatility_coefficient = 0.15
        
        # Activity and logs (bounded deques to cap memory footprint < 10 MB)
        from collections import deque
        self.activity_log = deque(maxlen=1000)
        self.system_logs = deque(maxlen=1000)
        
        self.status = "RUNNING"
        self.latency_ms = 1.4
        self.rpc_node_health = "HEALTHY"
        self.clients = set()
        
        # State locks and limit fallback orders
        self.market_locks = {}           # slug -> status (e.g. LOCKED_STRATEGY_A)
        self.resting_limit_orders = []    # list of active resting orders
        self.priority_gas_gwei = 65      # Polygon priority gas fee Gwei
        self.matic_price = 0.55          # Matic price in USDC
        self.clob_clock_offset = 0.0     # Synchronized clock offset
        
        self.add_system_log("POLY-BOT trading engine initialized.")
        
        # Database Integration
        self.db = DatabaseManager(self.add_system_log)
        self.rehydrate_state()

    def rehydrate_state(self):
        recent_trades = self.db.load_recent_trades(50)
        self.add_system_log(f"Rehydrating state: loaded {len(recent_trades)} historical trades from database.")
        
        for t in recent_trades:
            trade_obj = {
                "id": t["id"],
                "datetime_utc": t["timestamp_utc"],
                "slug": t["market_slug"],
                "outcome": t["outcome_bet"],
                "price": t["entry_price"],
                "size": t["position_size"],
                "status": t["pnl_status"],
                "tx_hash": t["id"],
                "strategy": t["strategy"]
            }
            self.activity_log.append(trade_obj)
            
            if t["pnl_status"] != "PENDING":
                self.resolved_trades_count += 1
                self.total_trades_count += 1
                
                cost = t["position_size"] * t["entry_price"]
                if t["pnl_status"] == "WIN":
                    self.wins += 1
                    if "Arbitrage" in t["strategy"]:
                        self.arbitrage_wins += 1
                    else:
                        self.penny_wins += 1
                    self.wallet += (t["position_size"] - cost)
                    self.net_pnl_usdc += (t["position_size"] - cost)
                else:
                    self.losses += 1
                    self.wallet -= cost
                    self.net_pnl_usdc -= cost
                    
        if len(recent_trades) > 0:
            self.net_pnl_pct = (self.net_pnl_usdc / self.initial_wallet) * 100
            self.add_system_log(f"State rehydrated. Current Wallet Balance: ${self.wallet:.2f} USDC | Wins: {self.wins} | Losses: {self.losses}")

    def add_activity(self, slug, outcome, price, size, status, tx_hash=None, reason=None):
        if not tx_hash:
            tx_hash = f"0x{random.randbytes(32).hex()}"
        
        if not reason:
            if status == "WIN":
                reason = "Target outcome resolved successfully (Profit secured)"
            elif status == "LOSS":
                reason = "Target outcome expired worthless (Loss incurred)"
            elif status == "LIMIT_POSTED":
                reason = "Maker Limit Order posted to orderbook tail (Waiting for fill)"
            elif status == "PENDING":
                reason = "Limit order filled (Waiting for outcome resolution)"
            elif status == "CANCELLED":
                reason = "Failsafe active: Order cancelled before expiry"
            else:
                reason = "Status updated"

        trade = {
            "datetime_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "slug": slug,
            "outcome": outcome,
            "price": price,
            "size": size,
            "status": status,
            "tx_hash": tx_hash,
            "reason": reason
        }
        self.activity_log.append(trade)
        return trade

    def add_system_log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {msg}"
        self.system_logs.append(log_line)
        print(log_line)

    def get_state(self):
        # Build state dict to stream to frontend
        return {
            "wallet": round(self.wallet, 2),
            "net_pnl_usdc": round(self.net_pnl_usdc, 2),
            "net_pnl_pct": round(self.net_pnl_pct, 2),
            "wins": self.wins,
            "losses": self.losses,
            "arbitrage_wins": self.arbitrage_wins,
            "penny_wins": self.penny_wins,
            "total_trades_count": self.total_trades_count,
            "resolved_trades_count": self.resolved_trades_count,
            "spot_prices": self.spot_prices,
            "live_obi": self.live_obi,
            "active_markets": list(self.active_markets.values()),
            "activity_log": list(self.activity_log),
            "system_logs": list(self.system_logs)[-25:],
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "rpc_node_health": self.rpc_node_health,
            "market_locks": self.market_locks,
            "resting_limit_orders": self.resting_limit_orders,
            "priority_gas_gwei": self.priority_gas_gwei,
            "matic_price": self.matic_price,
            "clob_clock_offset": self.clob_clock_offset,
            "version": "2.0.8"
        }

    async def broadcast(self):
        if not self.clients:
            return
        state_str = json.dumps(self.get_state(), cls=CustomJSONEncoder)
        disconnected = set()
        for client in list(self.clients):
            try:
                await client.send(state_str)
            except Exception:
                disconnected.add(client)
        for client in disconnected:
            if client in self.clients:
                self.clients.remove(client)

    async def handle_ws(self, websocket, path=None):
        self.clients.add(websocket)
        self.add_system_log(f"Frontend client connected. Total clients: {len(self.clients)}")
        try:
            # Send initial engine state immediately on connection open
            await websocket.send(json.dumps(self.get_state(), cls=CustomJSONEncoder))
            async for message in websocket:
                # Receive commands from frontend
                data = json.loads(message)
                action = data.get("action")
                if action == "toggle_status":
                    self.status = "RUNNING" if self.status == "PAUSED" else "PAUSED"
                    self.add_system_log(f"Engine status changed to: {self.status}")
                elif action == "trigger_gas_bump":
                    self.latency_ms = max(0.5, self.latency_ms - 0.3)
                    self.add_system_log("Manual gas priority bump triggered. Network latency optimized.")
                elif action in ["request_csv_data", "export_telemetry"]:
                    limit_val = data.get("limit")
                    csv_content, filename = self.generate_csv_string(limit=limit_val)
                    await asyncio.to_thread(self.export_trades_to_csv, filename)
                    await websocket.send(json.dumps({
                        "type": "csv_data",
                        "filename": filename,
                        "csv_content": csv_content
                    }, cls=CustomJSONEncoder))
                elif action == "run_backtest":
                    params = data.get("params", {})
                    self.add_system_log("Running historical backtest simulation request...")
                    try:
                        results = await asyncio.wait_for(asyncio.to_thread(self.run_backtest_simulation, params), timeout=60.0)
                    except asyncio.TimeoutError:
                        results = {
                            "error": "Backtest execution timed out (60s limit exceeded).",
                            "logs": ["[BACKTEST TIMEOUT] Simulation aborted: execution exceeded 60 seconds timeout limit."]
                        }
                    await websocket.send(json.dumps({
                        "type": "backtest_results",
                        "results": results
                    }, cls=CustomJSONEncoder))
        except Exception as e:
            import traceback
            err_str = f"[WS_ERROR] WebSocket connection exception: {e}"
            print(f"{err_str}\n{traceback.format_exc()}")
            self.add_system_log(err_str)
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
            self.add_system_log("Frontend client disconnected.")

    def supervise_task(self, name, coroutine_fn):
        """Wraps a background asyncio task in a supervisor watchdog.
        If the background loop encounters an exception or dies, logs the traceback
        directly to self.system_logs for the UI console monitor and restarts within 2s.
        """
        async def _run():
            while True:
                try:
                    self.add_system_log(f"[SUPERVISOR] Starting background loop task: '{name}'")
                    await coroutine_fn()
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    log_msg = f"[TASK_CRASH] Background loop '{name}' died: {e}. Restarting in 2s..."
                    self.add_system_log(log_msg)
                    print(f"{log_msg}\n{tb}")
                    await self.broadcast()
                    await asyncio.sleep(2.0)
        return asyncio.create_task(_run())

    async def fetch_pyth_rest_fallback(self):
        """Fetches Pyth REST price update fallback if WS ticks stall."""
        try:
            feed_ids = [
                "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
                "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
                "0xec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8"
            ]
            feed_map = {
                feed_ids[0]: "BTC",
                feed_ids[1]: "ETH",
                feed_ids[2]: "SOL",
                feed_ids[3]: "XRP"
            }
            url = f"https://hermes.pyth.network/v2/updates/price/latest?" + "&".join(f"ids[]={fid}" for fid in feed_ids)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            ctx = ssl._create_unverified_context()
            res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=3, context=ctx)
            data = json.loads(res.read().decode())
            for feed in data.get("parsed", []):
                fid = feed.get("id", "").lower()
                norm_id = fid if fid.startswith("0x") else f"0x{fid}"
                symbol = feed_map.get(norm_id)
                if symbol:
                    p = feed.get("price", {})
                    raw_price = float(p.get("price", 0))
                    expo = int(p.get("expo", 0))
                    spot_price = raw_price * (10 ** expo)
                    if spot_price > 0:
                        self.live_prices[symbol] = spot_price
                        self.spot_prices[symbol] = spot_price
        except Exception:
            pass

    async def pyth_price_ws(self):
        """Streams sub-second institutional price ticks from Pyth Network Hermes WebSocket (wss://hermes.pyth.network/ws).
        Subscribes using raw hex IDs without '0x' prefix and implements an instant 2s REST fallback.
        """
        pyth_url = "wss://hermes.pyth.network/ws"
        raw_ids_map = {
            "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43": "BTC",
            "e62df6e014e2bf977008b283f31b2b5b093630f7b321700114357900dac22541": "BTC",
            "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace": "ETH",
            "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d": "SOL",
            "ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8": "XRP",
            "ec5d39982219b5d37415893e3612d1c68d1dce7d63ef269ef50c1f6c770024f2": "XRP"
        }
        
        subscription_ids = list(raw_ids_map.keys())
        retry_delay = 0.5
        last_tick_time = time.time()

        while True:
            try:
                self.add_system_log("[PYTH HERMES] Connecting to Pyth Network Hermes WebSocket (wss://hermes.pyth.network/ws)...")
                ssl_context = ssl._create_unverified_context()
                async with websockets.connect(pyth_url, ssl=ssl_context) as ws:
                    self.add_system_log("[PYTH HERMES] Connected. Subscribing using raw hex feed IDs (stripped of '0x' prefix)...")
                    sub_msg = {
                        "type": "subscribe",
                        "ids": subscription_ids
                    }
                    await ws.send(json.dumps(sub_msg))
                    retry_delay = 0.5
                    
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            last_tick_time = time.time()
                        except asyncio.TimeoutError:
                            if time.time() - last_tick_time >= 2.0:
                                await self.fetch_pyth_rest_fallback()
                            continue
                            
                        data = json.loads(msg)
                        if data.get("type") == "price_update":
                            feed = data.get("price_feed", {})
                            feed_id = feed.get("id", "").lower().replace("0x", "")
                            symbol = raw_ids_map.get(feed_id)
                            
                            if symbol:
                                p_obj = feed.get("price", {})
                                raw_price = float(p_obj.get("price", 0))
                                expo = int(p_obj.get("expo", 0))
                                spot_price = raw_price * (10 ** expo)
                                
                                if spot_price > 0:
                                    self.live_prices[symbol] = spot_price
                                    self.spot_prices[symbol] = spot_price
                                    last_tick_time = time.time()
            except Exception as e:
                self.add_system_log(f"[PYTH HERMES] Connection error: {e}. Executing REST fallback & reconnecting in {retry_delay:.2f}s...")
                await self.fetch_pyth_rest_fallback()
                await asyncio.sleep(retry_delay)
                retry_delay = min(5.0, retry_delay * 2.0)

    async def binance_price_feed(self):
        """Fallback Binance price stream if needed."""
        await self.pyth_price_ws()

    def calculate_std(self, prices):
        if len(prices) < 2:
            return 0.0
        mean = sum(prices) / len(prices)
        variance = sum((x - mean) ** 2 for x in prices) / (len(prices) - 1)
        return variance ** 0.5

    async def initialize_rolling_prices(self):
        """Pre-populates 30m rolling prices cache on startup via Binance REST API."""
        ctx = ssl._create_unverified_context()
        for symbol in ["BTC", "ETH", "SOL", "XRP"]:
            ticker = f"{symbol}USDT"
            url = f"https://api.binance.com/api/v3/klines?symbol={ticker}&interval=1m&limit=30"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=ctx)
                data = json.loads(res.read().decode())
                closes = [float(c[4]) for c in data]
                self.rolling_prices[symbol] = closes
                if closes:
                    self.live_prices[symbol] = closes[-1]
            except Exception as e:
                try:
                    url_us = f"https://api.binance.us/api/v3/klines?symbol={ticker}&interval=1m&limit=30"
                    req_us = urllib.request.Request(url_us, headers={'User-Agent': 'Mozilla/5.0'})
                    res_us = await asyncio.to_thread(urllib.request.urlopen, req_us, timeout=5, context=ctx)
                    data_us = json.loads(res_us.read().decode())
                    closes_us = [float(c[4]) for c in data_us]
                    self.rolling_prices[symbol] = closes_us
                    if closes_us:
                        self.live_prices[symbol] = closes_us[-1]
                except Exception:
                    pass

    async def rolling_prices_update_loop(self):
        """Appends current spot prices to rolling 30m cache every 60s."""
        while True:
            await asyncio.sleep(60)
            for symbol in ["BTC", "ETH", "SOL", "XRP"]:
                spot = self.spot_prices.get(symbol)
                if spot and spot > 0:
                    self.rolling_prices[symbol].append(spot)
                    if len(self.rolling_prices[symbol]) > 30:
                        self.rolling_prices[symbol].pop(0)

    async def sync_clob_clock(self):
        """Continuously measures CLOB clock offset relative to local system time."""
        while True:
            try:
                req = urllib.request.Request("https://clob.polymarket.com/time", headers={'User-Agent': 'Mozilla/5.0'})
                ctx = ssl._create_unverified_context()
                t0 = time.time()
                res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=ctx)
                t1 = time.time()
                data = json.loads(res.read().decode())
                clob_time = float(data.get("time", t1))
                rtt = t1 - t0
                synced_clob_time = clob_time + (rtt / 2.0)
                self.clob_clock_offset = synced_clob_time - t1
            except Exception:
                pass
            await asyncio.sleep(60)

    async def sync_polymarket_gamma_api(self):
        """Discovers active and upcoming 5M crypto contracts via /events?slug= and /markets/slug/ endpoints."""
        ctx = ssl._create_unverified_context()
        while True:
            try:
                t_now = int(time.time() + self.clob_clock_offset)
                current_epoch = (t_now // 300) * 300
                
                # Instantly purge any past/expired epochs to maintain strictly 4 active cards
                for slug, m in list(self.active_markets.items()):
                    if m.get("close_time", 0) <= t_now:
                        self.active_markets.pop(slug, None)
                
                for sym in ["btc", "eth", "sol", "xrp"]:
                    slug = f"{sym}-updown-5m-{current_epoch}"
                    if slug in self.active_markets and not self.active_markets[slug].get("resolved"):
                        continue
                            
                        # Direct endpoints: /events?slug= and /markets/slug/
                        urls = [
                            f"https://gamma-api.polymarket.com/events?slug={slug}",
                            f"https://gamma-api.polymarket.com/markets/slug/{slug}"
                        ]
                        
                        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
                        m_data = None
                        for url in urls:
                            req = urllib.request.Request(url, headers=headers)
                            try:
                                res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=3, context=ctx)
                                data = json.loads(res.read().decode())
                                if data:
                                    if isinstance(data, list) and len(data) > 0:
                                        evt = data[0]
                                        mkts = evt.get("markets", [evt])
                                        if mkts and isinstance(mkts[0], dict):
                                            m_data = mkts[0]
                                            m_data["_title_fallback"] = evt.get("title", "") or evt.get("question", "")
                                            break
                                    elif isinstance(data, dict):
                                        m_data = data
                                        break
                            except Exception:
                                pass
                                
                        if m_data and isinstance(m_data, dict):
                            question = m_data.get("question", "") or m_data.get("title", "") or m_data.get("_title_fallback", "")
                            match = re.search(r"\$(\d+(?:\.\d+)?)", question)
                            symbol = sym.upper()
                            strike = float(match.group(1).replace(",", "")) if match else self.spot_prices.get(symbol, 0.0)
                            
                            tokens_raw = m_data.get("clobTokenIds", "[]")
                            tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else (tokens_raw or [])
                            condition_id = m_data.get("conditionId")
                            
                            self.active_markets[slug] = {
                                "slug": slug,
                                "symbol": symbol,
                                "strike_price": strike,
                                "epoch_start": current_epoch,
                                "close_time": current_epoch + 300,
                                "tokens": tokens,
                                "conditionId": condition_id,
                                "resolved": False,
                                "price_yes": 0.50,
                                "price_no": 0.50,
                                "orders_posted": False
                            }
                            self.add_system_log(f"[MARKET DISCOVERY] Active 5M market discovered: {slug} @ Strike ${strike:,.2f}")
            except Exception as e:
                self.add_system_log(f"[GAMMA_API_ERROR] Polymarket Gamma API market discovery failed: {e}")
                
            await asyncio.sleep(1.0)

    async def fetch_active_polymarket_events(self):
        """Discovers current 5M contracts across monitored assets."""
        t_now = time.time() + self.clob_clock_offset
        current_5m_epoch = int(t_now) - (int(t_now) % 300)
        
        ctx = ssl._create_unverified_context()
        for symbol in ["BTC", "ETH", "SOL", "XRP"]:
            slug = f"{symbol.lower()}-updown-5m-{current_5m_epoch}"
            if slug in self.active_markets and not self.active_markets[slug].get("resolved"):
                continue
                
            try:
                url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=ctx)
                data = json.loads(res.read().decode())
                
                if len(data) > 0:
                    m = data[0]
                    question = m.get("question", "")
                    match = re.search(r"\$(\d+(?:\.\d+)?)", question)
                    strike = float(match.group(1).replace(",", "")) if match else self.spot_prices.get(symbol, 0.0)
                    
                    tokens_raw = m.get("clobTokenIds", "[]")
                    if isinstance(tokens_raw, str):
                        tokens = json.loads(tokens_raw)
                    else:
                        tokens = tokens_raw or []
                        
                    condition_id = m.get("conditionId")
                    
                    self.active_markets[slug] = {
                        "slug": slug,
                        "symbol": symbol,
                        "strike_price": strike,
                        "epoch_start": current_5m_epoch,
                        "close_time": current_5m_epoch + 300,
                        "tokens": tokens,
                        "conditionId": condition_id,
                        "resolved": False,
                        "price_yes": 0.50,
                        "price_no": 0.50,
                        "orders_posted": False
                    }
            except Exception as e:
                pass

    async def market_management_loop(self):
        """Main engine execution loop evaluating active 5M markets, expiration-window order placement, fills, and epoch turnover."""
        while True:
            await self.fetch_active_polymarket_events()
            t = time.time() + self.clob_clock_offset
            
            for slug, market in list(self.active_markets.items()):
                if market.get("resolved"):
                    continue
                    
                time_remaining = market["close_time"] - t
                symbol = market["symbol"]
                strike = market["strike_price"]
                spot = self.spot_prices.get(symbol, strike)
                
                # Dynamic spot vs strike diff
                delta = spot - strike
                
                # Simulated order book YES/NO pricing derived from spot vs strike delta
                volatility_factor = 2.0 if symbol in ["BTC", "BNB"] else 0.1
                val = -delta / volatility_factor
                val = max(-50.0, min(50.0, val))
                price_yes = 1 / (1 + 2.718 ** val)
                price_yes = max(0.01, min(0.99, price_yes))
                price_no = 1 - price_yes
                
                market["time_remaining"] = time_remaining
                market["price_yes"] = round(price_yes, 2)
                market["price_no"] = round(price_no, 2)
                
                # Expiration Window Order Placement (Final 5.0s down to 0.6s before market close)
                if time_remaining <= 5.0 and time_remaining >= 0.6 and not market.get("orders_posted"):
                    market["orders_posted"] = True
                    asyncio.create_task(self.place_resting_orders_both_sides(market))
                    self.add_system_log(f"[EXPIRATION WINDOW] Deployed expiration boundary limit ladder for {slug} (T-{time_remaining:.1f}s remaining)")

                # WORKER 1: LIVE FILL WORKER (Evaluates resting orders during active window)
                if time_remaining > 0 and t < market["close_time"]:
                    for order in list(self.resting_limit_orders):
                        if order["slug"] == slug:
                            is_fill = False
                            if order["outcome"] == "Up" and price_yes <= order["price"]:
                                is_fill = True
                            elif order["outcome"] == "Down" and price_no <= order["price"]:
                                is_fill = True
                                
                            if is_fill:
                                cost = order["size"] * order["price"]
                                if self.wallet >= cost:
                                    self.wallet -= cost
                                    self.total_trades_count += 1
                                    
                                    matched_trade = None
                                    for trade in self.activity_log:
                                        if trade["tx_hash"] == order["tx_hash"]:
                                            matched_trade = trade
                                            break
                                    
                                    if matched_trade:
                                        matched_trade["status"] = "FILLED"
                                        matched_trade["reason"] = "Resting limit order filled by market taker in expiration window"
                                        self.db.resolve_trade(order["tx_hash"], "FILLED", None)
                                    else:
                                        trade = self.add_activity(slug, order["outcome"], order["price"], order["size"], "FILLED", order["tx_hash"], reason="Resting limit order filled by market taker in expiration window")
                                        trade["strategy"] = order["strategy"]
                                        self.db.insert_trade(
                                            order["tx_hash"], 
                                            trade["datetime_utc"], 
                                            slug, 
                                            order["strategy"], 
                                            order["outcome"], 
                                            order["price"], 
                                            order["size"], 
                                            self.priority_gas_gwei, 
                                            "FILLED",
                                            execution_mode="MAKER_LIMIT",
                                            strike_price=order.get("strike_price"),
                                            trigger_spot_price=order.get("trigger_spot_price"),
                                            time_delta_seconds=order.get("time_delta_seconds")
                                        )
                                    
                                    self.add_system_log(f"[MAKER LIMIT FILLED] Limit order for {order['outcome']} filled on {slug} @ ${order['price']:.3f} (Cost: ${cost:.2f} USDC)")
                                self.resting_limit_orders.remove(order)

                # WORKER 2: EPOCH TURNOVER RESOLVER (Triggers immediately when time_remaining <= 0.0)
                if time_remaining <= 0.0:
                    resolved_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    
                    # A. Cancel all unfilled resting limit orders immediately at time_remaining <= 0.0
                    for order in list(self.resting_limit_orders):
                        if order["slug"] == slug:
                            self.resting_limit_orders.remove(order)
                            for trade in self.activity_log:
                                if trade["tx_hash"] == order["tx_hash"] and trade["status"] == "LIMIT_POSTED":
                                    trade["status"] = "EXPIRED_UNFILLED"
                                    trade["reason"] = "Market epoch closed without fill at target limit price ($0.00 USDC cost change)"
                                    self.db.resolve_trade(order["tx_hash"], "EXPIRED_UNFILLED", resolved_time)

                    # B. Update SQLite DB to guarantee 100% of LIMIT_POSTED rows for this slug transition to EXPIRED_UNFILLED
                    self.db.execute(
                        "UPDATE trades SET pnl_status = 'EXPIRED_UNFILLED', resolved_at = ? WHERE market_slug = ? AND pnl_status = 'LIMIT_POSTED'",
                        (resolved_time, slug)
                    )

                    # C. Trigger async Oracle settlement resolution task for FILLED orders
                    condition_id = market.get("conditionId")
                    asyncio.create_task(self.poll_and_resolve_market(slug, strike, condition_id))
                    
                    # D. Purge expired market slug from active_markets
                    self.active_markets.pop(slug, None)
                    if slug in self.market_locks:
                        self.market_locks.pop(slug)
            
            await self.broadcast()
            await asyncio.sleep(0.5)

    async def get_clob_order_status(self, order_id):
        """Queries the Polymarket CLOB GET /order/{order_id} endpoint for status."""
        try:
            url = f"https://clob.polymarket.com/order/{order_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            ctx = ssl._create_unverified_context()
            res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=ctx)
            data = json.loads(res.read().decode())
            return data.get("status") # e.g. "FILLED", "PARTIALLY_FILLED", "UNFILLED"
        except Exception:
            # Fallback check for simulated/dry-run orders
            for trade in self.activity_log:
                if trade["tx_hash"] == order_id:
                    if trade["status"] in ["PENDING", "FILLED", "WIN", "LOSS"]:
                        return "FILLED"
            return "UNFILLED"

    async def resolve_market_via_oracle(self, slug, condition_id=None):
        """Queries Gamma API directly to retrieve the official settlement status and winner."""
        try:
            if condition_id and not condition_id.startswith("cond-"):
                url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}&closed=true"
            else:
                url = f"https://gamma-api.polymarket.com/markets?slug={slug}&closed=true"
                
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            ctx = ssl._create_unverified_context()
            res = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=ctx)
            data = json.loads(res.read().decode())
            if len(data) > 0:
                m = data[0]
                if m.get("closed") or m.get("active") is False:
                    outcome_prices_str = m.get("outcomePrices")
                    if outcome_prices_str:
                        if isinstance(outcome_prices_str, str):
                            prices = json.loads(outcome_prices_str)
                        else:
                            prices = outcome_prices_str
                        
                        if len(prices) >= 2:
                            p_yes = float(prices[0])
                            p_no = float(prices[1])
                            if p_yes > 0.9 or p_no < 0.1:
                                return "Up"
                            elif p_no > 0.9 or p_yes < 0.1:
                                return "Down"
        except Exception as e:
            self.add_system_log(f"[WARNING] Oracle resolution check failed for {slug} (conditionId: {condition_id}): {e}")
        return None

    async def poll_and_resolve_market(self, slug, strike, condition_id=None):
        """Asynchronously polls the Polymarket Gamma API until resolved, then settles trades."""
        self.add_system_log(f"[ORACLE] Started settlement resolution polling task for: {slug} (conditionId: {condition_id})")
        retry_delay = 1.0
        
        while True:
            winner = await self.resolve_market_via_oracle(slug, condition_id)
            if winner:
                resolved_any = False
                resolved_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

                # 1. Settle in-memory activity_log trades
                for trade in list(self.activity_log):
                    if trade.get("slug") == slug and trade.get("status") in ["PENDING", "FILLED"]:
                        resolved_any = True
                        is_win = (trade["outcome"] == winner)
                        cost = trade["size"] * trade["price"]
                        if is_win:
                            trade["status"] = "WIN"
                            trade["reason"] = f"Target outcome resolved successfully: {trade['outcome']} won at close"
                            self.wins += 1
                            if "Arbitrage" in trade.get("strategy", ""):
                                self.arbitrage_wins += 1
                            else:
                                self.penny_wins += 1
                            payout = trade["size"] * 1.0
                            self.wallet += payout
                            self.net_pnl_usdc += (payout - cost)
                        else:
                            trade["status"] = "LOSS"
                            trade["reason"] = f"Target outcome expired worthless: opposite outcome won at close"
                            self.losses += 1
                            self.net_pnl_usdc -= cost
                        
                        self.resolved_trades_count += 1
                        self.net_pnl_pct = (self.net_pnl_usdc / self.initial_wallet) * 100
                        self.add_system_log(f"[ORACLE] Round Settled: {slug} | Winner: {winner} | Trade: {trade['status']}")
                        self.db.resolve_trade(trade["tx_hash"], trade["status"], resolved_time)

                # 2. Query SQLite DB to settle any filled trades that fell out of activity_log memory queue
                cursor = self.db.execute("SELECT id, outcome_bet, entry_price, position_size, strategy FROM trades WHERE market_slug = ? AND pnl_status IN ('PENDING', 'FILLED')", (slug,))
                if cursor:
                    rows = cursor.fetchall()
                    for r in rows:
                        resolved_any = True
                        tx_id = r[0]
                        out_bet = r[1]
                        e_price = float(r[2]) if r[2] is not None else 0.0
                        pos_size = float(r[3]) if r[3] is not None else 0.0
                        strat = r[4] or ""
                        cost = pos_size * e_price
                        is_win = (out_bet == winner)
                        st = "WIN" if is_win else "LOSS"
                        if is_win:
                            self.wins += 1
                            if "Arbitrage" in strat:
                                self.arbitrage_wins += 1
                            else:
                                self.penny_wins += 1
                            payout = pos_size * 1.0
                            self.wallet += payout
                            self.net_pnl_usdc += (payout - cost)
                        else:
                            self.losses += 1
                            self.net_pnl_usdc -= cost
                        self.resolved_trades_count += 1
                        self.db.resolve_trade(tx_id, st, resolved_time)
                        self.add_system_log(f"[ORACLE] DB Trade Settled: {slug} | Winner: {winner} | Trade: {st}")
                
                if resolved_any:
                    self.add_system_log(f"[ORACLE] Cleaned up resolved contract state for: {slug}")
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    win_rate = (self.wins / (self.wins + self.losses) * 100) if (self.wins + self.losses) > 0 else 0.0
                    self.db.save_daily_stats(today_str, self.wallet, self.wins + self.losses, win_rate, now_str)
                    await self.broadcast()
                return
                
            await asyncio.sleep(retry_delay)
            retry_delay = min(10.0, retry_delay + 1.0)

    async def place_resting_orders_both_sides(self, market):
        """Places passive resting maker limit buy orders on BOTH sides (Up and Down) simultaneously using EGIG scaling."""
        slug = market["slug"]
        parent_order_id_up = f"parent-up-{slug}"
        parent_order_id_down = f"parent-down-{slug}"
        
        round_budget = getattr(self, "max_order_size_usdc", 10.0)
        # Dynamic EGIG Position Sizing Matrix: 60% @ $0.01 (600 sh), 30% @ $0.02 (150 sh), 10% @ $0.03 (33 sh)
        levels = [
            {"price": 0.010, "budget": 0.60 * round_budget},
            {"price": 0.020, "budget": 0.30 * round_budget},
            {"price": 0.030, "budget": 0.10 * round_budget}
        ]
        
        tasks = []
        # Place Up orders
        for level in levels:
            tasks.append(
                self.post_maker_limit_order_async(
                    slug, "Up", level["price"], level["budget"], strategy="Strategy B (Penny Sweep)", parent_order_id=parent_order_id_up
                )
            )
            
        # Place Down orders
        for level in levels:
            tasks.append(
                self.post_maker_limit_order_async(
                    slug, "Down", level["price"], level["budget"], strategy="Strategy B (Penny Sweep)", parent_order_id=parent_order_id_down
                )
            )
            
        await asyncio.gather(*tasks)

    async def post_maker_limit_order_async(self, slug, outcome, target_price, budget_usdc, strategy="Strategy B (Penny Sweep)", parent_order_id=None):
        """Asynchronously posts resting maker limit buy orders."""
        await asyncio.sleep(random.uniform(0.01, 0.05))
        
        symbol = slug.split("-")[0].upper()
        strike = self.active_markets.get(slug, {}).get("strike_price", 0.0)
        spot = self.spot_prices.get(symbol, strike)
        time_delta = float(self.active_markets.get(slug, {}).get("close_time", time.time() + 300)) - (time.time() + self.clob_clock_offset)
        
        if target_price <= 0.0 or budget_usdc <= 0.0:
            return
            
        shares = budget_usdc / target_price
        price = target_price
        strategy_name = strategy
        priority_gas_gwei = self.priority_gas_gwei
        
        gas_cost_usdc = 150000 * (priority_gas_gwei * 1e-9) * self.matic_price
        expected_net_profit = (shares * (1.00 - price)) - gas_cost_usdc
        
        if expected_net_profit <= self.min_profit_threshold_usdc:
            self.add_system_log(f"[Blocked] Maker limit order on {slug} blocked: Expected net profit ({expected_net_profit:.4f}) <= threshold ({self.min_profit_threshold_usdc}).")
            
            tx_hash = f"0x{random.randbytes(16).hex()}"
            self.db.insert_trade(
                tx_hash,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                slug,
                strategy_name,
                outcome,
                price,
                shares,
                priority_gas_gwei,
                "BLOCKED_BY_GUARDRAIL",
                execution_mode="MAKER_LIMIT",
                strike_price=strike,
                trigger_spot_price=spot,
                time_delta_seconds=time_delta,
                block_reason="GAS_UNPROFITABLE",
                parent_order_id=parent_order_id
            )
            return

        tx_hash = f"0x{random.randbytes(16).hex()}"
        self.resting_limit_orders.append({
            "slug": slug,
            "outcome": outcome,
            "price": price,
            "size": shares,
            "strategy": strategy_name,
            "tx_hash": tx_hash,
            "strike_price": strike,
            "trigger_spot_price": spot,
            "time_delta_seconds": time_delta,
            "parent_order_id": parent_order_id
        })
        
        trade = self.add_activity(
            slug, 
            outcome, 
            price, 
            shares, 
            "LIMIT_POSTED", 
            tx_hash,
            reason=f"Maker Limit Order fragment posted to orderbook (Size: {shares:.1f} shares @ ${price:.3f})"
        )
        trade["strategy"] = strategy_name
        trade["parent_order_id"] = parent_order_id
        
        self.db.insert_trade(
            tx_hash,
            trade["datetime_utc"],
            slug,
            strategy_name,
            outcome,
            price,
            shares,
            priority_gas_gwei,
            "LIMIT_POSTED",
            execution_mode="MAKER_LIMIT",
            strike_price=strike,
            trigger_spot_price=spot,
            time_delta_seconds=time_delta,
            parent_order_id=parent_order_id
        )
        self.add_system_log(f"[LIMIT_POSTED] Posted async maker limit order on {slug}: {shares:.1f} shares of {outcome} @ ${price:.3f}")

    def post_maker_limit_order(self, market, outcome, price, strategy_name, budget_allocation=1.0, parent_order_id=None):
        """Simulates placing a resting maker limit order on the CLOB."""
        slug = market["slug"]
        
        shares = (self.max_position_size_usdc * budget_allocation) / price
        priority_gas_gwei = self.priority_gas_gwei
        spot = self.live_prices.get(market["symbol"], 0.0)
        strike = market.get("strike_price", 0.0)
        
        # Strict validation pre-flight guard
        if strike <= 0.0 or spot <= 0.0:
            self.add_system_log(f"[WARNING] Aborting trade on {slug}: Strike or Spot price read failed (defaulted to 0.0)")
            return
            
        time_delta = float(market["close_time"]) - (time.time() + self.clob_clock_offset)

        # Check gas-adjusted expected net profit to clear block inclusion
        gas_cost_usdc = 150000 * (priority_gas_gwei * 1e-9) * self.matic_price
        expected_net_profit = (shares * (1.00 - price)) - gas_cost_usdc
        
        if expected_net_profit <= self.min_profit_threshold_usdc:
            self.add_system_log(f"[Blocked] Maker limit order on {slug} blocked: Expected net profit ({expected_net_profit:.4f}) <= threshold ({self.min_profit_threshold_usdc}).")
            
            # Record blocked trade in database
            tx_hash = f"0x{random.randbytes(32).hex()}"
            self.db.insert_trade(
                tx_hash,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                slug,
                strategy_name,
                outcome,
                price,
                shares,
                priority_gas_gwei,
                "BLOCKED_BY_GUARDRAIL",
                execution_mode="MAKER_LIMIT",
                strike_price=strike,
                trigger_spot_price=spot,
                time_delta_seconds=time_delta,
                block_reason="GAS_UNPROFITABLE",
                parent_order_id=parent_order_id
            )
            return

        # Post resting limit order
        tx_hash = f"0x{random.randbytes(32).hex()}"
        self.resting_limit_orders.append({
            "slug": slug,
            "outcome": outcome,
            "price": price,
            "size": shares,
            "strategy": strategy_name,
            "tx_hash": tx_hash,
            "strike_price": strike,
            "trigger_spot_price": spot,
            "time_delta_seconds": time_delta,
            "parent_order_id": parent_order_id
        })
        
        # Record trade as LIMIT_POSTED
        trade = self.add_activity(slug, outcome, price, shares, "LIMIT_POSTED", tx_hash)
        trade["strategy"] = strategy_name
        
        # Insert trade into database with LIMIT_POSTED status
        self.db.insert_trade(
            trade["tx_hash"], 
            trade["datetime_utc"], 
            slug, 
            strategy_name, 
            outcome, 
            price, 
            shares, 
            priority_gas_gwei, 
            "LIMIT_POSTED",
            execution_mode="MAKER_LIMIT",
            strike_price=strike,
            trigger_spot_price=spot,
            time_delta_seconds=time_delta,
            parent_order_id=parent_order_id
        )
        
        self.add_system_log(f"[MAKER LIMIT POSTED] Maker limit order placed on {slug} for {outcome} @ ${price:.3f} (size: {shares:.2f} shares)")

    async def latency_jitter_simulation(self):
        """Simulates network jitter of WebSocket connectivity and gas fluctuations."""
        while True:
            self.latency_ms = max(0.5, min(25.0, self.latency_ms + random.uniform(-0.4, 0.5)))
            self.priority_gas_gwei = max(35, min(180, self.priority_gas_gwei + random.randint(-8, 10)))
            await asyncio.sleep(2)

    async def sync_clob_clock(self):
        """Periodically syncs system time against Polymarket CLOB Server Time."""
        import urllib.request
        import json
        from datetime import datetime, timezone
        
        url = "https://clob.polymarket.com/time"
        self.add_system_log("CLOB Server Time sync task started.")
        
        while True:
            try:
                def _fetch():
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as response:
                        return response.read().decode('utf-8')
                        
                res = await asyncio.to_thread(_fetch)
                if res:
                    try:
                        try:
                            data = json.loads(res)
                            if isinstance(data, dict):
                                time_val = data.get("time") or data.get("timestamp") or res
                            else:
                                time_val = data
                        except (ValueError, TypeError):
                            time_val = res.strip().replace('"', '')
                            
                        if isinstance(time_val, str) and ("T" in time_val or "-" in time_val):
                            iso_str = time_val.replace("Z", "+00:00").replace('"', '').strip()
                            dt = datetime.fromisoformat(iso_str)
                            server_time = dt.timestamp()
                        else:
                            server_time = float(time_val)
                            
                        local_time = time.time()
                        self.clob_clock_offset = server_time - local_time
                        # Optional debugging log
                        # self.add_system_log(f"Synced CLOB clock. Offset: {self.clob_clock_offset:.3f}s")
                    except Exception as parse_err:
                        self.add_system_log(f"Error parsing CLOB time response: {res} -> {parse_err}")
            except Exception as e:
                pass
            await asyncio.sleep(10)

    async def automated_csv_export_loop(self):
        """Generates a CSV snapshot of all trade records every 24 hours at 00:00:00 UTC."""
        self.add_system_log("Automated CSV Export Service started.")
        while True:
            try:
                now = datetime.now(timezone.utc)
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                sleep_secs = (tomorrow - now).total_seconds()
                if sleep_secs < 1:
                    sleep_secs = 86400
                self.add_system_log(f"Next scheduled CSV export in {sleep_secs:.1f} seconds (at 00:00:00 UTC).")
                await asyncio.sleep(sleep_secs)
                
                date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
                filename = f"poly_bot_live_dump_{date_str}.csv"
                await asyncio.to_thread(self.export_trades_to_csv, filename)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.add_system_log(f"Error in CSV export loop: {e}")
                await asyncio.sleep(60)

    def export_trades_to_csv(self, filename):
        """Fetches all trades from the database and exports them to a CSV file."""
        import csv
        self.add_system_log(f"Starting database snapshot export to {filename}...")
        try:
            query = """
            SELECT id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                   execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason, rejection_reason, spot_strike_delta
            FROM trades
            ORDER BY timestamp_utc ASC;
            """
            cursor = self.db.execute(query)
            if not cursor:
                self.add_system_log("Export failed: could not query database.")
                return
            
            rows = cursor.fetchall()
            
            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "timestamp",
                    "datetime_utc",
                    "market_slug",
                    "strategy_type",
                    "execution_mode",
                    "side_outcome",
                    "strike_price",
                    "trigger_spot_price",
                    "time_delta_seconds",
                    "entry_price",
                    "shares_count",
                    "usdc_size",
                    "priority_gas_gwei",
                    "pnl_status",
                    "block_reason",
                    "rejection_reason",
                    "spot_strike_delta",
                    "transaction_hash"
                ])
                
                for r in rows:
                    tx_hash = r[0]
                    dt_utc = r[1]
                    slug = r[2]
                    strategy = r[3]
                    outcome = r[4]
                    price = float(r[5]) if r[5] is not None else 0.0
                    size = float(r[6]) if r[6] is not None else 0.0
                    gas = float(r[7]) if r[7] is not None else 0.0
                    status = r[8]
                    mode = r[10] or "MAKER_LIMIT"
                    strike = float(r[11]) if r[11] is not None else 0.0
                    spot = float(r[12]) if r[12] is not None else 0.0
                    time_delta = float(r[13]) if r[13] is not None else 0.0
                    block_reason = r[14] or ""
                    rejection = r[15] or ""
                    delta_spot_strike = float(r[16]) if r[16] is not None else 0.0
                    
                    if isinstance(dt_utc, datetime):
                        ts_ms = int(dt_utc.timestamp() * 1000)
                        iso_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                    else:
                        try:
                            clean_dt_str = str(dt_utc).replace("Z", "+00:00").strip()
                            dt = datetime.fromisoformat(clean_dt_str)
                            ts_ms = int(dt.timestamp() * 1000)
                            iso_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                        except Exception:
                            ts_ms = int(time.time() * 1000)
                            iso_str = str(dt_utc)
                            
                    strat_upper = str(strategy).upper()
                    if "PENNY" in strat_upper or "B" in strat_upper:
                        strat_mapped = "STRATEGY_B_PENNY"
                    else:
                        strat_mapped = "STRATEGY_A_ARB"
                        
                    out_upper = str(outcome).upper()
                    if "UP" in out_upper or "YES" in out_upper:
                        side_mapped = "BUY_UP"
                    else:
                        side_mapped = "BUY_DOWN"
                        
                    writer.writerow([
                        ts_ms,
                        iso_str,
                        slug,
                        strat_mapped,
                        mode,
                        side_mapped,
                        strike,
                        spot,
                        time_delta,
                        price,
                        size,
                        round(price * size, 4),
                        gas,
                        status,
                        block_reason,
                        rejection,
                        delta_spot_strike,
                        tx_hash
                    ])
                    
            self.add_system_log(f"Export completed: {len(rows)} records flushed to {filename}.")
        except Exception as e:
            self.add_system_log(f"Database CSV export error: {e}")

    def run_backtest_simulation(self, params):
        """Runs the isolated backtester on a separate thread."""
        try:
            start_date = params.get("startDate")
            end_date = params.get("endDate")
            proximity_limit = float(params.get("proximityLimit", 0.15))
            obi_cutoff = float(params.get("obiCutoff", 0.65))
            base_size = float(params.get("baseSize", 10.0))
            start_balance = float(params.get("startBalance", 1000.0))
            
            backtester = Backtester(
                start_date=start_date,
                end_date=end_date,
                proximity_limit=proximity_limit,
                obi_cutoff=obi_cutoff,
                base_size=base_size,
                start_balance=start_balance,
                vol_multiplier=4.8
            )
            return backtester.run()
        except Exception as e:
            return {"error": f"Backtest execution failed: {e}"}

    async def http_handler(self, arg1, arg2):
        """Serves production built static React files from dist/ directory.
        Handles both old websockets (path, headers) and new websockets (connection, request) signatures.
        """
        headers = None
        path = "/"
        
        if hasattr(arg2, "headers") and hasattr(arg2, "path"):
            path = arg2.path
            headers = arg2.headers
        elif isinstance(arg1, str):
            path = arg1
            headers = arg2
        elif hasattr(arg1, "headers"):
            headers = arg1.headers
            if hasattr(arg1, "path"):
                path = arg1.path
                
        is_websocket = False
        if headers is not None:
            try:
                up = str(headers.get("Upgrade", "") or headers.get("upgrade", "")).lower()
                conn = str(headers.get("Connection", "") or headers.get("connection", "")).lower()
                if "websocket" in up or "upgrade" in conn:
                    is_websocket = True
            except Exception:
                try:
                    for k, v in headers:
                        k_str = str(k).lower()
                        v_str = str(v).lower()
                        if (k_str == "upgrade" and "websocket" in v_str) or (k_str == "connection" and "upgrade" in v_str):
                            is_websocket = True
                            break
                except Exception:
                    pass
                    
        if is_websocket:
            return None # Proceed to websocket handler

        if path == "/api/export-logs" or path.startswith("/api/export-logs"):
            csv_content, filename = self.generate_csv_string()
            headers = [
                ("Content-Type", "text/csv"),
                ("Content-Disposition", f"attachment; filename={filename}"),
                ("Access-Control-Allow-Origin", "*")
            ]
            return http.HTTPStatus.OK, headers, csv_content.encode("utf-8")
            
        # Default to index.html for SPA router requests
        if path == "/" or not "." in path.split("/")[-1]:
            path = "/index.html"
            
        clean_path = path.lstrip("/")
        file_path = os.path.join("dist", clean_path)
        
        if not os.path.exists(file_path):
            file_path = "dist/index.html"
            
        if not os.path.exists(file_path):
            return http.HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")], b"404 Not Found"
            
        content_type = "text/html"
        if file_path.endswith(".js"):
            content_type = "application/javascript"
        elif file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".svg"):
            content_type = "image/svg+xml"
        elif file_path.endswith(".png"):
            content_type = "image/png"
        elif file_path.endswith(".ico"):
            content_type = "image/x-icon"
            
        try:
            with open(file_path, "rb") as f:
                body = f.read()
            return http.HTTPStatus.OK, [("Content-Type", content_type)], body
        except Exception as e:
            return http.HTTPStatus.INTERNAL_SERVER_ERROR, [("Content-Type", "text/plain")], f"Error: {e}".encode()

    def generate_csv_string(self, limit=None):
        """Queries database and generates the CSV content as a string, sanitizing NULL/NaN values."""
        import io
        import csv
        import math
        from datetime import datetime, timezone
        
        date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        
        limit_clean = None
        if limit is not None and str(limit).lower() != "all":
            try:
                limit_clean = int(limit)
            except Exception:
                limit_clean = None
                
        if limit_clean:
            filename = f"poly_bot_live_dump_last_{limit_clean}_{date_str}.csv"
            query = f"""
            SELECT id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                   execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason, rejection_reason, spot_strike_delta, parent_order_id
            FROM (
                SELECT id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                       execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason, rejection_reason, spot_strike_delta, parent_order_id
                FROM trades
                ORDER BY timestamp_utc DESC
                LIMIT {limit_clean}
            ) sub
            ORDER BY timestamp_utc ASC;
            """
        else:
            filename = f"poly_bot_live_dump_all_{date_str}.csv"
            query = """
            SELECT id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                   execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason, rejection_reason, spot_strike_delta, parent_order_id
            FROM trades
            ORDER BY timestamp_utc ASC;
            """
            
        def sanitize(val):
            if val is None:
                return ""
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return ""
            val_str = str(val)
            if val_str.lower() in ["none", "null", "nan"]:
                return ""
            return val_str
        
        try:
            cursor = self.db.execute(query)
            if not cursor:
                return "Error querying database", filename
            
            rows = cursor.fetchall()
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "timestamp", "datetime_utc", "market_slug", "strategy_type", "execution_mode",
                "side_outcome", "strike_price", "trigger_spot_price", "time_delta_seconds",
                "entry_price", "shares_count", "usdc_size", "priority_gas_gwei", "pnl_status",
                "block_reason", "rejection_reason", "spot_strike_delta", "transaction_hash", "parent_order_id"
            ])
            
            for r in rows:
                tx_hash = r[0]
                dt_utc = r[1]
                slug = r[2]
                strategy = r[3]
                outcome = r[4]
                price = float(r[5]) if r[5] is not None else 0.0
                size = float(r[6]) if r[6] is not None else 0.0
                gas = float(r[7]) if r[7] is not None else 0.0
                status = r[8]
                mode = r[10] or "MAKER_LIMIT"
                strike = float(r[11]) if r[11] is not None else 0.0
                spot = float(r[12]) if r[12] is not None else 0.0
                time_delta = float(r[13]) if r[13] is not None else 0.0
                block_reason = r[14] or ""
                rejection = r[15] or ""
                delta_spot_strike = float(r[16]) if r[16] is not None else 0.0
                parent_order_id = r[17] or ""
                
                if isinstance(dt_utc, datetime):
                    ts_ms = int(dt_utc.timestamp() * 1000)
                    iso_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                else:
                    try:
                        clean_dt_str = str(dt_utc).replace("Z", "+00:00").strip()
                        dt = datetime.fromisoformat(clean_dt_str)
                        ts_ms = int(dt.timestamp() * 1000)
                        iso_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                    except Exception:
                        ts_ms = int(time.time() * 1000)
                        iso_str = str(dt_utc)
                        
                strat_upper = str(strategy).upper()
                if "PENNY" in strat_upper or "B" in strat_upper:
                    strat_mapped = "STRATEGY_B_PENNY"
                else:
                    strat_mapped = "STRATEGY_A_ARB"
                    
                out_upper = str(outcome).upper()
                if "UP" in out_upper or "YES" in out_upper:
                    side_mapped = "BUY_UP"
                else:
                    side_mapped = "BUY_DOWN"
                    
                usdc_val = round(price * size, 4) if price and size else ""
                
                writer.writerow([
                    sanitize(ts_ms),
                    sanitize(iso_str),
                    sanitize(slug),
                    sanitize(strat_mapped),
                    sanitize(mode),
                    sanitize(side_mapped),
                    sanitize(strike),
                    sanitize(spot),
                    sanitize(time_delta),
                    sanitize(price),
                    sanitize(size),
                    sanitize(usdc_val),
                    sanitize(gas),
                    sanitize(status),
                    sanitize(block_reason),
                    sanitize(rejection),
                    sanitize(delta_spot_strike),
                    sanitize(tx_hash),
                    sanitize(parent_order_id)
                ])
                
            csv_data = output.getvalue()
            output.close()
            import gc
            gc.collect()
            return csv_data, filename
        except Exception as e:
            import gc
            gc.collect()
            return f"Error exporting CSV: {e}", filename

async def main():
    engine = TradingEngine()
    
    # Initialize rolling 30-minute prices on startup
    await engine.initialize_rolling_prices()
    
    # Start background tasks supervised by Exception Watchdog
    engine.supervise_task("Pyth Hermes Price Feed", engine.pyth_price_ws)
    engine.supervise_task("Polymarket Gamma API Sync", engine.sync_polymarket_gamma_api)
    engine.supervise_task("Market Management Loop", engine.market_management_loop)
    engine.supervise_task("Rolling Prices Update", engine.rolling_prices_update_loop)
    engine.supervise_task("CLOB Clock Sync", engine.sync_clob_clock)
    
    # Run an initial export on startup to verify setup
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    filename = f"poly_bot_live_dump_{date_str}.csv"
    asyncio.create_task(asyncio.to_thread(engine.export_trades_to_csv, filename))
    
    # Start Local WebSocket Server
    port = int(os.environ.get("PORT", 8000))
    engine.add_system_log(f"Starting Local WebSocket Server on ws://localhost:{port}")
    async with websockets.serve(engine.handle_ws, "0.0.0.0", port, process_request=engine.http_handler):
        await asyncio.Event().wait()  # keep running

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPOLY-BOT Server Terminated.")
