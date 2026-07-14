from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.live import Live
from rich.columns import Columns
from datetime import datetime

class Dashboard:
    def __init__(self, initial_wallet=1000.00):
        self.console = Console()
        self.initial_wallet = initial_wallet
        self.wallet = initial_wallet
        self.net_pnl_usdc = 0.0
        self.net_pnl_pct = 0.0
        self.wins = 0
        self.losses = 0
        self.arbitrage_wins = 0
        self.penny_wins = 0
        self.total_trades_count = 0
        self.resolved_trades_count = 0
        
        # UI state
        self.status = "DRY-RUN"
        self.latency_ms = 1.2
        self.rpc_node_health = "HEALTHY"
        
        # Logging history
        self.activity_log = []
        self.max_activity = 15
        
        self.system_logs = []
        self.max_system_logs = 15

    def add_activity(self, datetime_utc, slug, outcome, price, size, status):
        """Adds a trade execution record to the live activity feed."""
        self.activity_log.append({
            'datetime_utc': datetime_utc,
            'slug': slug,
            'outcome': outcome,
            'price': price,
            'size': size,
            'status': status
        })
        if len(self.activity_log) > self.max_activity:
            self.activity_log.pop(0)

    def add_system_log(self, msg):
        """Adds a background process log message."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.system_logs.append(f"[{timestamp}] {msg}")
        if len(self.system_logs) > self.max_system_logs:
            self.system_logs.pop(0)

    def generate_header(self) -> Panel:
        """Generates the header block panel."""
        status_color = "green" if self.status == "ACTIVE" else "yellow"
        health_color = "green" if self.rpc_node_health == "HEALTHY" else "red"
        
        header_text = Text()
        header_text.append("ANTIGRAVITY POLYMARKET ARBITRAGE BOT ", style="bold cyan")
        header_text.append("|  STATUS: ", style="bold white")
        header_text.append(self.status, style=f"bold {status_color}")
        header_text.append("  |  WEBSOCKET LATENCY: ", style="bold white")
        header_text.append(f"{self.latency_ms:.1f}ms", style="bold green" if self.latency_ms < 5 else "bold yellow")
        header_text.append("  |  RPC NODE: ", style="bold white")
        header_text.append(self.rpc_node_health, style=f"bold {health_color}")
        
        return Panel(Align.center(header_text), border_style="cyan")

    def generate_metrics(self) -> Table:
        """Generates a grid table showing current wallet performance metrics."""
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        
        # Calculate win rate
        total_resolved = self.wins + self.losses
        win_rate_val = (self.wins / total_resolved * 100) if total_resolved > 0 else 0.0
        
        # Color codes
        pnl_color = "green" if self.net_pnl_usdc >= 0 else "red"
        
        # Metric 1: Wallet Balance
        wallet_panel = Panel(
            Align.center(Text(f"${self.wallet:,.2f} USDC", style="bold white")),
            title="Wallet Balance",
            border_style="white"
        )
        
        # Metric 2: Net PnL
        pnl_panel = Panel(
            Align.center(Text(f"${self.net_pnl_usdc:+,.2f} USDC ({self.net_pnl_pct:+.2f}%)", style=f"bold {pnl_color}")),
            title="Net PnL",
            border_style=pnl_color
        )
        
        # Metric 3: Win Rate
        win_rate_panel = Panel(
            Align.center(Text(f"{win_rate_val:.2f}% ({self.wins}W - {self.losses}L)", style="bold green")),
            title="Win Rate",
            border_style="green"
        )
        
        # Metric 4: Strategy Split
        strategy_panel = Panel(
            Align.center(Text(f"Arb: {self.arbitrage_wins} | Penny: {self.penny_wins}", style="bold magenta")),
            title="Strategy Wins (Arb / Penny)",
            border_style="magenta"
        )
        
        grid.add_row(wallet_panel, pnl_panel, win_rate_panel, strategy_panel)
        return grid

    def generate_activity_table(self) -> Panel:
        """Generates the live activity scrolling feed table."""
        table = Table(expand=True, show_header=True, header_style="bold blue")
        table.add_column("Timestamp (UTC)", ratio=2)
        table.add_column("Market Slug", ratio=4)
        table.add_column("Side/Outcome", ratio=2)
        table.add_column("Entry Price", ratio=2, justify="right")
        table.add_column("Position Size", ratio=2, justify="right")
        table.add_column("PnL Status", ratio=2, justify="center")

        for act in reversed(self.activity_log):
            status_style = "bold yellow"
            if act['status'] == "WIN":
                status_style = "bold green"
            elif act['status'] == "LOSS":
                status_style = "bold red"
                
            table.add_row(
                act['datetime_utc'],
                act['slug'],
                f"BUY {act['outcome']}",
                f"${act['price']:.3f}",
                f"{act['size']:,.2f}",
                Text(act['status'], style=status_style)
            )

        return Panel(table, title="Live Activity Feed", border_style="blue")

    def generate_system_logs(self) -> Panel:
        """Generates the scrolling system process logs view."""
        log_text = Text()
        for log in self.system_logs:
            # Highlight keyword colors
            if "Arbitrage window" in log or "Executing BUY" in log:
                log_text.append(log + "\n", style="cyan")
            elif "WIN" in log or "filled" in log:
                log_text.append(log + "\n", style="green")
            elif "LOSS" in log or "failed" in log:
                log_text.append(log + "\n", style="red")
            else:
                log_text.append(log + "\n", style="white")

        return Panel(log_text, title="System Process Monitor", border_style="cyan")

    def get_layout(self) -> Layout:
        """Assembles the final page layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="metrics", size=4),
            Layout(name="body", ratio=8)
        )
        
        layout["body"].split_row(
            Layout(name="activity", ratio=1),
            Layout(name="system_logs", ratio=1)
        )
        
        layout["header"].update(self.generate_header())
        layout["metrics"].update(self.generate_metrics())
        layout["activity"].update(self.generate_activity_table())
        layout["system_logs"].update(self.generate_system_logs())
        
        return layout
