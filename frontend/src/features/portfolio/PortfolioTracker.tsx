/**
 * PortfolioTracker — Multi-asset portfolio tracking page.
 *
 * Features:
 *  - Browse ALL supported market assets from real backend API
 *  - Add/remove assets to portfolio with live price tracking
 *  - Real-time portfolio value calculations
 *  - Search, filter, and sort functionality
 *  - Professional dark fintech UI with animations
 */
import { useState, useMemo, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
    Briefcase, Plus, Trash2,
    Search, Filter, ArrowUpDown, PieChart,
    RefreshCw, AlertCircle, X, Activity, TrendingUp, TrendingDown, Shield
} from 'lucide-react'
import { useMarketsByClass } from '@/shared/api/hooks'
import { formatPrice, formatChange, formatVolume, sourceLabel, isPriced, dataStatusLabel, dataStatusColor } from '@/shared/api/marketFormat'

interface MarketAsset {
    symbol: string
    name?: string
    price: number
    change: number
    asset_class: string
    source?: string
    volume?: number
    high_24h?: number
    low_24h?: number
    open_24h?: number
    timestamp?: number
    data_status?: string
}

interface PortfolioHolding {
    symbol: string
    name?: string
    quantity: number
    avg_price: number
    current_price: number
    asset_class: string
}

type SortOption = 'symbol' | 'price' | 'change' | 'category'
type FilterCategory = 'all' | 'stocks' | 'crypto' | 'forex' | 'commodities' | 'bonds' | 'etfs' | 'indices'

const CATEGORY_COLORS: Record<string, string> = {
    stocks: 'bg-blue-500/20 border-blue-500/30 text-blue-300',
    crypto: 'bg-purple-500/20 border-purple-500/30 text-purple-300',
    forex: 'bg-green-500/20 border-green-500/30 text-green-300',
    commodities: 'bg-amber-500/20 border-amber-500/30 text-amber-300',
    bonds: 'bg-cyan-500/20 border-cyan-500/30 text-cyan-300',
    etfs: 'bg-pink-500/20 border-pink-500/30 text-pink-300',
    indices: 'bg-orange-500/20 border-orange-500/30 text-orange-300',
}

const CATEGORY_ACCENTS: Record<string, string> = {
    stocks: 'bg-blue-400',
    crypto: 'bg-purple-400',
    forex: 'bg-green-400',
    commodities: 'bg-amber-400',
    bonds: 'bg-cyan-400',
    etfs: 'bg-pink-400',
    indices: 'bg-orange-400',
}

const CATEGORY_LABELS: Record<string, string> = {
    stocks: 'Stocks',
    crypto: 'Crypto',
    forex: 'Forex',
    commodities: 'Commodities',
    bonds: 'Bonds',
    etfs: 'ETFs',
    indices: 'Indices',
}

function signedTone(value: number): string {
    if (value > 0) return 'text-emerald-400'
    if (value < 0) return 'text-red-400'
    return 'text-gray-400'
}

export function PortfolioTracker() {
    // Portfolio state
    const [portfolio, setPortfolio] = useState<PortfolioHolding[]>([])
    
    // UI state
    const [searchQuery, setSearchQuery] = useState('')
    const [selectedCategory, setSelectedCategory] = useState<FilterCategory>('all')
    const [sortBy, setSortBy] = useState<SortOption>('symbol')
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
    const { data: marketsData, isLoading, error, refetch } = useMarketsByClass(selectedCategory)
    
    // Flatten every asset class the API returned into a single array.
    // `unavailable` rows are counted separately rather than dropped silently, so
    // a provider outage is visible instead of looking like a shorter universe.
    const { allAssets, unavailableCount } = useMemo(() => {
        if (!marketsData?.data) return { allAssets: [] as MarketAsset[], unavailableCount: 0 }

        const assets: MarketAsset[] = []
        let unavailable = 0
        const categories = ['stocks', 'crypto', 'forex', 'commodities', 'bonds', 'etfs', 'indices'] as const
        // `/markets/all` returns an object keyed by class; `/markets/{class}` returns an array.
        const isSingleMarket = Array.isArray(marketsData.data)
        const marketData: Record<string, any[]> = isSingleMarket
            ? { [marketsData.asset_class ?? selectedCategory]: marketsData.data }
            : marketsData.data

        categories.forEach(category => {
            const items = marketData[category] || []
            items.forEach((item: any) => {
                if (!item?.symbol) return
                if (!isPriced(item)) {
                    unavailable += 1
                    return
                }
                assets.push({
                    symbol: item.symbol,
                    name: item.name || item.symbol,
                    price: item.price,
                    change: typeof item.change === 'number' ? item.change : 0,
                    asset_class: item.asset_class || category,
                    source: item.source,
                    volume: item.volume,
                    high_24h: item.high_24h,
                    low_24h: item.low_24h,
                    open_24h: item.open_24h,
                    timestamp: item.timestamp,
                    data_status: item.data_status,
                })
            })
        })

        return { allAssets: assets, unavailableCount: unavailable }
    }, [marketsData, selectedCategory])

    // Per-class counts for the filter chips
    const countsByCategory = useMemo(() => {
        const counts: Record<string, number> = {}
        allAssets.forEach(a => { counts[a.asset_class] = (counts[a.asset_class] || 0) + 1 })
        return counts
    }, [allAssets])

    const marketBreadth = useMemo(() => {
        const advancing = allAssets.filter(asset => asset.change > 0).length
        const declining = allAssets.filter(asset => asset.change < 0).length
        const delayed = allAssets.filter(asset => asset.data_status && asset.data_status !== 'live').length

        return {
            advancing,
            declining,
            delayed,
            priced: allAssets.length,
        }
    }, [allAssets])

    // Filter and sort assets
    const filteredAssets = useMemo(() => {
        let filtered = allAssets
        
        // Category filter
        if (selectedCategory !== 'all') {
            filtered = filtered.filter(asset => asset.asset_class === selectedCategory)
        }
        
        // Search filter
        if (searchQuery) {
            const query = searchQuery.toLowerCase()
            filtered = filtered.filter(asset =>
                asset.symbol.toLowerCase().includes(query) ||
                (asset.name && asset.name.toLowerCase().includes(query))
            )
        }
        
        // Sorting (copy first — `filtered` may still alias the memoized array)
        filtered = [...filtered].sort((a, b) => {
            let comparison = 0
            switch (sortBy) {
                case 'symbol':
                    comparison = a.symbol.localeCompare(b.symbol)
                    break
                case 'price':
                    comparison = a.price - b.price
                    break
                case 'change':
                    comparison = a.change - b.change
                    break
                case 'category':
                    comparison = a.asset_class.localeCompare(b.asset_class)
                    break
            }
            return sortOrder === 'asc' ? comparison : -comparison
        })
        
        return filtered
    }, [allAssets, selectedCategory, searchQuery, sortBy, sortOrder])
    
    // Portfolio calculations
    const portfolioStats = useMemo(() => {
        const totalValue = portfolio.reduce((sum, holding) => 
            sum + (holding.quantity * holding.current_price), 0
        )
        
        const totalCost = portfolio.reduce((sum, holding) => 
            sum + (holding.quantity * holding.avg_price), 0
        )
        
        const totalPnL = totalValue - totalCost
        const totalPnLPercent = totalCost > 0 ? (totalPnL / totalCost) * 100 : 0
        
        // Asset allocation
        const allocation = portfolio.map(holding => ({
            symbol: holding.symbol,
            name: holding.name,
            value: holding.quantity * holding.current_price,
            percentage: totalValue > 0 ? ((holding.quantity * holding.current_price) / totalValue) * 100 : 0,
            asset_class: holding.asset_class,
        }))
        
        return {
            totalValue,
            totalCost,
            totalPnL,
            totalPnLPercent,
            allocation,
            assetCount: portfolio.length,
        }
    }, [portfolio])

    const topAllocation = useMemo(
        () => [...portfolioStats.allocation].sort((a, b) => b.value - a.value).slice(0, 6),
        [portfolioStats.allocation]
    )
    
    // Add asset to portfolio
    const addAsset = useCallback((asset: MarketAsset) => {
        const existing = portfolio.find(h => h.symbol === asset.symbol)
        if (existing) {
            // Increase quantity
            setPortfolio(prev => prev.map(h => 
                h.symbol === asset.symbol
                    ? { ...h, quantity: h.quantity + 1, current_price: asset.price }
                    : h
            ))
        } else {
            // Add new holding
            setPortfolio(prev => [...prev, {
                symbol: asset.symbol,
                name: asset.name,
                quantity: 1,
                avg_price: asset.price,
                current_price: asset.price,
                asset_class: asset.asset_class,
            }])
        }
    }, [portfolio])
    
    // Remove asset from portfolio
    const removeAsset = useCallback((symbol: string) => {
        setPortfolio(prev => prev.filter(h => h.symbol !== symbol))
    }, [])
    
    // Update portfolio prices when market data changes
    const updatePortfolioPrices = useCallback(() => {
        if (!allAssets.length) return
        
        setPortfolio(prev => prev.map(holding => {
            const asset = allAssets.find(a => a.symbol === holding.symbol)
            if (asset) {
                return { ...holding, current_price: asset.price }
            }
            return holding
        }))
    }, [allAssets])
    
    // Auto-update portfolio prices when market data refreshes
    useEffect(() => {
        updatePortfolioPrices()
    }, [allAssets, updatePortfolioPrices])
    
    // Handle sort change
    const handleSort = (option: SortOption) => {
        if (sortBy === option) {
            setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(option)
            setSortOrder('asc')
        }
    }
    
    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-full p-6 text-center gap-4 font-mono">
                <AlertCircle className="w-12 h-12 text-red-400" />
                <div>
                    <h3 className="text-base font-bold text-white mb-2">Data Temporarily Unavailable</h3>
                    <p className="text-sm text-gray-400 max-w-md">
                        Unable to fetch market data. Please check your connection and try again.
                    </p>
                </div>
                <button
                    onClick={() => refetch()}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-xs hover:bg-white/20 transition-all"
                >
                    <RefreshCw className="w-4 h-4" />
                    Retry
                </button>
            </div>
        )
    }
    
    return (
        <div className="h-full flex flex-col bg-[#03060f] text-white">
            {/* Header */}
            <div className="shrink-0 border-b border-white/10 bg-[#07091a]/80 backdrop-blur-xl">
                <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/15 bg-white/5 shadow-[0_0_18px_rgba(0,242,255,0.08)]">
                            <Briefcase className="h-5 w-5 text-[#00f2ff]" />
                        </div>
                        <div className="min-w-0">
                            <div className="flex items-center gap-2">
                                <h1 className="text-sm font-bold tracking-widest text-white uppercase">Portfolio Tracker</h1>
                                <span className="hidden sm:inline-flex rounded border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-300">
                                    Live
                                </span>
                            </div>
                            <p className="text-[10px] font-mono text-gray-500">
                                Multi-asset exposure, live pricing, and unrealized P/L
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 sm:flex sm:items-center">
                        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
                            <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-gray-500">
                                <Activity className="h-3 w-3" />
                                Priced
                            </div>
                            <div className="mt-1 font-mono text-xs text-white">
                                {marketBreadth.priced}
                                {unavailableCount > 0 && (
                                    <span className="ml-1 text-[10px] text-amber-400" title="Symbols the upstream providers could not price right now">
                                        / {unavailableCount} unavailable
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
                            <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-gray-500">
                                <TrendingUp className="h-3 w-3" />
                                Breadth
                            </div>
                            <div className="mt-1 flex items-center gap-2 font-mono text-xs">
                                <span className="text-emerald-400">{marketBreadth.advancing} up</span>
                                <span className="text-red-400">{marketBreadth.declining} down</span>
                            </div>
                        </div>
                        <button
                            onClick={() => refetch()}
                            className="col-span-2 flex h-10 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 text-[10px] font-semibold uppercase tracking-wider text-gray-300 transition-all hover:border-[#00f2ff]/35 hover:bg-[#00f2ff]/10 hover:text-white sm:col-span-1"
                            title="Refresh prices"
                        >
                            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                            Refresh
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="min-h-0 flex-1 overflow-y-auto xl:grid xl:grid-cols-[minmax(0,1fr)_420px] xl:overflow-hidden">
                {/* Left Panel - Market Asset List */}
                <div className="min-h-[560px] min-w-0 border-white/10 xl:flex xl:min-h-0 xl:flex-col xl:border-r">
                    {/* Search and Filters */}
                    <div className="border-b border-white/10 bg-[#050817]/80 p-4">
                        <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-start">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                                <input
                                    type="text"
                                    placeholder="Search assets..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="h-10 w-full rounded-lg border border-white/10 bg-[#07091a]/90 pl-10 pr-10 text-xs text-white placeholder-gray-600 transition-colors focus:border-[#00f2ff]/50 focus:outline-none"
                                />
                                {searchQuery && (
                                    <button
                                        onClick={() => setSearchQuery('')}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 transition-colors hover:text-white"
                                        title="Clear search"
                                    >
                                        <X className="h-4 w-4" />
                                    </button>
                                )}
                            </div>

                            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                                <Filter className="h-4 w-4 text-gray-600" />
                                {(['all', 'stocks', 'crypto', 'forex', 'commodities', 'bonds', 'etfs', 'indices'] as FilterCategory[]).map(category => {
                                    const count = category === 'all' ? allAssets.length : countsByCategory[category]
                                    const active = selectedCategory === category
                                    return (
                                        <button
                                            key={category}
                                            onClick={() => setSelectedCategory(category)}
                                            className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[10px] font-semibold transition-all ${
                                                active
                                                    ? 'border-[#00f2ff]/35 bg-[#00f2ff]/10 text-[#00f2ff]'
                                                    : 'border-white/10 bg-white/[0.03] text-gray-400 hover:border-white/20 hover:bg-white/8 hover:text-white'
                                            }`}
                                        >
                                            {category !== 'all' && (
                                                <span className={`h-1.5 w-1.5 rounded-full ${CATEGORY_ACCENTS[category]}`} />
                                            )}
                                            {category === 'all' ? 'All' : CATEGORY_LABELS[category]}
                                            {count ? <span className="text-white/35">{count}</span> : null}
                                        </button>
                                    )
                                })}
                            </div>
                        </div>

                        <div className="mt-3 flex flex-wrap items-center gap-2">
                            <ArrowUpDown className="h-4 w-4 text-gray-600" />
                            {(['symbol', 'price', 'change', 'category'] as SortOption[]).map(option => (
                                <button
                                    key={option}
                                    onClick={() => handleSort(option)}
                                    className={`h-8 rounded-lg border px-3 text-[10px] font-semibold capitalize transition-all ${
                                        sortBy === option
                                            ? 'border-white/25 bg-white/10 text-white'
                                            : 'border-white/10 bg-white/[0.03] text-gray-500 hover:border-white/20 hover:text-gray-200'
                                    }`}
                                >
                                    {option}
                                    {sortBy === option && (
                                        <span className="ml-1 text-[#00f2ff]">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                                    )}
                                </button>
                            ))}
                            {marketBreadth.delayed > 0 && (
                                <span className="ml-auto text-[10px] font-mono text-amber-400/80">
                                    {marketBreadth.delayed} delayed/reference
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Asset List */}
                    <div className="min-h-0 flex-1 overflow-y-auto p-4">
                        {isLoading ? (
                            <div className="flex items-center justify-center py-12 text-xs text-gray-500">
                                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                                Loading market data...
                            </div>
                        ) : filteredAssets.length === 0 ? (
                            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-white/10 py-14 text-center text-xs text-gray-500">
                                <Search className="mb-3 h-8 w-8 opacity-50" />
                                <p className="font-semibold text-gray-400">No assets found</p>
                                <p className="mt-1 text-[10px] text-gray-600">Adjust the search or market filter.</p>
                            </div>
                        ) : (
                            <div className="grid gap-2">
                                <AnimatePresence mode="popLayout">
                                    {filteredAssets.map(asset => (
                                        <motion.div
                                            key={asset.symbol}
                                            initial={{ opacity: 0, y: 8 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0, y: -8 }}
                                            transition={{ duration: 0.15 }}
                                            className="group relative overflow-hidden rounded-lg border border-white/8 bg-[#07091a]/75 p-3 transition-all hover:border-[#00f2ff]/25 hover:bg-white/[0.06]"
                                        >
                                            <div className={`absolute left-0 top-0 h-full w-0.5 ${asset.change >= 0 ? 'bg-emerald-400' : 'bg-red-400'}`} />
                                            <div className="flex items-center justify-between gap-3 pl-2">
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="font-mono text-sm font-bold text-white">{asset.symbol}</span>
                                                        <span className={`rounded border px-2 py-0.5 text-[9px] font-semibold ${CATEGORY_COLORS[asset.asset_class] || 'border-white/10 bg-white/5 text-gray-300'}`}>
                                                            {CATEGORY_LABELS[asset.asset_class] || asset.asset_class}
                                                        </span>
                                                        {asset.data_status && asset.data_status !== 'live' && (
                                                            <span className={`text-[8px] font-semibold uppercase ${dataStatusColor(asset.data_status)}`}>
                                                                {dataStatusLabel(asset.data_status)}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                                                        {asset.name && asset.name !== asset.symbol && (
                                                            <span className="max-w-[320px] truncate text-[10px] text-gray-500">{asset.name}</span>
                                                        )}
                                                        {asset.source && (
                                                            <span className="text-[9px] text-gray-600" title={`Priced by ${asset.source}`}>
                                                                {sourceLabel(asset.source)}
                                                            </span>
                                                        )}
                                                        {formatVolume(asset.volume) && (
                                                            <span className="hidden text-[9px] text-gray-600 lg:inline">
                                                                vol {formatVolume(asset.volume)}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                <div className="flex shrink-0 items-center gap-3">
                                                    <div className="text-right">
                                                        <p className="font-mono text-sm font-semibold text-white">
                                                            {formatPrice(asset.price, asset.asset_class)}
                                                        </p>
                                                        <p className={`font-mono text-[10px] ${signedTone(asset.change)}`}>
                                                            {formatChange(asset.change)}
                                                        </p>
                                                    </div>
                                                    <button
                                                        onClick={() => addAsset(asset)}
                                                        className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#00f2ff]/25 bg-[#00f2ff]/10 text-[#00f2ff] transition-all hover:border-[#00f2ff]/50 hover:bg-[#00f2ff]/20"
                                                        title="Add to portfolio"
                                                    >
                                                        <Plus className="h-4 w-4" />
                                                    </button>
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </AnimatePresence>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Panel - Portfolio */}
                <div className="min-h-[560px] min-w-0 border-t border-white/10 bg-[#050817]/75 xl:flex xl:min-h-0 xl:flex-col xl:border-t-0">
                    {/* Portfolio Header */}
                    <div className="border-b border-white/10 p-4">
                        <div className="mb-4 flex items-center gap-2">
                            <PieChart className="h-4 w-4 text-[#00f2ff]" />
                            <h2 className="text-xs font-bold uppercase tracking-widest text-white">My Portfolio</h2>
                            <span className="ml-auto rounded border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] text-gray-500">
                                {portfolioStats.assetCount} assets
                            </span>
                        </div>

                        <div className="rounded-lg border border-[#00f2ff]/20 bg-[#00f2ff]/[0.06] p-4">
                            <p className="mb-1 text-[9px] uppercase tracking-widest text-gray-500">Total Value</p>
                            <p className="font-mono text-2xl font-bold text-white">
                                ${portfolioStats.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </p>
                            <div className="mt-3 grid grid-cols-2 gap-2">
                                <div className="rounded-lg border border-white/10 bg-[#03060f]/70 p-3">
                                    <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-gray-500">
                                        {portfolioStats.totalPnL >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                                        Total P/L
                                    </div>
                                    <p className={`mt-1 font-mono text-sm font-bold ${signedTone(portfolioStats.totalPnL)}`}>
                                        {portfolioStats.totalPnL >= 0 ? '+' : ''}${portfolioStats.totalPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-white/10 bg-[#03060f]/70 p-3">
                                    <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest text-gray-500">
                                        <Shield className="h-3 w-3" />
                                        P/L %
                                    </div>
                                    <p className={`mt-1 font-mono text-sm font-bold ${signedTone(portfolioStats.totalPnLPercent)}`}>
                                        {portfolioStats.totalPnLPercent >= 0 ? '+' : ''}{portfolioStats.totalPnLPercent.toFixed(2)}%
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Asset Allocation */}
                    {topAllocation.length > 0 && (
                        <div className="border-b border-white/10 p-4">
                            <div className="mb-3 flex items-center justify-between">
                                <p className="text-[10px] uppercase tracking-widest text-gray-500">Asset Allocation</p>
                                <span className="text-[9px] text-gray-600">Top {topAllocation.length}</span>
                            </div>
                            <div className="mb-3 flex h-2 overflow-hidden rounded-full bg-gray-900">
                                {topAllocation.map(item => (
                                    <div
                                        key={item.symbol}
                                        className={`${CATEGORY_ACCENTS[item.asset_class] || 'bg-gray-500'}`}
                                        style={{ width: `${Math.max(item.percentage, 2)}%` }}
                                        title={`${item.symbol}: ${item.percentage.toFixed(1)}%`}
                                    />
                                ))}
                            </div>
                            <div className="space-y-2">
                                {topAllocation.map(item => (
                                    <div key={item.symbol} className="flex items-center gap-2">
                                        <span className={`h-2 w-2 rounded-full ${CATEGORY_ACCENTS[item.asset_class] || 'bg-gray-500'}`} />
                                        <span className="w-16 truncate font-mono text-[10px] text-gray-300">{item.symbol}</span>
                                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-900">
                                            <div
                                                className={`h-full rounded-full ${CATEGORY_ACCENTS[item.asset_class] || 'bg-gray-500'}`}
                                                style={{ width: `${item.percentage}%` }}
                                            />
                                        </div>
                                        <span className="w-12 text-right font-mono text-[10px] text-gray-400">{item.percentage.toFixed(1)}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Portfolio Holdings */}
                    <div className="min-h-0 flex-1 overflow-y-auto p-4">
                        {portfolio.length === 0 ? (
                            <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-6 text-center text-xs text-gray-500">
                                <Briefcase className="mb-3 h-9 w-9 text-gray-600" />
                                <p className="font-semibold text-gray-300">Your portfolio is empty</p>
                                <p className="mt-1 text-[10px] text-gray-600">Add assets from the market list to start tracking exposure.</p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <AnimatePresence mode="popLayout">
                                    {portfolio.map(holding => {
                                        const currentValue = holding.quantity * holding.current_price
                                        const costBasis = holding.quantity * holding.avg_price
                                        const pnl = currentValue - costBasis
                                        const pnlPercent = costBasis > 0 ? (pnl / costBasis) * 100 : 0

                                        return (
                                            <motion.div
                                                key={holding.symbol}
                                                initial={{ opacity: 0, x: 16 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                exit={{ opacity: 0, x: -16 }}
                                                transition={{ duration: 0.15 }}
                                                className="group rounded-lg border border-white/10 bg-[#07091a]/85 p-3 transition-all hover:border-white/20"
                                            >
                                                <div className="mb-3 flex items-start justify-between gap-2">
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="font-mono text-sm font-bold text-white">{holding.symbol}</span>
                                                            <span className={`rounded border px-2 py-0.5 text-[9px] font-semibold ${CATEGORY_COLORS[holding.asset_class] || 'border-white/10 bg-white/5 text-gray-300'}`}>
                                                                {CATEGORY_LABELS[holding.asset_class] || holding.asset_class}
                                                            </span>
                                                        </div>
                                                        {holding.name && holding.name !== holding.symbol && (
                                                            <p className="mt-1 truncate text-[10px] text-gray-500">{holding.name}</p>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={() => removeAsset(holding.symbol)}
                                                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-gray-600 opacity-100 transition-all hover:bg-red-500/10 hover:text-red-400 sm:opacity-0 sm:group-hover:opacity-100"
                                                        title="Remove from portfolio"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                    </button>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2 text-[10px]">
                                                    <div className="rounded border border-white/5 bg-white/[0.03] p-2">
                                                        <p className="text-gray-500">Quantity</p>
                                                        <p className="mt-0.5 font-mono text-white">{holding.quantity}</p>
                                                    </div>
                                                    <div className="rounded border border-white/5 bg-white/[0.03] p-2">
                                                        <p className="text-gray-500">Avg Price</p>
                                                        <p className="mt-0.5 font-mono text-white">{formatPrice(holding.avg_price, holding.asset_class)}</p>
                                                    </div>
                                                    <div className="rounded border border-white/5 bg-white/[0.03] p-2">
                                                        <p className="text-gray-500">Current</p>
                                                        <p className="mt-0.5 font-mono text-white">{formatPrice(holding.current_price, holding.asset_class)}</p>
                                                    </div>
                                                    <div className="rounded border border-white/5 bg-white/[0.03] p-2">
                                                        <p className="text-gray-500">Value</p>
                                                        <p className="mt-0.5 font-mono text-white">${currentValue.toFixed(2)}</p>
                                                    </div>
                                                </div>
                                                <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
                                                    <span className="text-[9px] uppercase tracking-widest text-gray-600">Unrealized P/L</span>
                                                    <span className={`font-mono text-[10px] font-semibold ${signedTone(pnl)}`}>
                                                        {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} ({pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%)
                                                    </span>
                                                </div>
                                            </motion.div>
                                        )
                                    })}
                                </AnimatePresence>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
