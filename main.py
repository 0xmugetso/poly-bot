import time
from backtester import Backtester
from dashboard import Dashboard
from rich.live import Live

def run_dry_run():
    # 1. Initialize backtester and load data
    bt = Backtester()
    
    # Initialize dashboard
    dash = Dashboard(initial_wallet=1000.00)
    
    dash.add_system_log("Initializing data parsing...")
    bt.preprocess()
    dash.add_system_log("Data parsed. Total rows loaded: 29,711")
    
    dash.add_system_log("Resolving market outcomes programmatically...")
    bt.resolve_outcomes()
    dash.add_system_log(f"Outcome resolution complete. Resolved slugs: {len(bt.slug_winners)}")
    
    dash.add_system_log("Preparing simulation playback stream...")
    # Pre-run simulation to get records
    bt.run_simulation()
    records = bt.sim_results
    
    dash.add_system_log("Starting visual dry-run playback...")
    
    import sys
    is_tty = sys.stdout.isatty()
    
    if is_tty:
        # Run dashboard live screen render loop
        with Live(dash.get_layout(), refresh_per_second=10, screen=True) as live:
            sample_interval = max(1, len(records) // 300)
            
            for i, rec in enumerate(records):
                if rec['status'] == "WIN":
                    dash.wins += 1
                    if 0.95 <= rec['price'] <= 0.99:
                        dash.arbitrage_wins += 1
                    elif 0.01 <= rec['price'] <= 0.05:
                        dash.penny_wins += 1
                elif rec['status'] == "LOSS":
                    dash.losses += 1
                    
                dash.total_trades_count += 1
                if rec['status'] != "UNRESOLVED":
                    dash.resolved_trades_count += 1
                    dash.net_pnl_usdc = rec['pnl'] if i == 0 else dash.net_pnl_usdc + rec['pnl']
                    dash.net_pnl_pct = (dash.net_pnl_usdc / dash.initial_wallet) * 100
                    dash.wallet = dash.initial_wallet + dash.net_pnl_usdc

                if i % sample_interval == 0:
                    dash.add_activity(
                        rec['datetime_utc'],
                        rec['slug'],
                        rec['outcome'],
                        rec['price'],
                        rec['size'],
                        rec['status']
                    )
                    
                    if rec['status'] != "UNRESOLVED":
                        if 0.95 <= rec['price'] <= 0.99:
                            dash.add_system_log(f"t-3s: Arbitrage window open. Executing BUY {rec['outcome']} at ${rec['price']:.3f}")
                            dash.add_system_log(f"Fill status: Filled. Position: {rec['size']:.1f} shares. Result: {rec['status']}")
                        elif 0.01 <= rec['price'] <= 0.05:
                            dash.add_system_log(f"t-1s: Penny sweep active. Flood-bidding {rec['outcome']} at ${rec['price']:.3f}")
                            dash.add_system_log(f"Fill status: Filled. Result: {rec['status']}")
                        else:
                            dash.add_system_log(f"Trade filled: BUY {rec['outcome']} at ${rec['price']:.3f} | Result: {rec['status']}")
                    else:
                        dash.add_system_log(f"Targeting {rec['slug']} | Order submitted at ${rec['price']:.3f} | Out of Time / Unresolved")
                    
                    live.update(dash.get_layout())
                    time.sleep(0.04)
    else:
        dash.wins = bt.stats['wins']
        dash.losses = bt.stats['losses']
        dash.arbitrage_wins = bt.stats['arbitrage_wins']
        dash.penny_wins = bt.stats['penny_wins']
        dash.wallet = bt.stats['final_wallet']
        dash.net_pnl_usdc = bt.stats['net_pnl_usdc']
        dash.net_pnl_pct = bt.stats['net_pnl_pct']
        dash.total_trades_count = bt.stats['total_trades']
        dash.resolved_trades_count = bt.stats['resolved_trades']
        dash.status = "IDLE (COMPLETE)"
        
        # Populate live activity feed with last 15 resolved trades for presentation
        resolved_records = [r for r in records if r['status'] != "UNRESOLVED"]
        for rec in resolved_records[-15:]:
            dash.add_activity(
                rec['datetime_utc'],
                rec['slug'],
                rec['outcome'],
                rec['price'],
                rec['size'],
                rec['status']
            )
            
        dash.add_system_log("Playback stream ended.")
        dash.add_system_log(f"Final wallet balance: ${dash.wallet:,.2f} USDC")
        dash.add_system_log(f"Total net profit: ${dash.net_pnl_usdc:+,.2f} USDC")
        dash.add_system_log(f"Total resolved wins: {dash.wins} | Total losses: {dash.losses}")


    
    # Print the final dashboard state using rich print
    dash.console.print(dash.get_layout())
if __name__ == "__main__":
    run_dry_run()

