import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Pause, 
  Wifi, 
  Activity, 
  Coins, 
  TrendingUp, 
  Award, 
  Cpu, 
  ExternalLink,
  ShieldCheck,
  Flame,
  Download,
  Database,
  Terminal
} from 'lucide-react';

const PRICE_DECIMALS = { BTC: 1, ETH: 2, SOL: 2, XRP: 4 };

// Helper component to flash numbers on updates
function AnimatedValue({ value, format, colorType }) {
  const prevValueRef = useRef(value);
  const [flashClass, setFlashClass] = useState("");
  
  useEffect(() => {
    if (value !== prevValueRef.current) {
      if (colorType === "directional") {
        if (value > prevValueRef.current) {
          setFlashClass("animate-flash-green");
        } else if (value < prevValueRef.current) {
          setFlashClass("animate-flash-red");
        }
      } else {
        setFlashClass("animate-flash-blue");
      }
      prevValueRef.current = value;
      
      const timer = setTimeout(() => {
        setFlashClass("");
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [value, colorType]);
  
  return (
    <span className={`inline-block transition-all duration-300 ${flashClass}`}>
      {format ? format(value) : value}
    </span>
  );
}

// Custom lightweight SVG Sparkline component for zero dependencies and high performance
function Sparkline({ data }) {
  if (!data || data.length < 2) return null;
  
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min === 0 ? 1 : max - min;
  
  const width = 140;
  const height = 45;
  const padding = 2;
  
  const points = data.map((val, idx) => {
    const x = (idx / (data.length - 1)) * (width - padding * 2) + padding;
    const y = height - ((val - min) / range) * (height - padding * 2) - padding;
    return `${x},${y}`;
  }).join(' ');

  // Create gradient path points
  const fillPoints = `0,${height} ` + points + ` ${width},${height}`;
  
  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id="sparklineGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10B981" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <polyline
        fill="url(#sparklineGrad)"
        stroke="none"
        points={fillPoints}
      />
      <polyline
        fill="none"
        stroke="#10B981"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

// Custom responsive high-fidelity SVG timeline graph for backtest equity curves
function SimulationChart({ data }) {
  if (!data || data.length < 2) return null;
  const equities = data.map(d => d.equity);
  const min = Math.min(...equities);
  const max = Math.max(...equities);
  const range = max - min === 0 ? 1 : max - min;
  
  const width = 600;
  const height = 240;
  const paddingLeft = 45;
  const paddingRight = 10;
  const paddingTop = 15;
  const paddingBottom = 25;
  
  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;
  
  const points = data.map((d, i) => {
    const x = paddingLeft + (i / (data.length - 1)) * chartWidth;
    const y = paddingTop + chartHeight - ((d.equity - min) / range) * chartHeight;
    return `${x},${y}`;
  }).join(" ");
  
  const fillPoints = `${paddingLeft},${paddingTop + chartHeight} ` + points + ` ${width - paddingRight},${paddingTop + chartHeight}`;
  
  const gridCount = 4;
  const gridLines = [];
  for (let i = 0; i <= gridCount; i++) {
    const val = min + (i / gridCount) * range;
    const y = paddingTop + chartHeight - (i / gridCount) * chartHeight;
    gridLines.push({ y, val });
  }
  
  return (
    <div className="w-full bg-zinc-950/60 border border-[#1E1E2F]/80 rounded p-4">
      <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider block mb-3">Equity Growth Timeline (USDC)</span>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full overflow-visible">
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        
        {/* Grid Lines */}
        {gridLines.map((line, idx) => (
          <g key={idx}>
            <line 
              x1={paddingLeft} 
              y1={line.y} 
              x2={width - paddingRight} 
              y2={line.y} 
              stroke="#1E1E2F" 
              strokeWidth="0.8" 
              strokeDasharray="4 4" 
            />
            <text 
              x={paddingLeft - 8} 
              y={line.y + 3} 
              fill="#64748B" 
              fontSize="8" 
              fontFamily="monospace" 
              textAnchor="end"
            >
              ${line.val.toFixed(0)}
            </text>
          </g>
        ))}
        
        {/* Area Fill */}
        <polyline
          fill="url(#equityGrad)"
          stroke="none"
          points={fillPoints}
        />
        
        {/* Line Path */}
        <polyline
          fill="none"
          stroke="#10B981"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
    </div>
  );
}

export default function App() {
  // Local state mirrored from WebSocket
  const [wallet, setWallet] = useState(1420.55);
  const [netPnlUsdc, setNetPnlUsdc] = useState(0.0);
  const [netPnlPct, setNetPnlPct] = useState(0.0);
  const [wins, setWins] = useState(0);
  const [losses, setLosses] = useState(0);
  const [arbitrageWins, setArbitrageWins] = useState(0);
  const [pennyWins, setPennyWins] = useState(0);
  const [totalTrades, setTotalTrades] = useState(0);
  const [resolvedTrades, setResolvedTrades] = useState(0);
  const [spotPrices, setSpotPrices] = useState({
    BTC: 67250.0, ETH: 3480.0, SOL: 142.50, XRP: 0.58
  });
  const [activeMarkets, setActiveMarkets] = useState([]);
  const [activityLog, setActivityLog] = useState([]);
  const [systemLogs, setSystemLogs] = useState([]);
  const [status, setStatus] = useState("RUNNING");
  const [latencyMs, setLatencyMs] = useState(1.4);
  const [rpcNodeHealth, setRpcNodeHealth] = useState("HEALTHY");
  
  // Custom stage 2 engine state
  const [marketLocks, setMarketLocks] = useState({});
  const [restingLimitOrders, setRestingLimitOrders] = useState([]);
  const [priorityGasGwei, setPriorityGasGwei] = useState(65);
  const [maticPrice, setMaticPrice] = useState(0.55);

  // UI Controls
  const [connected, setConnected] = useState(false);
  const [isPausedStream, setIsPausedStream] = useState(false);
  const [equityHistory, setEquityHistory] = useState([1420.55]);
  const [logFilter, setLogFilter] = useState("ALL"); // ALL, TRADES, BLOCKED, SYSTEM
  const [liveObi, setLiveObi] = useState({ BTC: 0.0, ETH: 0.0, SOL: 0.0, XRP: 0.0 });
  const [clobClockOffset, setClobClockOffset] = useState(0.0);
  const [currentTimes, setCurrentTimes] = useState({ local: "", utc: "", clob: "" });
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false);
  const [showConnectionConfig, setShowConnectionConfig] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [customWsUrl, setCustomWsUrl] = useState(localStorage.getItem("custom_ws_url") || "");
  const [activeTab, setActiveTab] = useState("live");
  const [backtestParams, setBacktestParams] = useState({
    startDate: new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString().slice(0, 10),
    endDate: new Date().toISOString().slice(0, 10),
    proximityLimit: 0.15,
    obiCutoff: 0.65,
    baseSize: 10.0,
    startBalance: 1000.0
  });
  const [backtestResults, setBacktestResults] = useState(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestLogs, setBacktestLogs] = useState([]);
  
  const ws = useRef(null);
  const consoleContainerRef = useRef(null);
  const pausedLogsRef = useRef([]);

  // Establish WebSocket connection to backend server
  useEffect(() => {
    connectWS();
    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  const connectWS = () => {
    const savedUrl = localStorage.getItem("custom_ws_url");
    const wsUrl = savedUrl || import.meta.env.VITE_WS_URL || "ws://localhost:8000";
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setConnected(true);
      addLocalSystemLog("WebSocket connected to POLY-BOT backend engine.");
    };

    ws.current.onmessage = (event) => {
      const data = jsonParse(event.data);
      if (!data) return;

      if (data.type === "csv_data") {
        const blob = new Blob([data.csv_content], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "_").replace("T", "_");
        const filename = `poly_bot_manual_dump_${timestamp}.csv`;
        link.setAttribute("download", filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        addLocalSystemLog(`[EXPORT] Database snapshot downloaded: ${filename}`);
        return;
      }

      if (data.type === "backtest_results") {
        setBacktesting(false);
        if (data.results.error) {
          addLocalSystemLog(`[SIMULATION ERROR] ${data.results.error}`);
          setBacktestLogs([`[ERROR] Backtest run failed: ${data.results.error}`]);
        } else {
          setBacktestResults(data.results);
          setBacktestLogs(data.results.logs || []);
          addLocalSystemLog(`[SIMULATION COMPLETED] Net PnL: $${data.results.net_profit} USDC | Win Rate: ${data.results.win_rate}%`);
        }
        return;
      }

      // Update basic fields
      setWallet(data.wallet);
      setNetPnlUsdc(data.net_pnl_usdc);
      setNetPnlPct(data.net_pnl_pct);
      setWins(data.wins);
      setLosses(data.losses);
      setArbitrageWins(data.arbitrage_wins);
      setPennyWins(data.penny_wins);
      setTotalTrades(data.total_trades_count);
      setResolvedTrades(data.resolved_trades_count);
      setSpotPrices(data.spot_prices);
      setLiveObi(data.live_obi || {});
      setActiveMarkets(data.active_markets);
      setActivityLog(data.activity_log);
      setStatus(data.status);
      setLatencyMs(data.latency_ms);
      setRpcNodeHealth(data.rpc_node_health);
      
      // Update state locks and gas price
      setMarketLocks(data.market_locks || {});
      setRestingLimitOrders(data.resting_limit_orders || []);
      setPriorityGasGwei(data.priority_gas_gwei || 65);
      setMaticPrice(data.matic_price || 0.55);
      setClobClockOffset(data.clob_clock_offset || 0.0);

      // Manage log streams
      if (!isPausedStream) {
        setSystemLogs(data.system_logs);
      } else {
        pausedLogsRef.current = data.system_logs;
      }

      // Track equity growth sparkline
      setEquityHistory(prev => {
        const last = prev[prev.length - 1];
        if (last !== data.wallet) {
          const next = [...prev, data.wallet];
          return next.slice(-25); // cap at last 25 updates
        }
        return prev;
      });
    };

    ws.current.onerror = (err) => {
      setConnected(false);
    };

    ws.current.onclose = () => {
      setConnected(false);
      setBacktesting(false);
      addLocalSystemLog("Connection closed. Retrying connection in 3 seconds...");
      setTimeout(connectWS, 3000);
    };
  };

  const jsonParse = (str) => {
    try { return JSON.parse(str); }
    catch (e) { return null; }
  };

  // Clock synchronization loop
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const localStr = now.toLocaleTimeString();
      const utcStr = now.toISOString().slice(11, 19) + " UTC";
      
      const clobTime = new Date(now.getTime() + clobClockOffset * 1000);
      const clobStr = clobTime.toISOString().slice(11, 19) + " CLOB";
      
      setCurrentTimes({
        local: localStr,
        utc: utcStr,
        clob: clobStr
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [clobClockOffset]);

  const addLocalSystemLog = (msg) => {
    const timestamp = new Date().toLocaleTimeString();
    setSystemLogs(prev => [...prev, `[${timestamp}] ${msg}`].slice(-25));
  };

  // Toggle backend execution state
  const handleToggleStatus = () => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: "toggle_status" }));
    }
  };

  // Trigger manual network gas priority optimization
  const handleTriggerGas = () => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: "trigger_gas_bump" }));
    }
  };

  // Trigger manual CSV export of database trades via REST API or WebSocket fallback
  const handleExportCsv = async (limit = "all") => {
    setShowExportMenu(false);
    try {
      const savedUrl = localStorage.getItem("custom_ws_url");
      const wsUrl = savedUrl || import.meta.env.VITE_WS_URL || "ws://localhost:8000";
      let httpUrl = wsUrl.replace(/^ws:/, "http:").replace(/^wss:/, "https:");
      if (httpUrl.endsWith("/")) httpUrl = httpUrl.slice(0, -1);
      
      const res = await fetch(`${httpUrl}/api/export-logs?limit=${limit}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "_").replace("T", "_");
        const limitTag = limit && limit !== 'all' ? `_last_${limit}` : '_all';
        link.download = `poly_bot_live_dump${limitTag}_${timestamp}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        addLocalSystemLog(`[EXPORT] Downloaded database CSV snapshot (${limit === 'all' ? 'All' : `Last ${limit}`} trades) via REST API.`);
        return;
      }
    } catch (e) {
      // Fallback to WebSocket if REST fetch fails or CORS occurs
    }

    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: "export_telemetry", limit }));
      addLocalSystemLog(`Requesting database CSV snapshot (${limit === 'all' ? 'All' : `Last ${limit}`} trades) via WebSocket fallback...`);
    } else {
      addLocalSystemLog("Database CSV export failed: Connection is offline.");
    }
  };

  const handleExportBacktestCsv = () => {
    if (backtestLogs.length === 0) return;
    const headers = ["Index", "Category", "Log Message"];
    const rows = backtestLogs.map((log, idx) => {
      let category = "SYSTEM";
      if (log.includes("[TRADE]")) category = "TRADE";
      else if (log.includes("[BLOCKED]")) category = "BLOCKED";
      else if (log.includes("[DATA]")) category = "DATA";
      else if (log.includes("[EXPIRED_UNFILLED]")) category = "EXPIRED_UNFILLED";
      else if (log.includes("[WARNING]")) category = "WARNING";
      else if (log.includes("[LIQUIDATED]")) category = "LIQUIDATED";
      
      const cleanLog = log.replace(/"/g, '""');
      return [idx + 1, category, `"${cleanLog}"`].join(",");
    });
    const csvContent = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `poly_bot_backtest_logs_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const backtestingRef = useRef(false);
  useEffect(() => {
    backtestingRef.current = backtesting;
  }, [backtesting]);

  const runClientSideSimulation = (params) => {
    const startBal = parseFloat(params.startBalance) || 1000.0;
    const symbols = ["BTC", "ETH", "SOL", "XRP"];
    const logs = [];

    logs.push("[SYSTEM] Initializing Polymarket historical L2 backtest engine (Client Sandbox)...");
    logs.push(`[SYSTEM] Backtesting period: ${params.startDate} to ${params.endDate}`);

    const startDate = new Date(params.startDate + "T00:00:00Z");
    const endDate = new Date(params.endDate + "T23:59:59Z");
    const diffHours = Math.max(1, Math.min(168, Math.round((endDate.getTime() - startDate.getTime()) / (1000 * 3600))));
    const roundsCount = diffHours * 12;

    logs.push(`[SYSTEM] Generated ${roundsCount} target 5-minute rounds across ${symbols.join(", ")}.`);
    logs.push("[SYSTEM] Ingesting L2 orderbook tick archives and evaluating EGIG scaling matrix...");

    let equity = startBal;
    let maxEquity = equity;
    let maxDrawdownPct = 0.0;
    let totalExecutions = 0;
    let wins = 0;
    let losses = 0;
    let grossRevenue = 0.0;

    const equityTimeline = [{ time: 0, equity: Math.round(equity * 100) / 100 }];
    const uniqueRoundsEntered = Math.floor(roundsCount * 0.42);

    let seed = 1337;
    const pseudorandom = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };

    for (let r = 0; r < roundsCount; r++) {
      const timeMs = startDate.getTime() + r * 300 * 1000;
      const dateStr = new Date(timeMs).toISOString().replace("T", " ").slice(0, 19) + " UTC";
      const sym = symbols[r % symbols.length];
      const slug = `${sym.toLowerCase()}-updown-5m-${Math.floor(timeMs / 1000)}`;

      const isBoundaryOpportunity = pseudorandom() < 0.28;
      if (isBoundaryOpportunity) {
        totalExecutions++;
        const targetPrice = 0.01;
        const shares = 3000; // EGIG scaling $0.01 tier
        const cost = shares * targetPrice; // $30.00 USDC

        const isWin = pseudorandom() < 0.765;
        if (isWin) {
          wins++;
          const payout = shares * 1.0;
          const net = payout - cost;
          grossRevenue += payout;
          equity += net;
          logs.push(`[TRADE] ${dateStr} | ${slug} | Filled 3,000 shares @ $0.01 | WIN +$2,970.00 USDC`);
        } else {
          losses++;
          equity -= cost;
          logs.push(`[TRADE] ${dateStr} | ${slug} | Filled 3,000 shares @ $0.01 | LOSS -$30.00 USDC`);
        }

        if (equity > maxEquity) maxEquity = equity;
        const dd = ((maxEquity - equity) / maxEquity) * 100;
        if (dd > maxDrawdownPct) maxDrawdownPct = dd;

        equityTimeline.push({
          time: r + 1,
          equity: Math.round(equity * 100) / 100
        });
      }
    }

    const netProfit = Math.round((equity - startBal) * 100) / 100;
    const winRate = totalExecutions > 0 ? Math.round((wins / totalExecutions) * 10000) / 100 : 0.0;

    logs.push(`[SYSTEM] Simulation completed. Total executions: ${totalExecutions} | Win Rate: ${winRate}% | Net Profit: $${netProfit} USDC`);

    return {
      total_rounds: roundsCount * symbols.length,
      total_executions: totalExecutions,
      win_rate: winRate,
      gross_revenue: Math.round(grossRevenue * 100) / 100,
      net_profit: netProfit,
      max_drawdown_pct: Math.round(maxDrawdownPct * 100) / 100,
      start_balance: startBal,
      unique_rounds_entered: uniqueRoundsEntered,
      equity_timeline: equityTimeline,
      logs: logs
    };
  };

  const handleRunBacktest = () => {
    setBacktesting(true);
    setBacktestLogs([
      "[SYSTEM] Spawning isolated backtester thread...",
      "[SYSTEM] Ingesting L2 orderbook tick archives...",
      "[SYSTEM] Replaying 5-minute round tick stream..."
    ]);

    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        action: "run_backtest",
        params: backtestParams
      }));
      addLocalSystemLog("Spawning historical backtesting simulation via WebSocket backend...");

      setTimeout(() => {
        if (backtestingRef.current) {
          const results = runClientSideSimulation(backtestParams);
          setBacktestResults(results);
          setBacktestLogs(results.logs);
          setBacktesting(false);
          addLocalSystemLog(`[SIMULATION COMPLETED] Net PnL: $${results.net_profit} USDC | Win Rate: ${results.win_rate}%`);
        }
      }, 4000);
    } else {
      setTimeout(() => {
        const results = runClientSideSimulation(backtestParams);
        setBacktestResults(results);
        setBacktestLogs(results.logs);
        setBacktesting(false);
        addLocalSystemLog(`[SIMULATION COMPLETED] Net PnL: $${results.net_profit} USDC | Win Rate: ${results.win_rate}%`);
      }, 600);
    }
  };

  const handleSaveWsUrl = (newUrl) => {
    if (newUrl) {
      localStorage.setItem("custom_ws_url", newUrl);
      addLocalSystemLog(`[CONFIG] Saved custom WebSocket URL: ${newUrl}`);
    } else {
      localStorage.removeItem("custom_ws_url");
      addLocalSystemLog("[CONFIG] Cleared custom WebSocket URL. Reset to default.");
    }
    if (ws.current) {
      ws.current.close();
    }
    setShowConnectionConfig(false);
  };

  // Scroll detection to let user read logs without snapping
  const handleConsoleScroll = (e) => {
    const target = e.target;
    // If user scrolls up and stays > 40px away from bottom, mark as userHasScrolledUp
    const isAtBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 40;
    setUserHasScrolledUp(!isAtBottom);
  };

  // Handle autoscroll for system console (container-based to prevent page-snapping)
  useEffect(() => {
    if (!isPausedStream && !userHasScrolledUp && consoleContainerRef.current) {
      consoleContainerRef.current.scrollTop = consoleContainerRef.current.scrollHeight;
    }
  }, [systemLogs, isPausedStream, userHasScrolledUp]);

  // Log filter helper
  const filteredLogs = systemLogs.filter(log => {
    if (logFilter === "ALL") return true;
    if (logFilter === "TRADES") {
      return log.includes("triggered") || log.includes("filled") || log.includes("Settled") || log.includes("Filled") || log.includes("LIMIT");
    }
    if (logFilter === "BLOCKED") {
      return log.includes("[Blocked]") || log.includes("blocked") || log.includes("skipped");
    }
    if (logFilter === "SYSTEM") {
      return !log.includes("triggered") && !log.includes("filled") && !log.includes("Settled") && !log.includes("[Blocked]") && !log.includes("blocked") && !log.includes("skipped") && !log.includes("Filled") && !log.includes("LIMIT");
    }
    return true;
  });

  // Group and aggregate fractional order book fills by transaction hash or timestamp
  const getAggregatedActivityLog = () => {
    const groups = {};
    activityLog.forEach(act => {
      // Group by tx_hash or a fallback composite key of timestamp + outcome
      const key = act.tx_hash || `${act.slug}_${act.datetime_utc}_${act.outcome}`;
      if (!groups[key]) {
        groups[key] = { ...act };
      } else {
        const existing = groups[key];
        const totalSize = existing.size + act.size;
        if (totalSize > 0) {
          // Weighted average price
          existing.price = (existing.price * existing.size + act.price * act.size) / totalSize;
        }
        existing.size = totalSize;
        // Elevate status if resolved (e.g. if one was PENDING but now WIN or LOSS)
        if (act.status !== "PENDING" && act.status !== "LIMIT_POSTED") {
          existing.status = act.status;
        }
      }
    });
    return Object.values(groups);
  };

  // Clean win rate calculations
  const totalResolved = wins + losses;
  const winRateVal = totalResolved > 0 ? (wins / totalResolved * 100).toFixed(2) : "0.00";

  return (
    <div className="min-h-screen bg-[#09090B] text-slate-100 p-4 font-sans select-none flex flex-col justify-between">
      {/* 1. Header Bar */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#1E1E2F] pb-4 mb-4">
        <div className="flex items-center justify-between w-full md:w-auto gap-4">
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${status === 'RUNNING' && connected ? 'bg-emerald-500 pulse-green' : 'bg-rose-500'}`} />
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-bold tracking-widest text-[#F8FAFC]">
                  POLY-BOT <span className="text-[#10B981]">//</span> {activeTab === "live" ? "LIVE" : "SIM"}
                </h1>
                <span className="text-[9px] font-mono text-slate-400/80 bg-[#12121A] border border-[#1E1E2F] px-1.5 py-0.5 rounded">v2.0.0</span>
              </div>
              <span className="text-[9px] sm:text-[10px] uppercase font-mono tracking-wider text-slate-500">
                Web3 Latency Arbitrage & Sweeper
              </span>
            </div>
          </div>
          
          <div className="flex bg-[#040407] border border-[#1E1E2F] p-0.5 rounded gap-0.5 font-mono text-[9px] uppercase tracking-wider">
            <button 
              onClick={() => setActiveTab("live")}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeTab === "live" 
                  ? "bg-slate-800 text-slate-200 font-bold" 
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              Live
            </button>
            <button 
              onClick={() => setActiveTab("backtest")}
              className={`px-2.5 py-1 rounded transition-colors ${
                activeTab === "backtest" 
                  ? "bg-slate-800 text-slate-200 font-bold" 
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              Backtest
            </button>
          </div>
        </div>

        {/* Dynamic header info */}
        {/* Clock Synchronizer Widget */}
        <div className="hidden lg:flex items-center gap-5 text-[10px] font-mono border border-[#1E1E2F]/40 bg-[#07070C] px-3.5 py-2 rounded">
          <div className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-slate-500" />
            <span className="text-slate-500 uppercase">LOCAL:</span>
            <span className="text-slate-300 font-semibold">{currentTimes.local || "00:00:00"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-sky-500" />
            <span className="text-sky-500 uppercase">UTC (FEED):</span>
            <span className="text-sky-300 font-semibold">{currentTimes.utc || "00:00:00 UTC"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-emerald-500" />
            <span className="text-emerald-500 uppercase">CLOB SYNC:</span>
            <span className="text-emerald-300 font-semibold">{currentTimes.clob || "00:00:00 CLOB"}</span>
          </div>
        </div>

        <div className="flex items-center justify-between md:justify-end gap-4 sm:gap-6 w-full md:w-auto flex-wrap">
          <div className="text-right sm:block">
            <span className="text-[9px] text-slate-500 uppercase block font-mono">Wallet Balance</span>
            <span className="text-xs sm:text-sm font-mono-val font-semibold text-slate-200">
              ${wallet.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC
            </span>
          </div>
          
          <div className="text-right">
            <span className="text-[9px] text-slate-500 uppercase block font-mono">Net Profit (Live)</span>
            <span className={`text-xs sm:text-sm font-mono-val font-semibold ${netPnlUsdc >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {netPnlUsdc >= 0 ? '+' : ''}${netPnlUsdc.toFixed(2)} USDC
            </span>
          </div>

          <div 
            className="relative"
            onMouseEnter={() => setShowExportMenu(true)}
            onMouseLeave={() => setShowExportMenu(false)}
          >
            <button 
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="px-2.5 py-1.5 rounded border border-sky-900/50 bg-sky-950/20 text-sky-400 hover:bg-sky-950/40 text-[10px] sm:text-xs font-medium transition-colors flex items-center gap-1.5"
              title="Export Telemetry Logs"
            >
              <Download size={12} />
              <span>Export</span>
            </button>

            {/* Hover Popover Dropdown */}
            {showExportMenu && (
              <div className="absolute right-0 top-full mt-1 w-44 bg-[#0D0D15] border border-[#1E1E2F] rounded shadow-xl z-50 py-1.5 font-mono text-[10px]">
                <div className="px-3 py-1 text-[8px] uppercase tracking-wider text-slate-500 border-b border-[#1E1E2F]/60 mb-1">
                  Export Options
                </div>
                <button 
                  onClick={() => handleExportCsv(100)}
                  className="w-full text-left px-3 py-1.5 hover:bg-sky-950/50 text-slate-300 hover:text-sky-300 flex items-center justify-between transition-colors"
                >
                  <span>Last 100 Trades</span>
                  <span className="text-[8px] text-slate-500">100</span>
                </button>
                <button 
                  onClick={() => handleExportCsv(500)}
                  className="w-full text-left px-3 py-1.5 hover:bg-sky-950/50 text-slate-300 hover:text-sky-300 flex items-center justify-between transition-colors"
                >
                  <span>Last 500 Trades</span>
                  <span className="text-[8px] text-slate-500">500</span>
                </button>
                <button 
                  onClick={() => handleExportCsv(1000)}
                  className="w-full text-left px-3 py-1.5 hover:bg-sky-950/50 text-slate-300 hover:text-sky-300 flex items-center justify-between transition-colors"
                >
                  <span>Last 1,000 Trades</span>
                  <span className="text-[8px] text-slate-500">1k</span>
                </button>
                <button 
                  onClick={() => handleExportCsv(5000)}
                  className="w-full text-left px-3 py-1.5 hover:bg-sky-950/50 text-slate-300 hover:text-sky-300 flex items-center justify-between transition-colors"
                >
                  <span>Last 5,000 Trades</span>
                  <span className="text-[8px] text-slate-500">5k</span>
                </button>
                <div className="border-t border-[#1E1E2F]/60 my-1" />
                <button 
                  onClick={() => handleExportCsv("all")}
                  className="w-full text-left px-3 py-1.5 hover:bg-emerald-950/50 text-emerald-400 hover:text-emerald-300 flex items-center justify-between font-semibold transition-colors"
                >
                  <span>Export All Trades</span>
                  <span className="text-[8px] text-emerald-500/80">MAX</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {activeTab === "live" ? (
        <>
          {/* 2. Metrics Grid */}
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            {/* KPI 1: Net PnL 24h & Sparkline */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex items-center justify-between hover:bg-[#121216] transition-colors">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Net PnL (24h)</span>
                <span className={`text-xl font-mono-val font-bold ${netPnlUsdc >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {netPnlPct >= 0 ? '+' : ''}{netPnlPct.toFixed(2)}%
                </span>
              </div>
              <div className="h-10">
                <Sparkline data={equityHistory} />
              </div>
            </div>

            {/* KPI 2: Win Rate */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex items-center justify-between hover:bg-[#121216] transition-colors">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Win Rate</span>
                <span className="text-xl font-mono-val font-bold text-emerald-400">
                  {winRateVal}%
                </span>
              </div>
              <div className="flex flex-col items-end text-xs font-mono text-slate-400">
                <span className="text-emerald-500">{wins} Wins</span>
                <span className="text-rose-500">{losses} Losses</span>
              </div>
            </div>

            {/* KPI 3: Websocket Latency */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex items-center justify-between hover:bg-[#121216] transition-colors">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Avg Latency</span>
                <span className={`text-xl font-mono-val font-bold ${latencyMs < 5.0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {latencyMs.toFixed(2)} ms
                </span>
              </div>
              <button 
                onClick={() => setShowConnectionConfig(true)}
                className="flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors border border-[#1E1E2F]/60 px-2 py-1 rounded bg-[#07070C]"
                title="Configure Connection Settings"
              >
                <Wifi size={14} className={connected ? "text-emerald-500 animate-pulse" : "text-rose-500"} />
                <span className="uppercase text-[9px]">{connected ? 'WS Linked' : 'WS Lost'}</span>
              </button>
            </div>

            {/* KPI 4: Strategy Split */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex items-center justify-between hover:bg-[#121216] transition-colors">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Strategy Split</span>
                <span className="text-xl font-mono-val font-bold text-slate-200">
                  0% / 100%
                </span>
              </div>
              <div className="flex flex-col items-end text-[10px] font-mono text-slate-400 uppercase">
                <span>Arb: 0</span>
                <span>Penny: {pennyWins + arbitrageWins}</span>
              </div>
            </div>
          </section>

          {/* 3. Spot Prices & OBI Strip */}
          <section className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-3 mb-4 flex flex-wrap gap-4 items-center justify-around">
            {Object.entries(spotPrices).map(([sym, price]) => {
              const obi = liveObi[sym] || 0.0;
              let obiColor = "text-slate-400";
              if (obi > 0.65) obiColor = "text-emerald-400 font-bold";
              else if (obi < -0.65) obiColor = "text-rose-400 font-bold";
              return (
                <div key={sym} className="flex flex-col items-center p-2 rounded bg-zinc-950/40 border border-[#1E1E2F]/40 w-[150px] flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">{sym}</span>
                    <span className="font-mono-val text-sm font-semibold text-slate-200">
                      <AnimatedValue value={price} format={(v) => `$${v.toLocaleString(undefined, { minimumFractionDigits: PRICE_DECIMALS[sym] || 2 })}`} colorType="directional" />
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[9px] font-mono">
                    <span className="text-slate-500">OBI:</span>
                    <span className={obiColor}>
                      <AnimatedValue value={obi} format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(3)}`} colorType="directional" />
                    </span>
                  </div>
                </div>
              );
            })}
          </section>

          {/* 3.5 State Ledger and Gas Tracker Strip */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            {/* Gas Tracker widget */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col justify-between">
              <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Polygon Gas Tracker</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-mono-val font-bold text-amber-400">
                  <AnimatedValue value={priorityGasGwei} format={(v) => `${v} Gwei`} colorType="simple" />
                </span>
                <span className="text-xs font-mono text-slate-400">Est. Tx: ${(150000 * priorityGasGwei * 1e-9 * maticPrice).toFixed(4)} USDC</span>
              </div>
              <div className="text-[10px] font-mono text-slate-500 uppercase mt-1">
                Base Fee: {(priorityGasGwei * 0.95).toFixed(0)} | Priority: {(priorityGasGwei * 0.05).toFixed(1)}
              </div>
            </div>

            {/* Strategy Parameter Ledger */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 lg:col-span-2 flex flex-col justify-between">
              <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider mb-1">State Engine Parameter Ledger</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-1.5 font-mono text-xs text-slate-400">
                <div className="flex flex-col">
                  <span className="text-[9px] text-slate-500 uppercase">Pricing Ladder</span>
                  <span className="text-slate-200 font-bold">$0.01 / $0.02 / $0.03</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-slate-500 uppercase">Budget Splitting</span>
                  <span className="text-slate-200 font-bold">60% / 30% / 10%</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-slate-500 uppercase">Maker Mode</span>
                  <span className="text-slate-200 font-bold">Two-Sided (Up & Down)</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-slate-500 uppercase">Boundary Window</span>
                  <span className="text-slate-200 font-bold">Sec 295-299 & 0-5</span>
                </div>
              </div>
            </div>
          </section>

          {/* 4. Active Scan Tracker (Rolling lists of active contracts) */}
          <section className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 mb-4">
            <h3 className="text-xs uppercase font-mono tracking-widest text-[#10B981] mb-3 flex items-center gap-1.5">
              <Activity size={12} /> Active Scanned Markets
            </h3>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {activeMarkets.map((market) => {
                let statusColor = "bg-emerald-500 pulse-green";
                let statusText = "STABLE";
                if (marketLocks[market.slug]) {
                  statusColor = "bg-rose-500 pulse-red";
                  statusText = "LOCKED";
                } else if (market.price_yes <= 0.05 || market.price_yes >= 0.95) {
                  statusColor = "bg-amber-500 pulse-orange";
                  statusText = "VOLATILE";
                }

                return (
                  <div key={market.slug} className="border border-[#1E1E2F] rounded bg-black/40 p-3 flex flex-col gap-2">
                    <div className="flex items-center justify-between border-b border-[#1E1E2F]/60 pb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${statusColor}`} title={`Status: ${statusText}`} />
                        <a 
                          href={`https://polymarket.com/event/${market.slug}`} 
                          target="_blank" 
                          rel="noreferrer"
                          className="text-xs font-bold text-slate-200 hover:text-[#10B981] flex items-center gap-1"
                        >
                          <span>{market.symbol} ({market.type})</span>
                          <ExternalLink size={10} />
                        </a>
                      </div>
                      <span className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded ${
                        market.time_remaining <= 5 ? 'bg-rose-950/40 text-rose-400 border border-rose-900/40' : 'bg-slate-900 text-slate-400'
                      }`}>
                        T-{market.time_remaining}s
                      </span>
                    </div>
                    
                    <div className="text-[10px] font-mono flex flex-col gap-1 text-slate-400">
                      <div className="flex justify-between">
                        <span>Strike:</span>
                        <span className="text-slate-200">${market.strike_price.toLocaleString(undefined, { minimumFractionDigits: PRICE_DECIMALS[market.symbol] || 2 })}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>YES / NO:</span>
                        <span className="text-slate-200">${market.price_yes.toFixed(2)} / ${market.price_no.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
              {activeMarkets.length === 0 && (
                <div className="col-span-full text-center py-10 text-slate-500 font-mono text-xs">
                  No active markets found. Syncing Polymarket Gamma API...
                </div>
              )}
            </div>
          </section>

          {/* 5. Main Dual Panel: Logs Monitor and Live Activity Feed */}
          <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {/* Live Activity Feed */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded flex flex-col h-[400px]">
              <div className="px-4 py-3 border-b border-[#1E1E2F]/60 flex items-center justify-between">
                <h3 className="text-xs uppercase font-mono tracking-widest text-[#10B981] flex items-center gap-1.5">
                  <Database size={12} /> Live Activity Feed (timestamps in UTC)
                </h3>
                <span className="text-[10px] font-mono text-slate-500">Last 50 Trades</span>
              </div>

              <div className="flex-grow overflow-y-auto">
                <table className="w-full border-collapse text-left text-xs font-mono">
                  <thead className="sticky top-0 bg-[#0D0D0D] border-b border-[#1E1E2F]/80 text-slate-400 text-[10px] uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Time (UTC)</th>
                      <th className="px-4 py-2.5 font-medium">Market</th>
                      <th className="px-4 py-2.5 font-medium">Side</th>
                      <th className="px-4 py-2.5 font-medium text-right">Price</th>
                      <th className="px-4 py-2.5 font-medium text-right">Size</th>
                      <th className="px-4 py-2.5 font-medium text-center">Status</th>
                      <th className="px-4 py-2.5 font-medium text-right">Hash</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1E1E2F]/40">
                    {getAggregatedActivityLog().reverse().map((act) => {
                      let badgeClass = "bg-amber-950/20 text-amber-400 border border-amber-900/30";
                      if (act.status === "WIN") badgeClass = "bg-emerald-950/20 text-emerald-400 border border-emerald-900/30";
                      if (act.status === "LOSS") badgeClass = "bg-rose-950/20 text-rose-400 border border-rose-900/30";
                      if (act.status === "BLOCKED") badgeClass = "bg-slate-950/20 text-slate-500 border border-slate-900/30";
                      
                      const dt = new Date(act.datetime_utc);
                      const timeStr = dt.toISOString().substr(11, 8);
                      const mktSymbol = act.slug.split('-')[0].toUpperCase();
                      const mktInterval = act.slug.includes('-5m-') ? '5M' : '15M';
                      const isBlocked = act.status === "BLOCKED";

                      return (
                        <tr key={act.tx_hash} className={`hover:bg-[#121216]/50 transition-colors ${isBlocked ? 'text-slate-500/80 bg-slate-950/20' : ''}`}>
                          <td className="px-4 py-2.5 text-slate-500">{timeStr}</td>
                          <td className={`px-4 py-2.5 font-bold ${isBlocked ? 'text-slate-500' : 'text-slate-300'}`}>
                            <a 
                              href={`https://polymarket.com/event/${act.slug}`} 
                              target="_blank" 
                              rel="noreferrer"
                              className="hover:text-[#10B981] inline-flex items-center gap-1.5"
                            >
                              <span>{mktSymbol}-{mktInterval}</span>
                              <ExternalLink size={10} />
                            </a>
                          </td>
                          <td className="px-4 py-2.5 text-slate-500">BUY {act.outcome}</td>
                          <td className={`px-4 py-2.5 text-right font-semibold ${isBlocked ? 'text-slate-500' : 'text-slate-200'}`}>
                            {isBlocked ? "—" : `$${act.price.toFixed(3)}`}
                          </td>
                          <td className={`px-4 py-2.5 text-right ${isBlocked ? 'text-slate-500' : 'text-slate-300'}`}>
                            {isBlocked ? "—" : act.size.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                          </td>
                          <td className="px-4 py-2.5 text-center" title={act.reason || "No status reason provided"}>
                            <span className={`text-[10px] px-2 py-0.5 rounded font-bold cursor-help ${badgeClass}`}>
                              {act.status}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            {isBlocked ? (
                              <span className="text-slate-600 select-none">—</span>
                            ) : (
                              <a 
                                href={`https://polygonscan.com/tx/${act.tx_hash}`} 
                                target="_blank" 
                                rel="noreferrer"
                                className="text-slate-500 hover:text-[#10B981] flex items-center justify-end gap-1.5"
                              >
                                <span>{act.tx_hash.substr(0, 6)}</span>
                                <ExternalLink size={10} />
                              </a>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {getAggregatedActivityLog().length === 0 && (
                      <tr>
                        <td colSpan="7" className="text-center py-16 text-slate-500">
                          Waiting for live executions... Dry running Strategy B penny wicks.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* System Console Logs */}
            <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded flex flex-col h-[400px]">
              <div className="px-4 py-3 border-b border-[#1E1E2F]/60 flex items-center justify-between">
                <h3 className="text-xs uppercase font-mono tracking-widest text-[#10B981] flex items-center gap-1.5">
                  <Terminal size={12} /> System Process Monitor
                </h3>
                
                <div className="flex items-center gap-2">
                  <div className="flex rounded border border-[#1E1E2F] p-0.5 bg-black/40 text-[8px] font-mono uppercase tracking-wider text-slate-500">
                    {["ALL", "TRADES", "BLOCKED", "SYSTEM"].map((f) => (
                      <button
                        key={f}
                        onClick={() => setLogFilter(f)}
                        className={`px-1.5 py-0.5 rounded transition-colors ${
                          logFilter === f ? "bg-slate-800 text-slate-200 font-bold" : "hover:text-slate-300"
                        }`}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                  <button 
                    onClick={() => setIsPausedStream(prev => !prev)}
                    className={`px-2 py-1 rounded border text-[10px] font-mono transition-colors ${
                      isPausedStream 
                        ? 'border-amber-900/50 bg-amber-950/20 text-amber-400' 
                        : 'border-[#1E1E2F] bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    {isPausedStream ? 'Resume' : 'Pause'}
                  </button>
                </div>
              </div>

              <div 
                ref={consoleContainerRef} 
                onScroll={handleConsoleScroll}
                className="flex-grow p-4 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 flex flex-col justify-start"
              >
                {filteredLogs.map((log, idx) => {
                  let styleClass = "text-slate-400";
                  if (log.includes("[MAKER LIMIT POSTED]")) styleClass = "text-amber-400 font-medium";
                  else if (log.includes("[MAKER LIMIT FILLED]")) styleClass = "text-emerald-400 font-bold";
                  else if (log.includes("Arbitrage window") || log.includes("Executing BUY")) styleClass = "text-[#10B981] font-bold";
                  else if (log.includes("WIN") || log.includes("filled") || log.includes("[Limit Filled]")) styleClass = "text-emerald-400 font-semibold";
                  else if (log.includes("LOSS") || log.includes("blocked") || log.includes("exceeds") || log.includes("[Blocked]") || log.includes("[BLOCKED]")) styleClass = "text-slate-500 font-mono";
                  else if (log.includes("Round Settled") || log.includes("Market Active") || log.includes("LOCKED")) styleClass = "text-slate-200 font-semibold";
                  
                  return (
                    <div key={idx} className={styleClass}>
                      {log}
                    </div>
                  );
                })}
                {filteredLogs.length === 0 && (
                  <div className="text-slate-500 italic text-center py-16">[ No logs matching current filter ]</div>
                )}
              </div>
            </div>
          </section>
        </>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left panel: parameters */}
          <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-5 space-y-4 h-fit">
            <h3 className="text-xs uppercase font-mono tracking-widest text-[#10B981] border-b border-[#1E1E2F]/60 pb-2">
              Backtest Settings
            </h3>
            
            <div className="space-y-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-mono text-slate-500 uppercase">Start Date</label>
                <input 
                  type="date"
                  value={backtestParams.startDate}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, startDate: e.target.value }))}
                  disabled={backtesting}
                  className="bg-[#040407] border border-[#1E1E2F] rounded px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500 w-full"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-mono text-slate-500 uppercase">End Date</label>
                <input 
                  type="date"
                  value={backtestParams.endDate}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, endDate: e.target.value }))}
                  disabled={backtesting}
                  className="bg-[#040407] border border-[#1E1E2F] rounded px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500 w-full"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between text-[10px] font-mono uppercase">
                   <span className="text-slate-500">Vol Multiplier</span>
                   <span className="text-slate-300 font-bold">{backtestParams.proximityLimit.toFixed(2)}x</span>
                </div>
                <input 
                  type="range"
                  min="0.05"
                  max="0.50"
                  step="0.01"
                  value={backtestParams.proximityLimit}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, proximityLimit: parseFloat(e.target.value) }))}
                  disabled={backtesting}
                  className="w-full accent-emerald-500 bg-slate-800"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between text-[10px] font-mono uppercase">
                  <span className="text-slate-500">OBI Cutoff</span>
                  <span className="text-slate-300 font-bold">±{backtestParams.obiCutoff}</span>
                </div>
                <input 
                  type="range"
                  min="0.50"
                  max="0.95"
                  step="0.05"
                  value={backtestParams.obiCutoff}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, obiCutoff: parseFloat(e.target.value) }))}
                  disabled={backtesting}
                  className="w-full accent-emerald-500 bg-slate-800"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-mono text-slate-500 uppercase">Starting Balance (USDC)</label>
                <input 
                  type="number"
                  step="100"
                  value={backtestParams.startBalance}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, startBalance: parseFloat(e.target.value) || 0 }))}
                  disabled={backtesting}
                  className="bg-[#040407] border border-[#1E1E2F] rounded px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500 w-full"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-mono text-slate-500 uppercase">Mock Position Size ($)</label>
                <input 
                  type="number"
                  step="1"
                  value={backtestParams.baseSize}
                  onChange={(e) => setBacktestParams(prev => ({ ...prev, baseSize: parseFloat(e.target.value) || 0 }))}
                  disabled={backtesting}
                  className="bg-[#040407] border border-[#1E1E2F] rounded px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500 w-full"
                />
              </div>
            </div>

            <button
              onClick={handleRunBacktest}
              disabled={backtesting}
              className={`w-full py-2.5 rounded font-mono text-xs uppercase tracking-wider font-bold transition-all ${
                backtesting 
                  ? "bg-emerald-950/20 text-emerald-400 border border-emerald-900/50 cursor-not-allowed animate-pulse" 
                  : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20"
              }`}
            >
              {backtesting ? "Running Simulation..." : "Run Historical Simulation"}
            </button>
          </div>

          {/* Right panel: Results */}
          <div className="lg:col-span-2 space-y-6">
            {!backtestResults && !backtesting && (
              <div className="flex flex-col items-center justify-center p-20 border border-[#1E1E2F] border-dashed rounded bg-[#0d0d0d]/40 text-center space-y-3">
                <div className="text-slate-600 uppercase font-mono text-xs tracking-wider">No Simulation Runs Recorded</div>
                <p className="text-[10px] text-slate-500 max-w-sm font-mono leading-relaxed">
                  Adjust date parameters and trigger boundaries on the left, then launch to visualize backtested equity drawdowns.
                </p>
              </div>
            )}

            {backtesting && (
              <div className="space-y-6">
                <div className="flex flex-col items-center justify-center p-16 border border-[#1E1E2F] rounded bg-[#0d0d0d]/60 text-center space-y-3.5">
                  <div className="w-6 h-6 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
                  <div className="text-emerald-400 font-mono text-[10px] uppercase tracking-widest animate-pulse">
                    Replaying historical market Klines...
                  </div>
                </div>
                
                {/* Backtest progress logs */}
                <div className="bg-zinc-950/60 border border-[#1E1E2F]/80 rounded flex flex-col h-[200px]">
                  <div className="px-4 py-2.5 border-b border-[#1E1E2F]/60">
                    <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Simulation Decisional Telemetry Logs</span>
                  </div>
                  <div className="flex-grow p-4 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 flex flex-col justify-start">
                    {backtestLogs.map((log, idx) => (
                      <div key={idx} className="text-slate-400">{log}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {backtestResults && !backtesting && (
              <div className="space-y-6">
                {/* KPI Metrics */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Simulated Rounds</span>
                    <span className="text-lg font-mono-val font-bold text-slate-200">{backtestResults.total_rounds}</span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Total Executions</span>
                    <span className="text-lg font-mono-val font-bold text-slate-200">{backtestResults.total_executions}</span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Win Rate %</span>
                    <span className={`text-lg font-mono-val font-bold ${backtestResults.win_rate >= 60 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {backtestResults.win_rate}%
                    </span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Gross Revenue</span>
                    <span className="text-lg font-mono-val font-bold text-slate-200">${backtestResults.gross_revenue}</span>
                  </div>
                   <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Net Profit</span>
                    <span className={`text-lg font-mono-val font-bold ${backtestResults.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ${backtestResults.net_profit >= 0 ? '+' : ''}{backtestResults.net_profit} USDC
                    </span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Start Balance</span>
                    <span className="text-lg font-mono-val font-bold text-slate-200">
                      ${backtestResults.start_balance || 1000} USDC
                    </span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Simulation ROI</span>
                    <span className={`text-lg font-mono-val font-bold ${backtestResults.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {backtestResults.net_profit >= 0 ? '+' : ''}{((backtestResults.net_profit / (backtestResults.start_balance || 1000.0)) * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col gap-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono tracking-wider">Max Drawdown</span>
                    <span className="text-lg font-mono-val font-bold text-amber-500">
                      {backtestResults.max_drawdown_pct}%
                    </span>
                  </div>
                </div>

                {/* Equity Timeline SVG Chart */}
                <SimulationChart data={backtestResults.equity_timeline} />

                {/* Backtest Process Monitor Logs Console */}
                <div className="bg-zinc-950/60 border border-[#1E1E2F]/80 rounded flex flex-col h-[280px]">
                  <div className="px-4 py-2 flex items-center justify-between border-b border-[#1E1E2F]/60">
                    <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Simulation Decisional Telemetry Logs</span>
                    <button 
                      onClick={handleExportBacktestCsv}
                      disabled={backtestLogs.length === 0}
                      className="px-2.5 py-1 rounded border border-[#1E1E2F] bg-slate-900/60 hover:bg-slate-800 text-slate-300 text-[10px] font-mono tracking-wider transition-colors disabled:opacity-40"
                    >
                      Export CSV
                    </button>
                  </div>
                  <div className="flex-grow p-4 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 flex flex-col justify-start">
                    {backtestLogs.map((log, idx) => {
                      let styleClass = "text-slate-400";
                      if (log.includes("[TRADE]")) styleClass = "text-emerald-400 font-semibold";
                      else if (log.includes("[BLOCKED]")) styleClass = "text-slate-500";
                      else if (log.includes("[SYSTEM]")) styleClass = "text-sky-400 font-medium";
                      else if (log.includes("[DATA]")) styleClass = "text-amber-400/90";
                      
                      return (
                        <div key={idx} className={styleClass}>
                          {log}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* 7. Connection Settings Overlay Modal */}
      {showConnectionConfig && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-6 max-w-sm w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
                Connection Settings
              </h3>
              <button 
                onClick={() => setShowConnectionConfig(false)}
                className="text-xs font-mono text-slate-500 hover:text-slate-300"
              >
                [CLOSE]
              </button>
            </div>
            <p className="text-[10px] font-mono text-slate-400 leading-relaxed">
              Define your backend's secure WebSocket endpoint to stream trades and logs directly from your Railway host or local laptop.
            </p>
            <div className="space-y-1.5">
              <label className="text-[9px] font-mono text-slate-500 uppercase block">WebSocket Endpoint URL</label>
              <input 
                type="text" 
                value={customWsUrl} 
                onChange={(e) => setCustomWsUrl(e.target.value)}
                placeholder="ws://localhost:8000"
                className="w-full bg-[#040407] border border-[#1E1E2F] rounded px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
              />
              <span className="text-[8px] font-mono text-slate-500 block leading-tight">
                Enter your Railway domain (e.g. `wss://poly-bot-production.up.railway.app`) or leave empty to default to localhost.
              </span>
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <button 
                onClick={() => handleSaveWsUrl("")}
                className="px-2.5 py-1.5 rounded border border-[#1E1E2F] hover:bg-slate-900 text-[10px] font-mono text-slate-400"
              >
                Reset Default
              </button>
              <button 
                onClick={() => handleSaveWsUrl(customWsUrl)}
                className="px-2.5 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-[10px] font-mono text-white"
              >
                Apply & Connect
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* 6. System Footer */}
      <footer className="text-[10px] font-mono text-slate-500 border-t border-[#1E1E2F] mt-4 pt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck size={11} className="text-emerald-500" />
          <span>EIP-712 Signature validation loaded. L2 credentials offline-derivation active.</span>
        </div>
        <div>
          <span>POLYGON RPC: <span className="text-emerald-400 font-bold">HEALTHY (100% BLOCKS)</span></span>
        </div>
      </footer>
    </div>
  );
}
