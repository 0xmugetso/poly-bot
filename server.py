import asyncio
import json
import random
import time
import ssl
import sys
import os
import urllib.request
from datetime import datetime, timezone, timedelta
import websockets

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
            block_reason VARCHAR(128)
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
                
            # Migrations for SQLite if tables already exist
            if not self.is_postgres:
                for col, col_type in [("execution_mode", "VARCHAR(32) DEFAULT 'MAKER_LIMIT'"),
                                      ("strike_price", "DECIMAL(12, 4)"),
                                      ("trigger_spot_price", "DECIMAL(12, 4)"),
                                      ("time_delta_seconds", "DECIMAL(10, 4)"),
                                      ("block_reason", "VARCHAR(128)")]:
                    try:
                        cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type};")
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
                     time_delta_seconds=None, block_reason=None):
        query = """
        INSERT INTO trades (id, timestamp_utc, market_slug, strategy, outcome_bet, entry_price, position_size, gas_fee_gwei, pnl_status, resolved_at,
                            execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
        """
        if self.is_postgres:
            query = query.replace("?", "%s")
        self.execute(query, (id_, timestamp, slug, strategy, outcome, price, size, gas, status,
                             execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason))
        
    def resolve_trade(self, id_, status, resolved_at):
        query = """
        UPDATE trades SET pnl_status = ?, resolved_at = ? WHERE id = ?
        """
        if self.is_postgres:
            query = query.replace("?", "%s")
            self.execute(query, (status, resolved_at, id_))
        else:
            self.execute(query, (status, resolved_at, id_))

    def load_recent_trades(self, limit=50):
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
                    "entry_price": float(r[5]),
                    "position_size": float(r[6]),
                    "gas_fee_gwei": float(r[7]),
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
                    "entry_price": float(r["entry_price"]),
                    "position_size": float(r["position_size"]),
                    "gas_fee_gwei": float(r["gas_fee_gwei"]),
                    "pnl_status": r["pnl_status"],
                    "resolved_at": r["resolved_at"]
                })
        return trades[::-1]
        
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
        self.max_simultaneous_trades = int(os.environ.get("MAX_SIMULTANEOUS_TRADES", 2))
        self.min_profit_threshold_usdc = float(os.environ.get("MIN_PROFIT_THRESHOLD_USDC", 0.02))
        self.env = os.environ.get("ENV", "SIMULATION")
        
        # Live market tracking
        self.spot_prices = {"BTC": 67250.0, "ETH": 3480.0, "SOL": 142.50, "XRP": 0.58, "BNB": 585.0}
        self.price_decimals = {"BTC": 1, "ETH": 2, "SOL": 2, "XRP": 4, "BNB": 2}
        self.active_markets = {}  # symbol -> market_details
        
        # Activity and logs
        self.activity_log = []
        self.system_logs = []
        
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

    def add_activity(self, slug, outcome, price, size, status, tx_hash=None):
        if not tx_hash:
            tx_hash = f"0x{random.randbytes(32).hex()}"
        
        trade = {
            "datetime_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "slug": slug,
            "outcome": outcome,
            "price": price,
            "size": size,
            "status": status,
            "tx_hash": tx_hash
        }
        self.activity_log.append(trade)
        if len(self.activity_log) > 50:
            self.activity_log.pop(0)
        return trade

    def add_system_log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {msg}"
        self.system_logs.append(log_line)
        if len(self.system_logs) > 100:
            self.system_logs.pop(0)
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
            "active_markets": list(self.active_markets.values()),
            "activity_log": self.activity_log,
            "system_logs": self.system_logs[-20:],
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "rpc_node_health": self.rpc_node_health,
            "market_locks": self.market_locks,
            "resting_limit_orders": self.resting_limit_orders,
            "priority_gas_gwei": self.priority_gas_gwei,
            "matic_price": self.matic_price
        }

    async def broadcast(self):
        if not self.clients:
            return
        state_str = json.dumps(self.get_state())
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
        except Exception as e:
            pass
        finally:
            self.clients.remove(websocket)
            self.add_system_log("Frontend client disconnected.")

    async def binance_price_feed(self):
        """Streams prices from Binance Spot WebSocket with auto-reconnection and heartbeats.
        Exhibits self-healing properties: falls back to Binance.US if the host is geoblocked (HTTP 451).
        """
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
        global_url = "wss://stream.binance.com:9443/ws"
        us_url = "wss://stream.binance.us:9443/ws"
        
        use_us_feed = False
        
        while True:
            url = us_url if use_us_feed else global_url
            try:
                self.add_system_log(f"Connecting to {'Binance.US' if use_us_feed else 'Binance Global'} Spot WebSocket...")
                ssl_context = ssl._create_unverified_context()
                async with websockets.connect(url, ssl=ssl_context) as ws:
                    # Subscribe to tickers
                    sub_msg = {
                        "method": "SUBSCRIBE",
                        "params": [f"{s.lower()}@ticker" for s in symbols],
                        "id": 1
                    }
                    await ws.send(json.dumps(sub_msg))
                    self.add_system_log(f"Subscribed to {'Binance.US' if use_us_feed else 'Binance Global'} price feeds.")
                    
                    while True:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        except asyncio.TimeoutError:
                            self.add_system_log("Binance WebSocket read timeout (10s). Triggering reconnect...")
                            break
                            
                        data = json.loads(message)
                        if "s" in data and "c" in data:
                            ticker = data["s"]
                            price = float(data["c"])
                            symbol = ticker.replace("USDT", "")
                            self.spot_prices[symbol] = price
            except Exception as e:
                err_str = str(e)
                self.add_system_log(f"Binance WebSocket error: {err_str}")
                if "451" in err_str and not use_us_feed:
                    self.add_system_log("HTTP 451 detected (Geo-blocked). Switching to Binance.US feed...")
                    use_us_feed = True
                else:
                    self.add_system_log("Reconnecting in 1s...")
                    await asyncio.sleep(1)

    def fetch_market_details(self, slug):
        """Queries the Polymarket Gamma API to get details of a slug."""
        try:
            url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req).read()
            data = json.loads(res)
            if len(data) > 0:
                return data[0]
        except Exception as e:
            pass
        return None

    async def market_management_loop(self):
        """Periodically syncs active 5M/15M markets and resolves rounds."""
        symbols = ["BTC", "ETH", "SOL", "XRP", "BNB"]
        
        while True:
            if self.status != "RUNNING":
                await asyncio.sleep(1)
                continue
                
            t_synced = time.time() + self.clob_clock_offset
            t = int(t_synced)
            t_rounded_5m = t - (t % 300)
            t_rounded_15m = t - (t % 900)
            
            # 1. Update active 5m markets
            for symbol in symbols:
                # We expect a market to exist for the current 5m interval
                # Active round starts at t_rounded_5m, closes at t_rounded_5m + 300
                slug_5m = f"{symbol.lower()}-updown-5m-{t_rounded_5m}"
                close_time = t_rounded_5m + 300
                time_remaining = close_time - t
                
                # Fetch details if not already loaded
                if slug_5m not in self.active_markets:
                    self.add_system_log(f"Syncing active contract details for: {slug_5m}")
                    details = await asyncio.to_thread(self.fetch_market_details, slug_5m)
                    
                    if details:
                        # Record the strike price (the spot price at the start of the round)
                        # We fall back to current spot price if not available
                        strike = self.spot_prices[symbol]
                        self.active_markets[slug_5m] = {
                            "symbol": symbol,
                            "slug": slug_5m,
                            "type": "5M",
                            "start_time": t_rounded_5m,
                            "close_time": close_time,
                            "strike_price": strike,
                            "id": details.get("id"),
                            "clobTokenIds": json.loads(details.get("clobTokenIds", "[]")),
                            "conditionId": details.get("conditionId"),
                            "last_evaluated": 0,
                            "resolved": False
                        }
                        self.add_system_log(f"Market Active: {slug_5m} | Strike Price Set: ${strike:,.2f}")
                    else:
                        # Fallback mock details if the live round isn't created on Gamma API yet
                        # (Helps keep the engine alive offline or during API delay)
                        strike = self.spot_prices[symbol]
                        self.active_markets[slug_5m] = {
                            "symbol": symbol,
                            "slug": slug_5m,
                            "type": "5M",
                            "start_time": t_rounded_5m,
                            "close_time": close_time,
                            "strike_price": strike,
                            "id": f"mock-{t_rounded_5m}",
                            "clobTokenIds": [f"yes-{t_rounded_5m}", f"no-{t_rounded_5m}"],
                            "conditionId": f"cond-{t_rounded_5m}",
                            "last_evaluated": 0,
                            "resolved": False
                        }

            # 2. Evaluate execution triggers (-5s to +2s window)
            for slug, market in list(self.active_markets.items()):
                if market["resolved"]:
                    continue
                    
                time_remaining = market["close_time"] - t
                symbol = market["symbol"]
                spot = self.spot_prices[symbol]
                strike = market["strike_price"]
                
                # Strict boundary fence check: Time Delta <= 0.5 seconds
                time_delta = float(market["close_time"]) - t_synced
                fence_active = (time_delta <= 0.5)
                
                if fence_active:
                    # Instantly kill state machine for this slug
                    if slug in self.market_locks:
                        self.market_locks.pop(slug)
                    
                    # Cancel any resting limits
                    original_len = len(self.resting_limit_orders)
                    self.resting_limit_orders = [o for o in self.resting_limit_orders if o["slug"] != slug]
                    if len(self.resting_limit_orders) < original_len:
                        self.add_system_log(f"[FENCE ACTIVE] Synced time delta = {time_delta:.3f}s <= 0.5s. Cancelled resting orders for {slug}.")
                    
                    # Update database LIMIT_POSTED to CANCELLED
                    for trade in self.activity_log:
                        if trade["slug"] == slug and trade["status"] == "LIMIT_POSTED":
                            trade["status"] = "CANCELLED"
                            self.db.resolve_trade(trade["tx_hash"], "CANCELLED", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
                
                # Strike proximity check at t = 5s before close
                if time_remaining <= 5 and "proximity_enabled" not in market:
                    proximity = abs(spot - strike) / strike
                    is_valid = (proximity <= 0.0002)
                    market["proximity_enabled"] = is_valid
                    self.add_system_log(f"[{'ENABLED' if is_valid else 'BLOCKED'}] Proximity check for {slug}: Proximity = {proximity:.6f} (Limit: 0.0002)")
                
                # Dynamic contract pricing estimation based on spot vs strike
                # Difference between spot and strike
                delta = spot - strike
                
                # Estimate contract prices: YES is Up, NO is Down
                # If delta is positive and large, YES is high (0.95-0.99), NO is low (0.01-0.05)
                # If delta is negative and large, NO is high (0.95-0.99), YES is low (0.01-0.05)
                # Around delta = 0, they hover around 0.50.
                volatility_factor = 2.0 if symbol in ["BTC", "BNB"] else 0.1
                val = -delta / volatility_factor
                val = max(-50.0, min(50.0, val))
                price_yes = 1 / (1 + 2.718 ** val)
                price_yes = max(0.01, min(0.99, price_yes))
                price_no = 1 - price_yes
                
                # Add price fields to active market info for UI display
                market["time_remaining"] = time_remaining
                market["price_yes"] = round(price_yes, 2)
                market["price_no"] = round(price_no, 2)
                
                # Simulate order book bid/ask depth
                market["order_book"] = {
                    "YES": {
                        "bids": [[round(price_yes - 0.01 * j, 2), random.randint(100, 1000)] for j in range(1, 4)],
                        "asks": [[round(price_yes + 0.01 * j, 2), random.randint(100, 1000)] for j in range(1, 4)]
                    },
                    "NO": {
                        "bids": [[round(price_no - 0.01 * j, 2), random.randint(100, 1000)] for j in range(1, 4)],
                        "asks": [[round(price_no + 0.01 * j, 2), random.randint(100, 1000)] for j in range(1, 4)]
                    }
                }

                if not fence_active:
                    # Evaluate active resting limit orders for this slug
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
                                    
                                    # Re-hydrate or update the LIMIT_POSTED activity log item to PENDING
                                    matched_trade = None
                                    for trade in self.activity_log:
                                        if trade["tx_hash"] == order["tx_hash"]:
                                            matched_trade = trade
                                            break
                                    
                                    if matched_trade:
                                        matched_trade["status"] = "PENDING"
                                        self.db.resolve_trade(order["tx_hash"], "PENDING", None)
                                    else:
                                        trade = self.add_activity(slug, order["outcome"], order["price"], order["size"], "PENDING", order["tx_hash"])
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
                                            "PENDING",
                                            execution_mode="MAKER_LIMIT",
                                            strike_price=order.get("strike_price"),
                                            trigger_spot_price=order.get("trigger_spot_price"),
                                            time_delta_seconds=order.get("time_delta_seconds")
                                        )
                                    
                                    self.add_system_log(f"[MAKER LIMIT FILLED] Limit order for {order['outcome']} filled on {slug} @ ${order['price']:.3f}")
                                self.resting_limit_orders.remove(order)

                    # Evaluate execution triggers
                    # Window: final -5 seconds to +2 seconds epoch boundaries
                    if -5 <= time_remaining <= 2 and market["last_evaluated"] != t:
                        market["last_evaluated"] = t
                        
                        # Strategy A is hard deprecated.
                        # We evaluate YES/NO only for Strategy B (Penny Sweeps) targeting $0.01 to $0.04
                        
                        # Check YES (Up)
                        if 0.01 <= price_yes <= 0.04:
                            if market.get("proximity_enabled", True):
                                self.post_maker_limit_order(market, "Up", price_yes, "Strategy B (Penny Sweep)")
                            
                        # Check NO (Down)
                        if 0.01 <= price_no <= 0.04:
                            if market.get("proximity_enabled", True):
                                self.post_maker_limit_order(market, "Down", price_no, "Strategy B (Penny Sweep)")

                # 3. Post-Close Settlement Resolution (+2s grace period exploit)
                # Polymarket oracle settlement delay allows scanning/executing for up to 2s post-close
                if time_remaining < -2:
                    # Final spot tick resolution
                    winner = "Up" if spot >= strike else "Down"
                    
                    # Resolve active simulated positions
                    resolved_any = False
                    for trade in self.activity_log:
                        if trade["slug"] == slug and trade["status"] == "PENDING":
                            resolved_any = True
                            is_win = (trade["outcome"] == winner)
                            if is_win:
                                trade["status"] = "WIN"
                                self.wins += 1
                                if "Arbitrage" in trade.get("strategy", ""):
                                    self.arbitrage_wins += 1
                                else:
                                    self.penny_wins += 1
                                payout = trade["size"]
                                self.wallet += payout
                                self.net_pnl_usdc += (payout - (trade["size"] * trade["price"]))
                            else:
                                trade["status"] = "LOSS"
                                self.losses += 1
                                self.net_pnl_usdc -= (trade["size"] * trade["price"])
                            
                            self.resolved_trades_count += 1
                            self.net_pnl_pct = (self.net_pnl_usdc / self.initial_wallet) * 100
                            self.add_system_log(f"Round Settled: {slug} | Winner: {winner} | Trade: {trade['status']}")
                            
                            # Update database
                            resolved_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                            self.db.resolve_trade(trade["tx_hash"], trade["status"], resolved_time)
                    
                    if resolved_any:
                        self.add_system_log(f"Cleaned up resolved contract state for: {slug}")
                        # Save daily stats
                        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        win_rate = (self.wins / (self.wins + self.losses) * 100) if (self.wins + self.losses) > 0 else 0.0
                        self.db.save_daily_stats(today_str, self.wallet, self.wins + self.losses, win_rate, now_str)
                    
                    # Clean up locks and limit orders
                    if slug in self.market_locks:
                        self.market_locks.pop(slug)
                    self.resting_limit_orders = [o for o in self.resting_limit_orders if o["slug"] != slug]
                    
                    # Also update any remaining LIMIT_POSTED trades to CANCELLED in database and activity log
                    for trade in self.activity_log:
                        if trade["slug"] == slug and trade["status"] == "LIMIT_POSTED":
                            trade["status"] = "CANCELLED"
                            self.db.resolve_trade(trade["tx_hash"], "CANCELLED", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
                    
                    # Remove from active listing
                    market["resolved"] = True
                    self.active_markets.pop(slug)
            
            # Broadcast state to frontend
            await self.broadcast()
            await asyncio.sleep(0.1)

    def post_maker_limit_order(self, market, outcome, price, strategy_name):
        """Simulates placing a resting maker limit order on the CLOB."""
        slug = market["slug"]
        
        # Check MAX_SIMULTANEOUS_TRADES guardrail
        active_pools = set(t["slug"] for t in self.activity_log if t["status"] in ["PENDING", "LIMIT_POSTED"])
        for order in self.resting_limit_orders:
            active_pools.add(order["slug"])
            
        shares = self.max_position_size_usdc / price
        priority_gas_gwei = self.priority_gas_gwei
        spot = self.spot_prices[market["symbol"]]
        strike = market["strike_price"]
        time_delta = float(market["close_time"]) - (time.time() + self.clob_clock_offset)

        if len(active_pools) >= self.max_simultaneous_trades and slug not in active_pools:
            self.add_system_log(f"[Blocked] Maker limit order on {slug} blocked: Max simultaneous trades ({self.max_simultaneous_trades}) reached.")
            
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
                block_reason="MAX_SIMULTANEOUS_TRADES"
            )
            return

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
                block_reason="GAS_UNPROFITABLE"
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
            "time_delta_seconds": time_delta
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
            time_delta_seconds=time_delta
        )
        
        self.add_system_log(f"[MAKER LIMIT POSTED] t-{abs(market['time_remaining'])}s: Maker limit order placed on {slug} for {outcome} @ ${price:.3f}")

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
                   execution_mode, strike_price, trigger_spot_price, time_delta_seconds, block_reason
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
                        tx_hash
                    ])
                    
            self.add_system_log(f"Export completed: {len(rows)} records flushed to {filename}.")
        except Exception as e:
            self.add_system_log(f"Database CSV export error: {e}")

async def main():
    engine = TradingEngine()
    
    # Start background threads/tasks
    asyncio.create_task(engine.binance_price_feed())
    asyncio.create_task(engine.sync_clob_clock())
    asyncio.create_task(engine.market_management_loop())
    asyncio.create_task(engine.latency_jitter_simulation())
    asyncio.create_task(engine.automated_csv_export_loop())
    
    # Run an initial export on startup to verify setup
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    filename = f"poly_bot_live_dump_{date_str}.csv"
    asyncio.create_task(asyncio.to_thread(engine.export_trades_to_csv, filename))
    
    # Start Local WebSocket Server
    port = int(os.environ.get("PORT", 8000))
    engine.add_system_log(f"Starting Local WebSocket Server on ws://localhost:{port}")
    async with websockets.serve(engine.handle_ws, "0.0.0.0", port):
        await asyncio.Event().wait()  # keep running

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPOLY-BOT Server Terminated.")
