import pandas as pd
import re

class Backtester:
    def __init__(self, csv_path="/Users/khash/Downloads/egig_trades_crypto.csv"):
        self.csv_path = csv_path
        self.df = None
        self.slug_winners = {}
        self.sim_results = []
        self.stats = {}

    def preprocess(self):
        """Loads and preprocesses the CSV dataset."""
        self.df = pd.read_csv(self.csv_path)
        
        # Parse start timestamp and duration from slug
        def parse_slug_info(slug):
            # Format: <symbol>-updown-<5m/15m>-<timestamp>
            match = re.search(r'-(\d+)[m|M]-(\d+)$', slug)
            if match:
                duration_m = int(match.group(1))
                start_ts = int(match.group(2))
                return start_ts, duration_m * 60
            return None, None

        slug_info = self.df['slug'].apply(parse_slug_info)
        self.df['start_time'] = [info[0] for info in slug_info]
        self.df['duration_seconds'] = [info[1] for info in slug_info]
        
        # Calculate window close time and time delta
        # If start_time or duration_seconds is None, close_time is None
        self.df['close_time'] = self.df['start_time'] + self.df['duration_seconds']
        self.df['delta_t'] = self.df['timestamp'] - self.df['close_time']
        
        # Sort chronologically by timestamp
        self.df = self.df.sort_values(by='timestamp').reset_index(drop=True)

    def resolve_outcomes(self):
        """Resolves winning outcomes for market slugs programmatically."""
        # Group by slug and find the highest priced BUY trade
        for slug, group in self.df.groupby('slug'):
            buy_trades = group[group['side'] == 'BUY']
            if len(buy_trades) == 0:
                continue
            max_idx = buy_trades['price'].idxmax()
            max_row = buy_trades.loc[max_idx]
            max_price = max_row['price']
            outcome = max_row['outcome']
            if max_price >= 0.95:
                self.slug_winners[slug] = outcome

    def run_simulation(self, initial_wallet=1000.00):
        """Runs the wallet and accounting simulation over chronological BUY trades."""
        wallet = initial_wallet
        total_trades = 0
        resolved_trades = 0
        wins = 0
        losses = 0
        unresolved_count = 0
        unresolved_cost = 0.0
        
        arbitrage_wins = 0
        penny_wins = 0
        net_pnl = 0.0

        sim_records = []

        # We evaluate BUY trades for the simulation
        buy_df = self.df[self.df['side'] == 'BUY'].copy()

        for _, row in buy_df.iterrows():
            slug = row['slug']
            cost = row['usdc_size']
            shares = row['size']
            outcome = row['outcome']
            price = row['price']
            timestamp = row['timestamp']
            
            total_trades += 1
            
            # Deduct cost from wallet
            wallet -= cost
            
            if slug in self.slug_winners:
                resolved_trades += 1
                winning_outcome = self.slug_winners[slug]
                is_win = (outcome == winning_outcome)
                
                if is_win:
                    wins += 1
                    wallet += shares
                    pnl = shares - cost
                    status = "WIN"
                    
                    # Categorize winning strategy
                    if 0.95 <= price <= 0.99:
                        arbitrage_wins += 1
                    elif 0.01 <= price <= 0.05:
                        penny_wins += 1
                else:
                    losses += 1
                    pnl = -cost
                    status = "LOSS"
                
                net_pnl += pnl
            else:
                unresolved_count += 1
                unresolved_cost += cost
                pnl = 0.0
                status = "UNRESOLVED"
                # Since we don't know the outcome, we don't know if we won or lost.
                # To prevent draining the wallet, we "reimburse" the cost in the simulated wallet,
                # effectively keeping unresolved trades neutral in terms of reported wallet balance.
                # Or we can simply report wallet balance purely for resolved trades.
                # Let's keep wallet balance purely for resolved trades, which is:
                # wallet_balance = initial_wallet + net_pnl
                wallet += cost # Neutralize unresolved cost on the main wallet balance

            sim_records.append({
                'timestamp': timestamp,
                'datetime_utc': row['datetime_utc'],
                'slug': slug,
                'outcome': outcome,
                'price': price,
                'size': shares,
                'usdc_size': cost,
                'status': status,
                'pnl': pnl,
                'wallet': initial_wallet + net_pnl
            })

        self.sim_results = sim_records
        
        self.stats = {
            'initial_wallet': initial_wallet,
            'final_wallet': initial_wallet + net_pnl,
            'net_pnl_usdc': net_pnl,
            'net_pnl_pct': (net_pnl / initial_wallet) * 100,
            'total_trades': total_trades,
            'resolved_trades': resolved_trades,
            'unresolved_trades': unresolved_count,
            'unresolved_cost_usdc': unresolved_cost,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / resolved_trades * 100) if resolved_trades > 0 else 0.0,
            'arbitrage_wins': arbitrage_wins,
            'penny_wins': penny_wins
        }

if __name__ == "__main__":
    b = Backtester()
    print("Preprocessing data...")
    b.preprocess()
    print("Resolving outcomes...")
    b.resolve_outcomes()
    print("Running simulation...")
    b.run_simulation()
    print("Simulation Complete!")
    for k, v in b.stats.items():
        print(f"  {k}: {v}")
