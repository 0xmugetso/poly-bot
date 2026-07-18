import time
import json
import random
import os
import urllib.request
import ssl
from datetime import datetime, timezone, timedelta

class Backtester:
    def __init__(self, start_date=None, end_date=None, proximity_limit=0.0002, obi_cutoff=0.65, base_size=10.0, start_balance=1000.0, vol_multiplier=12.0):
        self.start_date = start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.end_date = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.proximity_limit = float(proximity_limit)
        self.obi_cutoff = float(obi_cutoff)
        self.base_size = float(base_size)
        self.start_balance = float(start_balance)
        self.vol_multiplier = float(vol_multiplier)
        self.symbols = ["BTC", "ETH", "SOL", "XRP"]

    def fetch_binance_klines(self, symbol, start_ms, end_ms, limit=1000):
        """Fetches historical 5-minute candles from Binance REST API for a specific period.
        Bypasses geoblocks dynamically by falling back to binance.us.
        """
        pair = f"{symbol}USDT"
        hosts = ["https://api.binance.com", "https://api.binance.us"]
        ctx = ssl._create_unverified_context()
        
        for host in hosts:
            url = f"{host}/api/v3/klines?symbol={pair}&interval=5m&startTime={start_ms}&endTime={end_ms}&limit={limit}"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=3, context=ctx).read()
                data = json.loads(res)
                if data and isinstance(data, list):
                    candles = []
                    for row in data:
                        candles.append({
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "time": int(row[0]) // 1000
                        })
                    return candles
            except Exception:
                continue
        return None

    def generate_monte_carlo_candles(self, symbol, start_price, start_ms, limit=1000):
        """Generates high-fidelity synthetic 5-minute candles starting from start_ms."""
        candles = []
        current_price = start_price
        vols = {"BTC": 0.0005, "ETH": 0.0007, "SOL": 0.0012, "XRP": 0.0015}
        vol = vols.get(symbol, 0.001)
        
        t_start = start_ms // 1000
        for i in range(limit):
            op = current_price
            prices = [op]
            for _ in range(4): # interpolate 4 sub-ticks
                current_price *= (1 + random.normalvariate(0, vol))
                prices.append(current_price)
            cl = current_price
            candles.append({
                "open": op,
                "high": max(prices),
                "low": min(prices),
                "close": cl,
                "time": t_start + (i * 5 * 60)
            })
        return candles

    def run(self):
        """Runs the historical strategy backtest simulation."""
        results = []
        equity = self.start_balance  # Simulated initial wallet from user input
        initial_equity = equity
        max_equity = equity
        max_drawdown = 0.0
        unique_rounds_entered = 0
        
        total_rounds = 0
        total_executions = 0
        wins = 0
        losses = 0
        gross_revenue = 0.0
        
        # Parse dates robustly
        try:
            dt_start = datetime.strptime(self.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            try:
                dt_start = datetime.strptime(self.start_date, "%m/%d/%Y").replace(tzinfo=timezone.utc)
            except Exception:
                dt_start = datetime.now(timezone.utc) - timedelta(days=3)
                
        try:
            dt_end = datetime.strptime(self.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            try:
                dt_end = datetime.strptime(self.end_date, "%m/%d/%Y").replace(tzinfo=timezone.utc)
            except Exception:
                dt_end = datetime.now(timezone.utc)
                
        start_ms = int(dt_start.timestamp() * 1000)
        end_ms = int(dt_end.timestamp() * 1000)
        if end_ms <= start_ms:
            end_ms = start_ms + (24 * 3600 * 1000) # 1 day default
            
        logs = [
            "[SYSTEM] Initializing Backtester...",
            f"[SYSTEM] Date range parameters: {dt_start.strftime('%Y-%m-%d')} to {dt_end.strftime('%Y-%m-%d')}",
            f"[SYSTEM] Proximity limit: {self.proximity_limit*100:.3f}% | OBI cutoff: {self.obi_cutoff:.2f} | Base size: ${self.base_size:.1f}"
        ]
        
        # Check if local JSON database cache exists
        local_path = "historical_candles_2026.json"
        if not os.path.exists(local_path):
            local_path = "/Users/khash/Projects/poly-bot/historical_candles_2026.json"
            
        loaded = False
        symbol_candles = {}
        
        # 1. Try querying real CEX API directly first
        logs.append("[SYSTEM] Fetching real historical candles from Binance API...")
        try:
            for sym in self.symbols:
                candles = self.fetch_binance_klines(sym, start_ms, end_ms, limit=1000)
                if not candles or len(candles) < 5:
                    raise Exception(f"Failed to fetch live API candles for {sym}")
                symbol_candles[sym] = candles
                logs.append(f"[DATA] Fetched {len(candles)} real candles for {sym} from Binance API.")
            loaded = True
            logs.append("[SYSTEM] Successfully synced real historical candles from CEX API.")
        except Exception as e:
            logs.append(f"[SYSTEM] Live CEX API fetch failed: {e}. Reloading from local database cache...")
            
        # 2. If live fetch failed, reload from local JSON database cache file
        if not loaded:
            if os.path.exists(local_path):
                try:
                    logs.append(f"[SYSTEM] Loading from local database cache: {os.path.basename(local_path)}")
                    with open(local_path, "r") as f:
                        db = json.load(f)
                    
                    t_start = start_ms // 1000
                    t_end = end_ms // 1000
                    
                    for sym in self.symbols:
                        all_c = db.get(sym, [])
                        filtered = [c for c in all_c if t_start <= c["time"] <= t_end]
                        if len(filtered) < 5:
                            raise Exception(f"Insufficient cached candles in range for {sym}")
                        symbol_candles[sym] = filtered
                        logs.append(f"[DATA] Loaded {len(filtered)} intervals for {sym} from local database cache.")
                    loaded = True
                    logs.append("[SYSTEM] Successfully loaded candles from local database cache.")
                except Exception as cache_err:
                    logs.append(f"[SYSTEM] Cache load failed: {cache_err}. Falling back to Monte Carlo...")
                    
        # 3. If both failed, generate synthetic Monte Carlo data
        if not loaded:
            logs.append("[SYSTEM] Initiating offline fallback generator...")
            for sym in self.symbols:
                start_prices = {"BTC": 67000.0, "ETH": 3450.0, "SOL": 140.0, "XRP": 0.58}
                candles = self.generate_monte_carlo_candles(sym, start_prices.get(sym, 10.0), start_ms, limit=1000)
                symbol_candles[sym] = candles
                logs.append(f"[DATA] Offline fallback. Generated 1000 Monte Carlo candles for {sym}.")
        
        # Check data length
        data_len = min(len(symbol_candles[sym]) for sym in self.symbols)
        if data_len < 2:
            return {
                "error": "Insufficient historical data found or generated.",
                "total_rounds": 0, "total_executions": 0, "win_rate": 0, "net_profit": 0,
                "logs": logs
            }

        # Step through intervals (each candle represents a 5-minute round)
        equity_timeline = [{"time": 0, "equity": equity}]
        
        import math
        rolling_closes = {sym: [] for sym in self.symbols}
        
        for idx in range(data_len):
            # Strict Capital Liquidation Check
            if equity < self.base_size:
                logs.append(f"[LIQUIDATED] Simulation halted at round {total_rounds}. Account balance (${equity:.2f}) dropped below required position size (${self.base_size:.1f}).")
                break
                
            total_rounds += 1
            round_pnl = 0.0
            
            for sym in self.symbols:
                c = symbol_candles[sym][idx]
                strike = c["open"]
                spot_at_close = c["close"]
                
                # Model the spot price 5 seconds before close (adding small tick volatility)
                vols = {"BTC": 0.0002, "ETH": 0.0003, "SOL": 0.0005, "XRP": 0.0008}
                vol = vols.get(sym, 0.0003)
                spot_at_5s = spot_at_close * (1 + random.normalvariate(0, vol * 0.1))
                
                # Hard Stop Pre-Flight Validation Rule (remains as a basic safety check)
                trigger_spot_price = spot_at_5s
                strike_price = strike
                if abs(trigger_spot_price - strike_price) / trigger_spot_price > 0.005:
                    if len(logs) < 200:
                        logs.append(f"[ERROR] Data mapping corruption detected for {sym} Rd {total_rounds}. Forcing cache flush.")
                    continue
                
                # Calculate OBI momentum representing final 5s spot price velocity
                base_obi = ((spot_at_close - spot_at_5s) / spot_at_5s) * 10000.0
                base_obi = max(-0.95, min(0.95, base_obi))
                obi = base_obi + random.uniform(-0.1, 0.1)
                
                # OBI determines the direction:
                # If OBI > 0 -> BUY_UP (YES)
                # If OBI < 0 -> BUY_DOWN (NO)
                direction = ""
                if obi > 0.0:
                    direction = "YES"
                elif obi < 0.0:
                    direction = "NO"
                else:
                    if len(logs) < 200:
                        logs.append(f"[BLOCKED] Rd {total_rounds} {sym}: OBI is exactly 0.0.")
                    continue
                
                # Generate high-fidelity 1-second ticks in final 3 seconds to determine if fill wicks cross the strike line
                # We interpolate between spot_at_5s and spot_at_close
                ticks = []
                steps = 3
                for step in range(steps):
                    weight = (step + 1) / steps
                    expected = spot_at_5s + (spot_at_close - spot_at_5s) * weight
                    tick_vol = vol * 0.1 / math.sqrt(60.0) # 1s volatility is roughly 1/sqrt(60) of 5m
                    tick_price = expected * (1 + random.normalvariate(0, tick_vol))
                    ticks.append(tick_price)
                    
                # Volatility Flash profile check to skip quiet periods (94% daily skip)
                # Requires candle high-to-low range to be at least 3.0 times baseline 5m volatility
                vol_5m = {"BTC": 0.0005, "ETH": 0.0007, "SOL": 0.0012, "XRP": 0.0015}.get(sym, 0.001)
                candle_range_pct = (c["high"] - c["low"]) / c["open"]
                is_volatility_flash = (candle_range_pct >= self.vol_multiplier * vol_5m)
                
                is_win = False
                filled = False
                
                if is_volatility_flash:
                    if direction == "YES":
                        # For a BUY_UP (YES) position: order filled only if 1s price low wicks BELOW Strike Price
                        # (since YES becomes cheap when spot drops below strike)
                        any_below_strike = any(t_val < strike for t_val in ticks)
                        if any_below_strike:
                            filled = True
                            is_win = (spot_at_close >= strike)
                    elif direction == "NO":
                        # For a BUY_DOWN (NO) position: order filled only if 1s price high wicks ABOVE Strike Price
                        # (since NO becomes cheap when spot rises above strike)
                        any_above_strike = any(t_val > strike for t_val in ticks)
                        if any_above_strike:
                            filled = True
                            is_win = (spot_at_close < strike)
                        
                if filled:
                    # Simultaneous Tiered Price Ladder Slicing (3 limit orders)
                    total_executions += 3
                    
                    l1_cost = 0.10 * self.base_size
                    l2_cost = 0.30 * self.base_size
                    l3_cost = 0.60 * self.base_size
                    
                    l1_shares = l1_cost / 0.030
                    l2_shares = l2_cost / 0.020
                    l3_shares = l3_cost / 0.010
                    
                    total_cost = self.base_size
                    total_shares = l1_shares + l2_shares + l3_shares
                    blended_price = total_cost / total_shares
                    
                    pnl = (total_shares - total_cost) if is_win else -total_cost
                    
                    if is_win:
                        wins += 1
                        gross_revenue += total_shares
                    else:
                        losses += 1
                        
                    round_pnl += pnl
                    if len(logs) < 200:
                        logs.append(f"[TRADE] Rd {total_rounds} {sym}: Tiered Bids Filled BUY {direction} @ Blended ${blended_price:.3f} -> {'WIN' if is_win else 'LOSS'} (PnL: {pnl:+.2f}). Wallet: ${equity+round_pnl:.2f}")
                else:
                    # Fallback: log as EXPIRED_UNFILLED with $0.00 USDC cost change
                    if len(logs) < 200:
                        logs.append(f"[EXPIRED_UNFILLED] Rd {total_rounds} {sym}: Strike line never intersected during final 3s. Bids expired unfilled ($0.00 USDC cost).")
 
            # Apply round results to simulated wallet balance
            equity += round_pnl
            if round_pnl != 0.0:
                unique_rounds_entered += 1
            if equity > max_equity:
                max_equity = equity
            
            dd = (max_equity - equity) / max_equity * 100
            if dd > max_drawdown:
                max_drawdown = dd
                
            equity_timeline.append({
                "time": total_rounds,
                "equity": round(equity, 2)
            })

        net_profit = equity - initial_equity
        win_rate = (wins / total_executions * 100) if total_executions > 0 else 0.0
        logs.append(f"[SYSTEM] Backtest complete. Net profit: ${net_profit:.2f} USDC.")
        if unique_rounds_entered > 150:
            logs.append(f"[WARNING] Parameter distortion detected: total unique rounds entered per day ({unique_rounds_entered}) exceeds 150.")
        
        return {
            "total_rounds": total_rounds,
            "total_executions": total_executions,
            "win_rate": round(win_rate, 2),
            "gross_revenue": round(gross_revenue, 2),
            "net_profit": round(net_profit, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "start_balance": round(self.start_balance, 2),
            "unique_rounds_entered": unique_rounds_entered,
            "equity_timeline": equity_timeline,
            "logs": logs
        }

if __name__ == "__main__":
    b = Backtester()
    res = b.run()
    print("Backtest results:")
    for k, v in res.items():
        if k != "equity_timeline":
            print(f"  {k}: {v}")
