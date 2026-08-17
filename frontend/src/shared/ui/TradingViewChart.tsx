import { useMemo } from 'react'
import { BarChart3 } from 'lucide-react'

type TradingViewChartProps = {
  symbol: string
  label?: string
  assetClass?: string
  category?: string
  className?: string
}

const EXPLICIT_SYMBOLS: Record<string, string> = {
  // Commodities
  XAUUSD: 'OANDA:XAUUSD',
  XAGUSD: 'OANDA:XAGUSD',
  PLATINUM: 'NYMEX:PL1!',
  PALLADIUM: 'NYMEX:PA1!',
  COPPER: 'COMEX:HG1!',
  WTI: 'NYMEX:CL1!',
  BRENT: 'TVC:UKOIL',
  NATGAS: 'NYMEX:NG1!',
  HEATINGOIL: 'NYMEX:HO1!',
  CORN: 'CBOT:ZC1!',
  WHEAT: 'CBOT:ZW1!',
  SOYBEANS: 'CBOT:ZS1!',
  COFFEE: 'ICEUS:KC1!',
  SUGAR: 'ICEUS:SB1!',
  COTTON: 'ICEUS:CT1!',
  COCOA: 'ICEUS:CC1!',
  ORANGEJUICE: 'ICEUS:OJ1!',
  LEANHOGS: 'CME:HE1!',
  LIVECATTLE: 'CME:LE1!',
  FEEDERCATTLE: 'CME:GF1!',
  OATS: 'CBOT:ZO1!',
  ROUGH_RICE: 'CBOT:ZR1!',
  SOYMEAL: 'CBOT:ZM1!',
  SOYOIL: 'CBOT:ZL1!',
  LUMBER: 'CME:LBR1!',

  // Indices
  SPX: 'SP:SPX',
  NDX: 'NASDAQ:NDX',
  DJI: 'DJ:DJI',
  RUT: 'TVC:RUT',
  DAX: 'XETR:DAX',
  FTSE: 'TVC:UKX',
  CAC: 'EURONEXT:PX1',
  STOXX50: 'TVC:SX5E',
  NKY: 'TVC:NI225',
  HSI: 'HSI:HSI',
  SSEC: 'SSE:000001',
  SENSEX: 'BSE:SENSEX',
  NIFTY: 'NSE:NIFTY',
  ASX200: 'ASX:XJO',
  TSX: 'TSX:TSX',
  IBOV: 'BMFBOVESPA:IBOV',
  MEXBOL: 'BMV:ME',
  KOSPI: 'KRX:KOSPI',
  TWSE: 'TWSE:TAIEX',
  STI: 'TVC:STI',
  JKSE: 'IDX:COMPOSITE',
  KLSE: 'MYX:FBMKLCI',
  TA35: 'TASE:TA35',
  IBEX: 'BME:IBC',
  SMI: 'SIX:SMI',

  // ETFs
  SPY: 'AMEX:SPY',
  QQQ: 'NASDAQ:QQQ',
  DIA: 'AMEX:DIA',
  IWM: 'AMEX:IWM',
  GLD: 'AMEX:GLD',
  SLV: 'AMEX:SLV',
  USO: 'AMEX:USO',
  UNG: 'AMEX:UNG',
  TLT: 'NASDAQ:TLT',
}

const NASDAQ_SYMBOLS = new Set([
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'COST',
  'NFLX', 'ADBE', 'CSCO', 'TMUS', 'AMD', 'CMCSA',
])

function normalizeSymbol(symbol: string): string {
  return symbol.replace(/[/:]/g, '').trim().toUpperCase()
}

function resolveTradingViewSymbol(symbol: string, assetClass?: string, category?: string): string {
  const clean = normalizeSymbol(symbol)
  if (EXPLICIT_SYMBOLS[clean]) return EXPLICIT_SYMBOLS[clean]

  const marketClass = `${assetClass || ''} ${category || ''}`.toLowerCase()
  if (marketClass.includes('crypto')) return `BINANCE:${clean}USDT`
  if (marketClass.includes('forex')) return `FX:${clean}`
  if (marketClass.includes('etf')) return `AMEX:${clean}`
  if (marketClass.includes('stock')) {
    return `${NASDAQ_SYMBOLS.has(clean) ? 'NASDAQ' : 'NYSE'}:${clean}`
  }

  return clean
}

function buildTradingViewIframeSrc(tradingViewSymbol: string): string {
  const settings = {
    autosize: true,
    symbol: tradingViewSymbol,
    interval: '60',
    timezone: 'Etc/UTC',
    theme: 'dark',
    style: '1',
    locale: 'en',
    allow_symbol_change: true,
    calendar: false,
    details: true,
    hide_side_toolbar: false,
    hide_top_toolbar: false,
    hide_legend: false,
    save_image: false,
    support_host: 'https://www.tradingview.com',
  }

  return `https://www.tradingview-widget.com/embed-widget/advanced-chart/?locale=en#${encodeURIComponent(JSON.stringify(settings))}`
}

export function TradingViewChart({
  symbol,
  label,
  assetClass,
  category,
  className = '',
}: TradingViewChartProps) {
  const tradingViewSymbol = useMemo(
    () => resolveTradingViewSymbol(symbol, assetClass, category),
    [assetClass, category, symbol],
  )
  const iframeSrc = useMemo(() => buildTradingViewIframeSrc(tradingViewSymbol), [tradingViewSymbol])

  return (
    <div className={`bg-white/5 border border-white/10 rounded-xl overflow-hidden ${className}`}>
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/10">
        <div className="min-w-0 flex items-center gap-2">
          <BarChart3 className="h-4 w-4 shrink-0 text-[#00f2ff]" />
          <div className="min-w-0">
            <div className="text-white font-mono text-sm font-bold truncate">MARKET CHART</div>
            <div className="text-white/40 font-mono text-[10px] truncate">{label || symbol}</div>
          </div>
        </div>
        <span className="shrink-0 text-[10px] font-mono text-white/50">{tradingViewSymbol}</span>
      </div>
      <iframe
        key={tradingViewSymbol}
        title={`${label || symbol} TradingView chart`}
        src={iframeSrc}
        className="h-[420px] w-full bg-[#050814]"
        style={{ border: 0 }}
        allow="fullscreen"
        referrerPolicy="origin"
        loading="lazy"
      />
    </div>
  )
}
