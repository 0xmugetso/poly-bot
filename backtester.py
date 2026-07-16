import time
import json
import random
import urllib.request
from datetime import datetime, timezone

class Backtester:
    def __init__(self, start_date=None, end_date=None, proximity_limit=0.0002, obi_cutoff=0.65, base_size=10.0):
        self.start_date = start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.end_date = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.proximity_limit = float(proximity_limit)
        self.obi_cutoff = float(obi_cutoff)
        self.base_size = float(base_size)
        self.symbols = ["BTC", "ETH", "SOL", "XRP", "BNB"]

    def fetch_binance_klines(self, symbol, limit=500):
        """Fetches historical 1-minute candles from Binance REST API."""
        try:
            # Map symbol names to standard USDT pairs
            pair = f"{symbol}USDT"
            url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval=1m&limit={limit}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=5).read()
            data = json.loads(res)
            # Row format: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
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
            return None

    def generate_monte_carlo_candles(self, symbol, start_price, limit=500):
        """Generates high-fidelity synthetic candles as a fallback."""
        candles = []
        current_price = start_price
        # Adjust volatilities matching current market states
        vols = {"BTC": 0.0005, "ETH": 0.0007, "SOL": 0.0012, "XRP": 0.0015, "BNB": 0.0008}
        vol = vols.get(symbol, 0.001)
        
        t_now = int(time.time()) - (limit * 60)
        for i in range(limit):
            op = current_price
            prices = [op]
            for _ in range(4): # interpolate 4 ticks per minute
                current_price *= (1 + random.normalvariate(0, vol))
                prices.append(current_price)
            cl = current_price
            candles.append({
                "open": op,
                "high": max(prices),
                "low": min(prices),
                "close": cl,
                "time": t_now + (i * 60)
            })
        return candles

    def run(self):
        """Runs the historical strategy backtest simulation."""
        results = []
        equity = 1000.0  # Simulated initial wallet
        initial_equity = equity
        max_equity = equity
        max_drawdown = 0.0
        
        total_rounds = 0
        total_executions = 0
        wins = 0
        losses = 0
        gross_revenue = 0.0
        
        logs = [
            "[SYSTEM] Initializing Backtester...",
            f"[SYSTEM] Date range parameters: {self.start_date} to {self.end_date}",
            f"[SYSTEM] Proximity limit: {self.proximity_limit*100:.3f}% | OBI cutoff: {self.obi_cutoff:.2f} | Base size: ${self.base_size:.1f}"
        ]
        
        # We simulate over 5-minute boundaries
        # Fetch 500 minutes of historical data (covers ~100 rounds of 5m intervals)
        symbol_candles = {}
        for sym in self.symbols:
            candles = self.fetch_binance_klines(sym, limit=500)
            if not candles:
                # Fallback to Monte Carlo simulation
                start_prices = {"BTC": 67000.0, "ETH": 3450.0, "SOL": 140.0, "XRP": 0.58, "BNB": 580.0}
                candles = self.generate_monte_carlo_candles(sym, start_prices.get(sym, 10.0), limit=500)
                logs.append(f"[DATA] Offline/Geoblocked. Generated 500 Monte Carlo candles for {sym}.")
            else:
                logs.append(f"[DATA] Fetched 500 historical candles for {sym} from Binance API.")
            symbol_candles[sym] = candles
        
        # Check data length
        data_len = min(len(symbol_candles[sym]) for sym in self.symbols)
        if data_len < 5:
            return {
                "error": "Insufficient historical data fetched.",
                "total_rounds": 0, "total_executions": 0, "win_rate": 0, "net_profit": 0,
                "logs": logs
            }

        # Step through 5-candle groups (each representing a 5-minute round)
        equity_timeline = [{"time": 0, "equity": equity}]
        
        for idx in range(0, data_len - 5, 5):
            total_rounds += 1
            round_pnl = 0.0
            
            for sym in self.symbols:
                candles = symbol_candles[sym][idx : idx + 5]
                # Open of first candle is the strike price
                strike = candles[0]["open"]
                # Close of 5th candle is spot price at close
                spot_at_5s = candles[4]["close"]
                spot_at_close = candles[4]["close"]
                
                # Proximity calculation
                proximity = abs(spot_at_5s - strike) / strike
                spot_strike_delta = abs(spot_at_5s - strike)
                
                if proximity <= self.proximity_limit:
                    # Model YES/NO prices
                    delta = spot_at_5s - strike
                    volatility_factor = 2.0 if sym in ["BTC", "BNB"] else 0.1
                    val = -delta / volatility_factor
                    # Apply sigmoid bounds
                    price_yes = 1 / (1 + 2.718 ** max(-50.0, min(50.0, val)))
                    price_yes = max(0.01, min(0.99, price_yes))
                    price_no = 1 - price_yes
                    
                    # Generate deterministic historical OBI (based on candle momentum)
                    candle_returns = [c["close"] - c["open"] for c in candles]
                    avg_return = sum(candle_returns) / len(candle_returns)
                    base_obi = max(-0.95, min(0.95, avg_return / (strike * 0.001)))
                    # Add random noise to OBI
                    obi = base_obi + random.uniform(-0.15, 0.15)
                    
                    yes_in_range = (0.01 <= price_yes <= 0.04)
                    no_in_range = (0.01 <= price_no <= 0.04)
                    traded = False
                    
                    # Evaluate Strategy B gates
                    if yes_in_range and obi > self.obi_cutoff:
                        total_executions += 1
                        cost = self.base_size
                        shares = cost / price_yes
                        
                        is_win = (spot_at_close >= strike)
                        pnl = (shares - cost) if is_win else -cost
                        if is_win:
                            wins += 1
                            gross_revenue += shares
                        else:
                            losses += 1
                        round_pnl += pnl
                        traded = True
                        if len(logs) < 200:
                            logs.append(f"[TRADE] Rd {total_rounds} {sym}: BUY YES @ ${price_yes:.3f} -> {'WIN' if is_win else 'LOSS'} (PnL: {pnl:+.2f}). Wallet: ${equity+round_pnl:.2f}")
                        
                    elif no_in_range and obi < -self.obi_cutoff:
                        total_executions += 1
                        cost = self.base_size
                        shares = cost / price_no
                        
                        is_win = (spot_at_close < strike)
                        pnl = (shares - cost) if is_win else -cost
                        if is_win:
                            wins += 1
                            gross_revenue += shares
                        else:
                            losses += 1
                        round_pnl += pnl
                        traded = True
                        if len(logs) < 200:
                            logs.append(f"[TRADE] Rd {total_rounds} {sym}: BUY NO @ ${price_no:.3f} -> {'WIN' if is_win else 'LOSS'} (PnL: {pnl:+.2f}). Wallet: ${equity+round_pnl:.2f}")
                            
                    if not traded and (yes_in_range or no_in_range) and len(logs) < 200:
                        logs.append(f"[BLOCKED] Rd {total_rounds} {sym}: OBI ({obi:.3f}) momentum insufficient (YES/NO Ask: ${price_yes:.2f}/${price_no:.2f}).")
                else:
                    if len(logs) < 200:
                        logs.append(f"[BLOCKED] Rd {total_rounds} {sym}: Proximity delta (${spot_strike_delta:.2f}) exceeded limit.")

            # Apply round results to simulated wallet balance
            equity += round_pnl
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
        
        return {
            "total_rounds": total_rounds,
            "total_executions": total_executions,
            "win_rate": round(win_rate, 2),
            "gross_revenue": round(gross_revenue, 2),
            "net_profit": round(net_profit, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
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
