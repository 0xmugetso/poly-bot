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
  Flame
} from 'lucide-react';

const PRICE_DECIMALS = { BTC: 1, ETH: 2, SOL: 2, XRP: 4, BNB: 2 };

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
    BTC: 67250.0, ETH: 3480.0, SOL: 142.50, XRP: 0.58, BNB: 585.0
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
    ws.current = new WebSocket("ws://localhost:8000");

    ws.current.onopen = () => {
      setConnected(true);
      addLocalSystemLog("WebSocket connected to POLY-BOT backend engine.");
    };

    ws.current.onmessage = (event) => {
      const data = jsonParse(event.data);
      if (!data) return;

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
      addLocalSystemLog("Connection closed. Retrying connection in 3 seconds...");
      setTimeout(connectWS, 3000);
    };
  };

  const jsonParse = (str) => {
    try { return JSON.parse(str); }
    catch (e) { return null; }
  };

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

  // Handle autoscroll for system console (container-based to prevent page-snapping)
  useEffect(() => {
    if (!isPausedStream && consoleContainerRef.current) {
      consoleContainerRef.current.scrollTop = consoleContainerRef.current.scrollHeight;
    }
  }, [systemLogs, isPausedStream]);

  // Log filter helper
  const filteredLogs = systemLogs.filter(log => {
    if (logFilter === "ALL") return true;
    if (logFilter === "TRADES") {
      return log.includes("triggered") || log.includes("filled") || log.includes("Settled") || log.includes("Filled");
    }
    if (logFilter === "BLOCKED") {
      return log.includes("[Blocked]") || log.includes("blocked") || log.includes("skipped");
    }
    if (logFilter === "SYSTEM") {
      return !log.includes("triggered") && !log.includes("filled") && !log.includes("Settled") && !log.includes("[Blocked]") && !log.includes("blocked") && !log.includes("skipped") && !log.includes("Filled");
    }
    return true;
  });

  // Clean win rate calculations
  const totalResolved = wins + losses;
  const winRateVal = totalResolved > 0 ? (wins / totalResolved * 100).toFixed(2) : "0.00";

  return (
    <div className="min-h-screen bg-[#09090B] text-slate-100 p-4 font-sans select-none flex flex-col justify-between">
      {/* 1. Header Bar */}
      <header className="flex items-center justify-between border-b border-[#1E1E2F] pb-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center">
            <span className={`w-3.5 h-3.5 rounded-full ${status === 'RUNNING' && connected ? 'bg-emerald-500 pulse-green' : 'bg-rose-500'}`} />
          </div>
          <div className="flex flex-col">
            <h1 className="text-lg font-bold tracking-widest text-[#F8FAFC]">
              POLY-BOT <span className="text-[#10B981]">//</span> LIVE
            </h1>
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500">
              Web3 Latency Arbitrage & Sweeper
            </span>
          </div>
        </div>

        {/* Dynamic header info */}
        <div className="flex items-center gap-6">
          <div className="text-right hidden sm:block">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Simulated Wallet Balance</span>
            <span className="text-base font-mono-val font-semibold text-slate-200">
              ${wallet.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC
            </span>
          </div>
          
          <div className="text-right">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Net Profit (Live)</span>
            <span className={`text-base font-mono-val font-semibold ${netPnlUsdc >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {netPnlUsdc >= 0 ? '+' : ''}${netPnlUsdc.toFixed(2)} USDC
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button 
              onClick={handleToggleStatus}
              className={`px-3 py-1.5 rounded border text-xs font-medium transition-colors flex items-center gap-1.5 ${
                status === 'RUNNING' 
                  ? 'border-rose-900/50 bg-rose-950/20 text-rose-400 hover:bg-rose-950/40' 
                  : 'border-emerald-900/50 bg-emerald-950/20 text-emerald-400 hover:bg-emerald-950/40'
              }`}
            >
              {status === 'RUNNING' ? <Pause size={13} /> : <Play size={13} />}
              {status === 'RUNNING' ? 'Pause Engine' : 'Resume Engine'}
            </button>
            
            <button 
              onClick={handleTriggerGas}
              className="px-3 py-1.5 rounded border border-amber-900/50 bg-amber-950/20 text-amber-400 hover:bg-amber-950/40 text-xs font-medium transition-colors flex items-center gap-1.5"
              title="Bump Gas Priority"
            >
              <Flame size={13} />
              <span>Optimized Gas</span>
            </button>
          </div>
        </div>
      </header>

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
          <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400">
            <Wifi size={14} className="text-emerald-500" />
            <span className="uppercase text-[10px]">{connected ? 'WS Linked' : 'WS Lost'}</span>
          </div>
        </div>

        {/* KPI 4: Strategy Split */}
        <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex items-center justify-between hover:bg-[#121216] transition-colors">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Strategy Split</span>
            <span className="text-xl font-mono-val font-bold text-slate-200">
              {arbitrageWins + pennyWins > 0 
                ? `${Math.round((arbitrageWins / (arbitrageWins + pennyWins)) * 100)}% / ${Math.round((pennyWins / (arbitrageWins + pennyWins)) * 100)}%`
                : "100% / 0%"
              }
            </span>
          </div>
          <div className="flex flex-col items-end text-[10px] font-mono text-slate-400 uppercase">
            <span>Arb: {arbitrageWins}</span>
            <span>Penny: {pennyWins}</span>
          </div>
        </div>
      </section>

      {/* 3. Spot Prices Strip */}
      <section className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-3 mb-4 flex flex-wrap gap-6 items-center justify-around">
        {Object.entries(spotPrices).map(([sym, price]) => (
          <div key={sym} className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">{sym}</span>
            <span className="font-mono-val text-sm font-semibold text-slate-200">
              ${price.toLocaleString(undefined, { minimumFractionDigits: PRICE_DECIMALS[sym] || 2 })}
            </span>
          </div>
        ))}
      </section>

      {/* 3.5 State Ledger and Gas Tracker Strip */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {/* Gas Tracker widget */}
        <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 flex flex-col justify-between">
          <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Polygon Gas Tracker</span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-2xl font-mono-val font-bold text-amber-400">{priorityGasGwei} Gwei</span>
            <span className="text-xs font-mono text-slate-400">Est. Tx: ${(150000 * priorityGasGwei * 1e-9 * maticPrice).toFixed(4)} USDC</span>
          </div>
          <div className="text-[10px] font-mono text-slate-500 uppercase mt-1">
            Matic Reference: ${maticPrice.toFixed(2)} USDC
          </div>
        </div>

        {/* State locks Ledger widget */}
        <div className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 lg:col-span-2 flex flex-col justify-between">
          <span className="text-[10px] text-slate-500 uppercase font-mono tracking-wider">Mutual Exclusion State Ledger</span>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(marketLocks).map(([slug, lockState]) => (
              <span key={slug} className="text-[10px] font-mono bg-rose-950/40 text-rose-400 border border-rose-900/50 px-2.5 py-1 rounded-full uppercase flex items-center gap-1.5 animate-pulse">
                <span className="w-1.5 h-1.5 bg-rose-500 rounded-full" />
                {slug.split('-')[0].toUpperCase()}: LOCKED (STRATEGY A)
              </span>
            ))}
            {restingLimitOrders.map((order) => (
              <span key={order.tx_hash} className="text-[10px] font-mono bg-blue-950/40 text-blue-400 border border-blue-900/50 px-2.5 py-1 rounded-full uppercase flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                {order.slug.split('-')[0].toUpperCase()}: LIMIT BUY {order.outcome} @ ${order.price}
              </span>
            ))}
            {Object.keys(marketLocks).length === 0 && restingLimitOrders.length === 0 && (
              <span className="text-xs font-mono text-slate-500 font-medium">
                No active market locks or resting orders. Safe execution mode active.
              </span>
            )}
          </div>
          <div className="text-[10px] font-mono text-slate-500 uppercase mt-1">
            Prevents dual-side Strategy A/B triggers on identical intervals.
          </div>
        </div>
      </section>

      {/* 4. Active Scan Tracker (Rolling lists of active contracts) */}
      <section className="bg-[#0D0D0D] border border-[#1E1E2F] rounded p-4 mb-4">
        <h3 className="text-xs uppercase font-mono tracking-widest text-[#10B981] mb-3 flex items-center gap-1.5">
          <Activity size={12} /> Active Scanned Markets
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
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
                    <span className="text-xs font-bold text-slate-200">{market.symbol} ({market.type})</span>
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
                    <span>YES (Up) Ask:</span>
                    <span className="text-[#10B981] font-semibold">${market.price_yes}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>NO (Down) Ask:</span>
                    <span className="text-rose-400 font-semibold">${market.price_no}</span>
                  </div>
                </div>
              </div>
            );
          })}
          {activeMarkets.length === 0 && (
            <div className="col-span-full text-center py-6 text-xs text-slate-500 font-mono">
              [ SCANNING POLYMARKET FOR ACTIVE ROUNDS... ]
            </div>
          )}
        </div>
      </section>

      {/* 5. Main Double Panel (Activity Feed + System Console) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-grow h-[460px]">
        {/* Left Panel: Live Activity Table */}
        <section className="bg-[#0D0D0D] border border-[#1E1E2F] rounded flex flex-col overflow-hidden">
          <div className="bg-black/40 border-b border-[#1E1E2F] px-4 py-3 flex items-center justify-between">
            <h2 className="text-xs uppercase font-mono tracking-widest text-[#F8FAFC]">Live Activity Feed</h2>
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
                {activityLog.slice().reverse().map((act) => {
                  let badgeClass = "bg-amber-950/20 text-amber-400 border border-amber-900/30";
                  if (act.status === "WIN") badgeClass = "bg-emerald-950/20 text-emerald-400 border border-emerald-900/30";
                  if (act.status === "LOSS") badgeClass = "bg-rose-950/20 text-rose-400 border border-rose-900/30";
                  
                  const dt = new Date(act.datetime_utc);
                  const timeStr = dt.toISOString().substr(11, 8);
                  const mktSymbol = act.slug.split('-')[0].toUpperCase();
                  const mktInterval = act.slug.includes('-5m-') ? '5M' : '15M';

                  return (
                    <tr key={act.tx_hash} className="hover:bg-[#121216]/50 transition-colors">
                      <td className="px-4 py-2.5 text-slate-500">{timeStr}</td>
                      <td className="px-4 py-2.5 text-slate-300 font-bold">{mktSymbol}-{mktInterval}</td>
                      <td className="px-4 py-2.5 text-slate-400">BUY {act.outcome}</td>
                      <td className="px-4 py-2.5 text-right font-semibold text-slate-200">${act.price.toFixed(3)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-300">{act.size.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${badgeClass}`}>
                          {act.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <a 
                          href={`https://polygonscan.com/tx/${act.tx_hash}`} 
                          target="_blank" 
                          rel="noreferrer"
                          className="text-slate-500 hover:text-[#10B981] flex items-center justify-end gap-1.5"
                        >
                          <span>{act.tx_hash.substr(0, 6)}</span>
                          <ExternalLink size={10} />
                        </a>
                      </td>
                    </tr>
                  );
                })}
                {activityLog.length === 0 && (
                  <tr>
                    <td colSpan="7" className="text-center py-16 text-slate-500">
                      [ WAITING FOR SYSTEM TRADING TRIGGERS... ]
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Right Panel: Glassmorphic System Console */}
        <section className="console-panel rounded flex flex-col overflow-hidden">
          <div className="bg-black/40 border-b border-[#1E1E2F] px-4 py-3 flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-xs uppercase font-mono tracking-widest text-[#10B981] flex items-center gap-1.5">
              <Cpu size={13} /> System Process Monitor
            </h2>
            <div className="flex items-center gap-2">
              <div className="flex items-center border border-[#1E1E2F] rounded overflow-hidden">
                {["ALL", "TRADES", "BLOCKED", "SYSTEM"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setLogFilter(f)}
                    className={`px-2 py-1 text-[9px] font-mono transition-colors ${
                      logFilter === f 
                        ? 'bg-[#10B981] text-black font-bold' 
                        : 'bg-slate-950 text-slate-400 hover:bg-slate-900 border-r border-[#1E1E2F]/45 last:border-0'
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

          <div ref={consoleContainerRef} className="flex-grow p-4 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 flex flex-col justify-start">
            {filteredLogs.map((log, idx) => {
              let styleClass = "text-slate-400";
              if (log.includes("Arbitrage window") || log.includes("Executing BUY")) styleClass = "text-[#10B981] font-bold";
              else if (log.includes("WIN") || log.includes("filled") || log.includes("[Limit Filled]")) styleClass = "text-emerald-400 font-semibold";
              else if (log.includes("LOSS") || log.includes("blocked") || log.includes("exceeds") || log.includes("[Blocked]")) styleClass = "text-rose-400";
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
        </section>
      </div>
      
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
