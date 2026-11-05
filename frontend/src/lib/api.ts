export type Asset = { ticker: string; name: string; sector: string; industry: string; type: 'Stock' | 'ETF' | 'Unknown'; expense?: number }

export type Summary = {
  total_contributed: number; median_end: number; mean_end: number; median_gain: number
  median_multiple_of_contributions: number | null
  p5_end: number; p10_end: number; p25_end: number; p75_end: number; p90_end: number; p95_end: number
  median_end_real: number; prob_below_contributions: number; prob_goal: number | null; cvar5_end: number
  median_annualized_twr: number; p10_annualized_twr: number; p90_annualized_twr: number
  median_max_drawdown: number; p90_max_drawdown: number; prob_drawdown_over_30: number; n_sims: number
}

export type SimResult = {
  months: number[]; contributions: number[]; inflation_factor: number[]
  percentiles: Record<string, number[]>; percentiles_real: Record<string, number[]>
  sample_paths: number[][]; terminal: number[]; terminal_real: number[]
  max_drawdowns: number[]; annualized_twr: number[]
  yearly: Array<Record<string, number>>
  summary: Summary
  assumptions: {
    label: string; method: string; tickers: string[]; weights: number[]
    arithmetic_mean: number[]; geometric_mean: number[]; volatility: number[]
    notes: string[]; warnings: string[]; dividend_yields: number[] | null
    calibration_start: string; calibration_end: string; calibration_months: number
  }
  data: DataInfo[]; synthetic: boolean; request_hash: string; elapsed_ms: number
}

export type DataInfo = { ticker: string; source: string; last_updated: string | null; first_date?: string; last_date?: string; observations?: number; note?: string | null; is_synthetic?: boolean }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      if (typeof j.detail === 'string') msg = j.detail
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('; ')
    } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  health: () => req<{ ok: boolean; dev_synthetic: boolean; network: boolean; local_history: boolean }>('/api/health'),
  universe: () => req<{ assets: Asset[]; sector_etfs: Record<string, string>; etf_holdings: Record<string, string[]>; dev_synthetic: boolean }>('/api/universe'),
  quality: (tickers: string[], window: string) => req<any>(`/api/quality?tickers=${encodeURIComponent(tickers.join(','))}&window=${window}`),
  simulate: (body: unknown, signal?: AbortSignal) => req<SimResult>('/api/simulate', { method: 'POST', body: JSON.stringify(body), signal }),
  compare: (body: unknown) => req<any>('/api/simulate/compare', { method: 'POST', body: JSON.stringify(body) }),
  stress: (body: unknown) => req<any>('/api/stress', { method: 'POST', body: JSON.stringify(body) }),
  asset: (t: string, period: string) => req<any>(`/api/asset/${encodeURIComponent(t)}?period=${period}`),
  optimize: (body: unknown) => req<any>('/api/optimize', { method: 'POST', body: JSON.stringify(body) }),
  backtest: (body: unknown) => req<any>('/api/backtest', { method: 'POST', body: JSON.stringify(body) }),
  mlTrain: (body: unknown) => req<any>('/api/ml/train', { method: 'POST', body: JSON.stringify(body) }),
  mlStatus: () => req<any>('/api/ml/status'),
  mlResults: () => req<any>('/api/ml/results'),
  mlPredictions: (t: string[]) => req<any>(`/api/ml/predictions?tickers=${encodeURIComponent(t.join(','))}`),
}
