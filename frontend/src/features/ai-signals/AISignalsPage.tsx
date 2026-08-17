import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  TrendingUp, Activity, Search, Filter, 
  ArrowUpRight, ArrowDownRight, Clock, Target, Shield,
  Zap, Globe, DollarSign, BarChart3, X
} from 'lucide-react'
import { formatPrice as formatMarketPrice } from '@/shared/api/marketFormat'
import { API_BASE } from '@/shared/api/client'
import { TradingViewChart } from '@/shared/ui/TradingViewChart'

// Types
interface Signal {
  symbol: string
  label: string
  asset_class: string
  category: string
  sector: string
  region: string
  description: string
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence_pct: number
  uncertainty_pct: number
  bullish_strength: number
  bearish_strength: number
  volatility_label: string
  vol_spike_prob: number
  time_horizon: string
  trade_setup: {
    current_price: number
    entry_price: number
    stop_loss: number
    target_price: number
    risk_reward: number
    atr_pct: number
    max_position_pct: number
  }
  reliability: {
    historical_accuracy: number
    win_rate: number
    sharpe_ratio: number
    max_drawdown: number
  }
  triggering_event: {
    id: string
    title: string
    category: string
    severity: number
    ts: string
  }
  reasoning_summary: string
  reasoning_chain: Array<{
    step: number
    label: string
    description: string
    evidence: string
    phase: string
    confidence_contribution: number
  }>
  event_timeline: Array<{
    ts: string
    label: string
    detail: string
    phase: string
  }>
  related_assets: string[]
  generated_at: string
  price?: number | null
  live_change_pct?: number | null
  quote_timestamp?: string
  data_status?: string
  data_source?: string
  actionable?: boolean
}

interface MarketCategory {
  id: string
  name: string
  icon: React.ReactNode
  color: string
}

const MARKET_CATEGORIES: MarketCategory[] = [
  { id: 'all', name: 'All Markets', icon: <Globe className="w-4 h-4" />, color: '#00f2ff' },
  { id: 'crypto', name: 'Crypto', icon: <Zap className="w-4 h-4" />, color: '#f59e0b' },
  { id: 'stocks', name: 'Stocks', icon: <TrendingUp className="w-4 h-4" />, color: '#22c55e' },
  { id: 'etfs', name: 'ETFs', icon: <BarChart3 className="w-4 h-4" />, color: '#3b82f6' },
  { id: 'forex', name: 'Forex', icon: <DollarSign className="w-4 h-4" />, color: '#a855f7' },
  { id: 'commodities', name: 'Commodities', icon: <Activity className="w-4 h-4" />, color: '#ef4444' },
  { id: 'bonds', name: 'Bonds', icon: <Shield className="w-4 h-4" />, color: '#06b6d4' },
  { id: 'indices', name: 'Indices', icon: <Target className="w-4 h-4" />, color: '#ec4899' },
]

const CATEGORY_TO_ASSET_CLASS: Record<string, string> = {
  crypto: 'crypto',
  stocks: 'stock',
  etfs: 'etf',
  forex: 'forex',
  commodities: 'commodity',
  bonds: 'bond',
  indices: 'equity_index',
}

function marketClassForSignal(assetClass: string): string {
  return {
    stock: 'stocks', commodity: 'commodities', equity_index: 'indices',
    bond: 'bonds', etf: 'etfs', crypto: 'crypto', forex: 'forex',
  }[assetClass] || assetClass
}

function displayPrice(signal: Signal, value: number): string {
  if (!Number.isFinite(value) || value <= 0) return 'Unavailable'
  return formatMarketPrice(value, marketClassForSignal(signal.asset_class))
}

export function AISignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'confidence' | 'change' | 'volatility'>('confidence')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Fetch signals from backend
  const fetchSignals = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      const signalsResponse = await fetch(`${API_BASE}/signals/v2/all?limit=500`)

      if (!signalsResponse.ok) {
        throw new Error(`HTTP ${signalsResponse.status}: ${signalsResponse.statusText}`)
      }
      const signalData = await signalsResponse.json()
      const directSignals: Signal[] = Array.isArray(signalData?.signals) ? signalData.signals as Signal[] : []
      const mergedSignals = directSignals.sort((a, b) => {
        const aPriced = typeof a.price === 'number' && a.price > 0 ? 1 : 0
        const bPriced = typeof b.price === 'number' && b.price > 0 ? 1 : 0
        if (aPriced !== bPriced) return bPriced - aPriced
        return a.symbol.localeCompare(b.symbol)
      })

      setSignals(mergedSignals)
      setSelectedSignal(previous => previous
        ? mergedSignals.find(signal => signal.symbol === previous.symbol) ?? mergedSignals[0] ?? null
        : mergedSignals[0] ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch signals')
      console.error('Error fetching signals:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSignals()
    const interval = setInterval(fetchSignals, 10000) // Refresh every 10 seconds
    return () => clearInterval(interval)
  }, [fetchSignals])

  // Filter and sort signals
  const filteredSignals = signals
    .filter(signal => {
      const matchesCategory = selectedCategory === 'all' ||
        signal.category === selectedCategory ||
        signal.asset_class === CATEGORY_TO_ASSET_CLASS[selectedCategory]
      const matchesSearch = searchQuery === '' || 
        signal.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        signal.label.toLowerCase().includes(searchQuery.toLowerCase())
      return matchesCategory && matchesSearch
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'confidence':
          return b.confidence_pct - a.confidence_pct
        case 'change':
          const aChange = a.live_change_pct || 0
          const bChange = b.live_change_pct || 0
          return Math.abs(bChange) - Math.abs(aChange)
        case 'volatility':
          return b.vol_spike_prob - a.vol_spike_prob
        default:
          return 0
      }
    })

  if (loading && signals.length === 0) {
    return (
      <div className="min-h-screen bg-[#03060f] flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-12 h-12 text-[#00f2ff] animate-pulse mx-auto mb-4" />
          <p className="text-white/60 font-mono text-sm">Loading AI Signals...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#03060f] flex items-center justify-center">
        <div className="text-center max-w-md">
          <X className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400 font-mono text-sm mb-2">Error Loading Signals</p>
          <p className="text-white/40 font-mono text-xs">{error}</p>
          <button 
            onClick={fetchSignals}
            className="mt-4 px-4 py-2 bg-[#00f2ff]/10 border border-[#00f2ff]/30 rounded-lg text-[#00f2ff] font-mono text-xs hover:bg-[#00f2ff]/20 transition-all"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#03060f] flex">
      {/* Background grid */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(0, 242, 255, 0.03) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(0, 242, 255, 0.03) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
        }}
      />

      {/* Left Sidebar - Signal Feed */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ x: -400, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -400, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="w-96 h-screen bg-[#07091a]/95 border-r border-white/10 flex flex-col relative z-20"
          >
            {/* Header */}
            <div className="p-4 border-b border-white/10">
              <div className="flex items-center justify-between mb-4">
                <h1 className="text-lg font-bold text-white font-mono flex items-center gap-2">
                  <Activity className="w-5 h-5 text-[#00f2ff]" />
                  AI SIGNALS
                </h1>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1 hover:bg-white/10 rounded transition-colors"
                >
                  <X className="w-4 h-4 text-white/60" />
                </button>
              </div>

              {/* Search */}
              <div className="relative mb-4">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
                <input
                  type="text"
                  placeholder="Search assets..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-white placeholder-white/40 font-mono text-sm focus:outline-none focus:border-[#00f2ff]/50 transition-colors"
                />
              </div>

              {/* Category Filter */}
              <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                {MARKET_CATEGORIES.map(category => (
                  <button
                    key={category.id}
                    onClick={() => setSelectedCategory(category.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-mono text-xs whitespace-nowrap transition-all ${
                      selectedCategory === category.id
                        ? 'bg-[#00f2ff]/20 border border-[#00f2ff]/50 text-[#00f2ff]'
                        : 'bg-white/5 border border-white/10 text-white/60 hover:bg-white/10'
                    }`}
                    style={selectedCategory === category.id ? { borderColor: category.color } : {}}
                  >
                    {category.icon}
                    {category.name}
                  </button>
                ))}
              </div>

              {/* Sort */}
              <div className="flex items-center gap-2 mt-3">
                <Filter className="w-3 h-3 text-white/40" />
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 text-white/60 font-mono text-xs focus:outline-none focus:border-[#00f2ff]/50"
                >
                  <option value="confidence">Sort by Confidence</option>
                  <option value="change">Sort by Change</option>
                  <option value="volatility">Sort by Volatility</option>
                </select>
              </div>
            </div>

            {/* Signal List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {filteredSignals.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-white/40 font-mono text-sm">No signals found</p>
                </div>
              ) : (
                filteredSignals.map(signal => (
                  <SignalCard
                    key={signal.symbol}
                    signal={signal}
                    isSelected={selectedSignal?.symbol === signal.symbol}
                    onClick={() => setSelectedSignal(signal)}
                  />
                ))
              )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-white/10">
              <div className="flex items-center justify-between text-xs font-mono text-white/40">
                <span>{filteredSignals.length} signals</span>
                <span className="flex items-center gap-1">
                  <Activity className="w-3 h-3 text-[#00f2ff] animate-pulse" />
                  Auto-refresh 10s
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Sidebar Toggle Button */}
      {!sidebarOpen && (
        <motion.button
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          onClick={() => setSidebarOpen(true)}
          className="fixed left-4 top-4 z-30 p-2 bg-[#07091a]/95 border border-white/10 rounded-lg hover:bg-white/10 transition-all"
        >
          <Activity className="w-5 h-5 text-[#00f2ff]" />
        </motion.button>
      )}

      {/* Main Content - Signal Details */}
      <div className="flex-1 h-screen overflow-y-auto">
        {selectedSignal ? (
          <SignalDetails signal={selectedSignal} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-white/40 font-mono text-sm">Select a signal to view details</p>
          </div>
        )}
      </div>
    </div>
  )
}

function SignalCard({ signal, isSelected, onClick }: { signal: Signal, isSelected: boolean, onClick: () => void }) {
  const isBuy = signal.action === 'BUY'
  const isSell = signal.action === 'SELL'
  const color = isBuy ? '#22c55e' : isSell ? '#ef4444' : '#f59e0b'
  const price = signal.price || signal.trade_setup.current_price
  const change = signal.live_change_pct || 0

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className={`p-4 rounded-lg border cursor-pointer transition-all ${
        isSelected
          ? 'bg-[#00f2ff]/10 border-[#00f2ff]/30 shadow-[0_0_20px_rgba(0,242,255,0.1)]'
          : 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20'
      }`}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg font-bold font-mono text-white">{signal.symbol}</span>
            <span
              className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${
                isBuy ? 'bg-[#22c55e]/20 text-[#22c55e]' : isSell ? 'bg-[#ef4444]/20 text-[#ef4444]' : 'bg-[#f59e0b]/20 text-[#f59e0b]'
              }`}
            >
              {signal.action}
            </span>
          </div>
          <p className="text-xs text-white/60 font-mono">{signal.label}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold font-mono text-white">{displayPrice(signal, price)}</p>
          <p className={`text-xs font-mono flex items-center justify-end gap-1 ${change >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
            {change >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            {Math.abs(change).toFixed(2)}%
          </p>
          <p className="text-[9px] font-mono text-white/40 mt-1">
            {(signal.data_status || 'unavailable').toUpperCase()} · {signal.data_source || 'unknown'}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/40 font-mono">Confidence</span>
          <span className="text-white font-mono">{signal.confidence_pct.toFixed(1)}%</span>
        </div>
        <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${signal.confidence_pct}%`, backgroundColor: color }}
          />
        </div>

        <div className="flex items-center justify-between text-xs mt-2">
          <span className="text-white/40 font-mono">Volatility</span>
          <span className="text-white font-mono">{signal.volatility_label}</span>
        </div>
      </div>
    </motion.div>
  )
}

function SignalDetails({ signal }: { signal: Signal }) {
  const isBuy = signal.action === 'BUY'
  const isSell = signal.action === 'SELL'
  const price = signal.price || signal.trade_setup.current_price

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-3xl font-bold font-mono text-white">{signal.symbol}</h2>
            <span
              className={`px-3 py-1 rounded-lg text-sm font-bold font-mono ${
                isBuy ? 'bg-[#22c55e]/20 text-[#22c55e]' : isSell ? 'bg-[#ef4444]/20 text-[#ef4444]' : 'bg-[#f59e0b]/20 text-[#f59e0b]'
              }`}
            >
              {signal.action}
            </span>
          </div>
          <p className="text-white/60 font-mono">{signal.label}</p>
          <p className="text-white/40 font-mono text-sm mt-1">{signal.category} • {signal.region}</p>
        </div>
        <div className="text-right">
          <p className="text-4xl font-bold font-mono text-white">{displayPrice(signal, price)}</p>
          {signal.live_change_pct != null && (
            <p className={`text-lg font-mono flex items-center justify-end gap-1 ${signal.live_change_pct >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
              {signal.live_change_pct >= 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {Math.abs(signal.live_change_pct).toFixed(2)}%
            </p>
          )}
          <p className="text-xs font-mono text-white/40 mt-2">
            {(signal.data_status || 'unavailable').toUpperCase()} · {signal.data_source || 'unknown'} · {new Date(signal.quote_timestamp || signal.generated_at).toLocaleString()}
          </p>
        </div>
      </div>

      {/* Trade Setup */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <h3 className="text-lg font-bold font-mono text-white mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-[#00f2ff]" />
          TRADE SETUP
        </h3>
        <div className="grid grid-cols-4 gap-4">
          <TradeMetric label="Current Price" value={displayPrice(signal, signal.trade_setup.current_price)} />
          <TradeMetric label="Entry Price" value={displayPrice(signal, signal.trade_setup.entry_price)} />
          <TradeMetric label="Stop Loss" value={displayPrice(signal, signal.trade_setup.stop_loss)} color="#ef4444" />
          <TradeMetric label="Target Price" value={displayPrice(signal, signal.trade_setup.target_price)} color="#22c55e" />
          <TradeMetric label="Risk/Reward" value={signal.trade_setup.risk_reward.toFixed(2)} />
          <TradeMetric label="ATR %" value={`${(signal.trade_setup.atr_pct * 100).toFixed(2)}%`} />
          <TradeMetric label="Max Position" value={`${(signal.trade_setup.max_position_pct * 100).toFixed(1)}%`} />
          <TradeMetric label="Time Horizon" value={signal.time_horizon} />
        </div>
      </div>

      {/* Signal Strength */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white/5 border border-white/10 rounded-xl p-6">
          <h3 className="text-sm font-bold font-mono text-white mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#00f2ff]" />
            SIGNAL STRENGTH
          </h3>
          <div className="space-y-4">
            <StrengthBar label="Bullish" value={signal.bullish_strength} color="#22c55e" />
            <StrengthBar label="Bearish" value={signal.bearish_strength} color="#ef4444" />
            <StrengthBar label="Confidence" value={signal.confidence_pct / 100} color="#00f2ff" />
            <StrengthBar label="Uncertainty" value={signal.uncertainty_pct / 100} color="#f59e0b" />
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-6">
          <h3 className="text-sm font-bold font-mono text-white mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-[#00f2ff]" />
            RELIABILITY
          </h3>
          <div className="space-y-3">
            <ReliabilityMetric label="Historical Accuracy" value={`${(signal.reliability.historical_accuracy * 100).toFixed(1)}%`} />
            <ReliabilityMetric label="Win Rate" value={`${(signal.reliability.win_rate * 100).toFixed(1)}%`} />
            <ReliabilityMetric label="Sharpe Ratio" value={signal.reliability.sharpe_ratio.toFixed(2)} />
            <ReliabilityMetric label="Max Drawdown" value={`${(signal.reliability.max_drawdown * 100).toFixed(1)}%`} />
          </div>
        </div>
      </div>

      <TradingViewChart
        symbol={signal.symbol}
        label={signal.label}
        assetClass={signal.asset_class}
        category={signal.category}
      />

      {/* Triggering Event */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <h3 className="text-lg font-bold font-mono text-white mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-[#f59e0b]" />
          TRIGGERING EVENT
        </h3>
        <div className="space-y-3">
          <div>
            <p className="text-white/60 font-mono text-xs mb-1">Event</p>
            <p className="text-white font-mono">{signal.triggering_event.title}</p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-white/60 font-mono text-xs mb-1">Category</p>
              <p className="text-white font-mono text-sm">{signal.triggering_event.category.replace('_', ' ')}</p>
            </div>
            <div>
              <p className="text-white/60 font-mono text-xs mb-1">Severity</p>
              <p className="text-white font-mono text-sm">{(signal.triggering_event.severity * 100).toFixed(0)}%</p>
            </div>
            <div>
              <p className="text-white/60 font-mono text-xs mb-1">Time</p>
              <p className="text-white font-mono text-sm">{new Date(signal.triggering_event.ts).toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* AI Reasoning */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <h3 className="text-lg font-bold font-mono text-white mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-[#00f2ff]" />
          AI REASONING
        </h3>
        <p className="text-white/80 font-mono text-sm leading-relaxed mb-6">{signal.reasoning_summary}</p>
        
        <div className="space-y-4">
          {signal.reasoning_chain.map((step) => (
            <div key={step.step} className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#00f2ff]/10 border border-[#00f2ff]/30 flex items-center justify-center">
                <span className="text-[#00f2ff] font-mono text-xs font-bold">{step.step}</span>
              </div>
              <div className="flex-1">
                <p className="text-white font-mono text-sm font-semibold mb-1">{step.label}</p>
                <p className="text-white/60 font-mono text-xs mb-1">{step.description}</p>
                <p className="text-white/40 font-mono text-xs">{step.evidence}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Event Timeline */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <h3 className="text-lg font-bold font-mono text-white mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-[#00f2ff]" />
          EVENT TIMELINE
        </h3>
        <div className="space-y-4">
          {signal.event_timeline.map((event, index) => (
            <div key={index} className="flex gap-4">
              <div className="flex-shrink-0 w-2 h-2 rounded-full bg-[#00f2ff] mt-2" />
              <div className="flex-1">
                <p className="text-white font-mono text-sm font-semibold mb-1">{event.label}</p>
                <p className="text-white/60 font-mono text-xs mb-1">{event.detail}</p>
                <p className="text-white/40 font-mono text-xs">{new Date(event.ts).toLocaleString()}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Related Assets */}
      {signal.related_assets.length > 0 && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-6">
          <h3 className="text-lg font-bold font-mono text-white mb-4 flex items-center gap-2">
            <Globe className="w-5 h-5 text-[#00f2ff]" />
            RELATED ASSETS
          </h3>
          <div className="flex flex-wrap gap-2">
            {signal.related_assets.map(asset => (
              <span key={asset} className="px-3 py-1.5 bg-white/10 rounded-lg text-white font-mono text-xs">
                {asset}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TradeMetric({ label, value, color }: { label: string, value: string, color?: string }) {
  return (
    <div>
      <p className="text-white/40 font-mono text-xs mb-1">{label}</p>
      <p className="text-white font-mono text-lg font-semibold" style={color ? { color } : {}}>{value}</p>
    </div>
  )
}

function StrengthBar({ label, value, color }: { label: string, value: number, color: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-white/60 font-mono text-xs">{label}</span>
        <span className="text-white font-mono text-xs">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-2 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${value * 100}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

function ReliabilityMetric({ label, value }: { label: string, value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-white/60 font-mono text-xs">{label}</span>
      <span className="text-white font-mono text-sm font-semibold">{value}</span>
    </div>
  )
}
