import time
import json
import random
import os
import urllib.request
import ssl
import re
import gc
from datetime import datetime, timezone, timedelta
import pandas as pd

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def check_memory_usage_mb():
    if HAS_PSUTIL:
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            pass
    try:
        import resource
        import sys
        rusage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == 'darwin':
            return rusage / (1024 * 1024)  # macOS returns ru_maxrss in bytes
        else:
            return rusage / 1024          # Linux returns ru_maxrss in kilobytes
    except Exception:
        return 0.0

def get_market_details_cached(slug):
    cache_path = "market_details_cache.json"
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cache = json.load(f)
        except Exception:
            pass
            
    if slug in cache:
        return cache[slug]
        
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}&closed=true"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    ctx = ssl._create_unverified_context()
    
    # Retry loop with backoff for rate limiting
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as res:
                data = json.loads(res.read().decode('utf-8'))
                if data:
                    m = data[0]
                    
                    # Parse clobTokenIds safely
                    clob_raw = m.get("clobTokenIds")
                    if isinstance(clob_raw, str):
                        clob_tokens = json.loads(clob_raw)
                    else:
                        clob_tokens = clob_raw or []
                        
                    # Parse outcomes safely
                    outcomes_raw = m.get("outcomes")
                    if isinstance(outcomes_raw, str):
                        outcomes = json.loads(outcomes_raw)
                    else:
                        outcomes = outcomes_raw or []
                        
                    # Parse outcomePrices safely
                    prices_raw = m.get("outcomePrices")
                    if isinstance(prices_raw, str):
                        prices = json.loads(prices_raw)
                    else:
                        prices = prices_raw or []
                        
                    details = {
                        "conditionId": m.get("conditionId"),
                        "clobTokenIds": clob_tokens,
                        "question": m.get("question"),
                        "outcomes": outcomes,
                        "outcomePrices": prices,
                        "closed": m.get("closed"),
                        "active": m.get("active")
                    }
                    cache[slug] = details
                    # Enforce max 100 cache entries eviction
                    if len(cache) > 100:
                        keys_to_remove = list(cache.keys())[:-100]
                        for k in keys_to_remove:
                            cache.pop(k, None)
                    with open(cache_path, "w") as f:
                        json.dump(cache, f)
                    return details
                else:
                    return None
        except Exception as e:
            if "429" in str(e):
                time.sleep(2.0)
            else:
                break
    return None

class Backtester:
    def __init__(self, start_date=None, end_date=None, proximity_limit=0.0002, obi_cutoff=0.65, base_size=10.0, start_balance=1000.0, vol_multiplier=4.8):
        self.start_date = start_date or "2026-07-13"
        self.end_date = end_date or "2026-07-14"
        self.proximity_limit = float(proximity_limit)
        self.obi_cutoff = float(obi_cutoff)
        self.base_size = float(base_size)
        self.start_balance = float(start_balance)
        self.vol_multiplier = float(vol_multiplier)
        self.symbols = ["BTC", "ETH", "SOL", "XRP"]

    def run(self):
        start_time = time.time()
        logs = []
        logs.append("[SYSTEM] Initializing Polymarket historical L2 backtest engine...")
        
        # Parse dates
        try:
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(self.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        except Exception as e:
            return {"error": f"Invalid date format: {e}"}
            
        logs.append(f"[SYSTEM] Backtesting period: {self.start_date} to {self.end_date}")
        
        # 1. Generate all 5-minute round close times in the date range
        close_times = []
        curr = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        if curr % 300 != 0:
            curr += (300 - (curr % 300))
        while curr < end_ts:
            close_times.append(curr)
            curr += 300
            
        logs.append(f"[SYSTEM] Generated {len(close_times)} target 5-minute rounds.")
        
        # 2. Gather market details (conditionId, clobTokenIds) for all rounds and symbols
        rounds_to_evaluate = []
        logs.append("[SYSTEM] Querying Polymarket Gamma API metadata (with local cache)...")
        
        for t_close in close_times:
            if time.time() - start_time > 45.0:
                logs.append("[BACKTEST TIMEOUT] Metadata fetch exceeded 45 seconds limit.")
                break
            epoch_start = t_close - 300
            for sym in self.symbols:
                slug = f"{sym.lower()}-updown-5m-{epoch_start}"
                details = get_market_details_cached(slug)
                if details and details.get("conditionId") and len(details.get("clobTokenIds", [])) >= 2:
                    rounds_to_evaluate.append({
                        "slug": slug,
                        "symbol": sym,
                        "epoch_start": epoch_start,
                        "epoch_close": t_close,
                        "details": details
                    })
                    
        logs.append(f"[SYSTEM] Found {len(rounds_to_evaluate)} valid Polymarket 5m rounds to evaluate.")
        if not rounds_to_evaluate:
            return {
                "total_rounds": 0,
                "total_executions": 0,
                "win_rate": 0.0,
                "gross_revenue": 0.0,
                "net_profit": 0.0,
                "max_drawdown_pct": 0.0,
                "start_balance": round(self.start_balance, 2),
                "unique_rounds_entered": 0,
                "equity_timeline": [{"time": 0, "equity": self.start_balance}],
                "logs": logs
            }
            
        # Group rounds by the hour they close in
        rounds_by_hour = {}
        for r in rounds_to_evaluate:
            dt = datetime.fromtimestamp(r["epoch_close"], tz=timezone.utc)
            hour_str = dt.strftime("%Y-%m-%dT%H")
            if hour_str not in rounds_by_hour:
                rounds_by_hour[hour_str] = []
            rounds_by_hour[hour_str].append(r)
            
        sorted_hours = sorted(rounds_by_hour.keys())
        
        # 3. Bulk pre-fetch missing parquet files into local parquet_cache directory
        cache_dir = "parquet_cache"
        os.makedirs(cache_dir, exist_ok=True)
        ctx = ssl._create_unverified_context()
        
        logs.append(f"[SYSTEM] Bulk pre-fetching Parquet archives for {len(sorted_hours)} hours...")
        for hour_str in sorted_hours:
            local_parquet = os.path.join(cache_dir, f"polymarket_orderbook_{hour_str}.parquet")
            if not os.path.exists(local_parquet) or os.path.getsize(local_parquet) == 0:
                url = f"https://r2v2.pmxt.dev/polymarket_orderbook_{hour_str}.parquet"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                try:
                    with urllib.request.urlopen(req, timeout=15, context=ctx) as response, open(local_parquet, 'wb') as out_file:
                        out_file.write(response.read())
                except Exception as e:
                    if len(logs) < 200:
                        logs.append(f"[WARNING] Pre-fetch failed for {hour_str}: {e}")
            gc.collect()
                        
        equity = self.start_balance
        max_equity = equity
        max_drawdown = 0.0
        
        total_rounds = 0
        total_executions = 0
        wins = 0
        losses = 0
        gross_revenue = 0.0
        unique_rounds_entered = 0
        equity_timeline = [{"time": 0, "equity": equity}]
        
        # 4. Process hour-by-hour using local batch files
        sim_start_time = time.time()
        initial_sim_mem = check_memory_usage_mb()
        
        for hour_str in sorted_hours:
            current_mem = check_memory_usage_mb()
            # Guard against memory leaks during simulation (> 2000 MB growth during simulation phase or total > 4000 MB)
            if (current_mem - initial_sim_mem > 2000.0) or (current_mem > 4000.0):
                logs.append(f"[MEMORY_SAFETY_LIMIT_REACHED] Simulation halted: memory growth ({current_mem - initial_sim_mem:.1f} MB) exceeded safety threshold.")
                break

            if time.time() - sim_start_time > 45.0:
                logs.append("[BACKTEST TIMEOUT] Simulation aborted: execution exceeded 45 seconds timeout limit.")
                break
                
            hour_rounds = rounds_by_hour[hour_str]
            hour_token_ids = set()
            for r in hour_rounds:
                hour_token_ids.add(r["details"]["clobTokenIds"][0])
                hour_token_ids.add(r["details"]["clobTokenIds"][1])
                
            local_parquet = os.path.join(cache_dir, f"polymarket_orderbook_{hour_str}.parquet")
            if not os.path.exists(local_parquet) or os.path.getsize(local_parquet) == 0:
                continue
                
            df = None
            try:
                df = pd.read_parquet(
                    local_parquet, 
                    filters=[
                        ('asset_id', 'in', list(hour_token_ids)),
                        ('event_type', '==', 'last_trade_price')
                    ],
                    columns=['timestamp', 'event_type', 'asset_id', 'price', 'size', 'side']
                )
            except Exception as e:
                if len(logs) < 200:
                    logs.append(f"[WARNING] Partition {hour_str} failed to parse: {e}. Skipping rounds in this hour.")
                continue
                
            if df is None or len(df) == 0:
                continue
                
            df['price'] = df['price'].astype(float)
            df['size'] = df['size'].astype(float)
            if pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp_sec'] = df['timestamp'].astype('int64') // 10**9
            else:
                df['timestamp_sec'] = df['timestamp'] // 1000
                
            df = df.sort_values(by='timestamp_sec')
            
            for r in hour_rounds:
                if time.time() - start_time > 30.0:
                    logs.append("[BACKTEST TIMEOUT] Simulation aborted: execution exceeded 30 seconds timeout limit.")
                    break
                    
                if equity < self.base_size:
                    logs.append(f"[LIQUIDATED] Simulation halted. Account balance (${equity:.2f}) dropped below base size (${self.base_size:.1f}).")
                    break
                    
                total_rounds += 1
                sym = r["symbol"]
                epoch_start = r["epoch_start"]
                epoch_close = r["epoch_close"]
                yes_token = r["details"]["clobTokenIds"][0]
                no_token = r["details"]["clobTokenIds"][1]
                
                question = r["details"].get("question", "")
                match = re.search(r"\$(\d+(?:\.\d+)?)", question)
                strike = float(match.group(1).replace(",", "")) if match else 0.0
                
                outcome_prices = r["details"].get("outcomePrices", [])
                if len(outcome_prices) >= 2:
                    p_yes = float(outcome_prices[0])
                    if p_yes > 0.9:
                        winner = "Up"
                    else:
                        winner = "Down"
                else:
                    winner = "Down"
                    
                up_won = (winner == "Up")
                down_won = not up_won
                
                window_start = epoch_start + 295
                window_end = epoch_start + 305
                
                round_trades = df[
                    (df['timestamp_sec'] >= window_start) & 
                    (df['timestamp_sec'] <= window_end)
                ]
                
                yes_trades = round_trades[round_trades['asset_id'] == yes_token]
                no_trades = round_trades[round_trades['asset_id'] == no_token]
                
                up_l1_filled = len(yes_trades[yes_trades['price'] <= 0.03]) > 0
                up_l2_filled = len(yes_trades[yes_trades['price'] <= 0.02]) > 0
                up_l3_filled = len(yes_trades[yes_trades['price'] <= 0.01]) > 0
                
                down_l1_filled = len(no_trades[no_trades['price'] <= 0.03]) > 0
                down_l2_filled = len(no_trades[no_trades['price'] <= 0.02]) > 0
                down_l3_filled = len(no_trades[no_trades['price'] <= 0.01]) > 0
                
                round_cost = 0.0
                round_shares = 0.0
                round_pnl = 0.0
                executions_in_round = 0
                
                up_fills = [up_l1_filled, up_l2_filled, up_l3_filled]
                up_prices = [0.030, 0.020, 0.010]
                up_allocations = [0.10, 0.30, 0.60]
                
                for filled_flag, p_limit, alloc in zip(up_fills, up_prices, up_allocations):
                    if filled_flag:
                        cost = alloc * self.base_size
                        shares = cost / p_limit
                        round_cost += cost
                        round_shares += shares
                        executions_in_round += 1
                        
                        pnl = (shares - cost) if up_won else -cost
                        round_pnl += pnl
                        if up_won:
                            wins += 1
                            gross_revenue += shares
                        else:
                            losses += 1
                            
                down_fills = [down_l1_filled, down_l2_filled, down_l3_filled]
                down_prices = [0.030, 0.020, 0.010]
                down_allocations = [0.10, 0.30, 0.60]
                
                for filled_flag, p_limit, alloc in zip(down_fills, down_prices, down_allocations):
                    if filled_flag:
                        cost = alloc * self.base_size
                        shares = cost / p_limit
                        round_cost += cost
                        round_shares += shares
                        executions_in_round += 1
                        
                        pnl = (shares - cost) if down_won else -cost
                        round_pnl += pnl
                        if down_won:
                            wins += 1
                            gross_revenue += shares
                        else:
                            losses += 1
                            
                if round_cost > 0.0:
                    total_executions += executions_in_round
                    equity += round_pnl
                    unique_rounds_entered += 1
                    
                    if len(logs) < 200:
                        logs.append(
                            f"[TRADE] Rd {total_rounds} {sym} @ Strike ${strike:,.2f}: Both sides limit orders evaluated. "
                            f"Up Fills=[L1={up_l1_filled}, L2={up_l2_filled}, L3={up_l3_filled}], "
                            f"Down Fills=[L1={down_l1_filled}, L2={down_l2_filled}, L3={down_l3_filled}] -> "
                            f"Outcome: {winner} won. PnL: {round_pnl:+.2f} USDC. Wallet: ${equity:.2f}"
                        )
                else:
                    if len(logs) < 200:
                        logs.append(
                            f"[EXPIRED_UNFILLED] Rd {total_rounds} {sym}: Passive resting buy limit orders on BOTH sides "
                            f"expired unfilled ($0.00 USDC cost change)."
                        )
                        
                equity_timeline.append({"time": total_rounds, "equity": equity})
                
                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity * 100.0
                if dd > max_drawdown:
                    max_drawdown = dd
                    
            if equity < self.base_size:
                break

            del df
            gc.collect()

        gc.collect()
        net_profit = equity - self.start_balance
        win_rate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0
        
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
