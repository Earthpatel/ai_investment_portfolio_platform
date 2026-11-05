export const usd = (v: number | null | undefined, digits = 0) =>
  v == null || !isFinite(v) ? '—' : v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits })

export const usdShort = (v: number) => {
  const a = Math.abs(v)
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `$${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`
  if (a >= 1e3) return `$${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`
  return `$${v.toFixed(0)}`
}

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || !isFinite(v) ? '—' : `${(v * 100).toFixed(digits)}%`

export const signedPct = (v: number | null | undefined, digits = 1) =>
  v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`

export const num = (v: number | null | undefined, digits = 2) =>
  v == null || !isFinite(v) ? '—' : v.toFixed(digits)

export const percentile = (sorted: number[], p: number) => {
  if (!sorted.length) return NaN
  const i = (sorted.length - 1) * p
  const lo = Math.floor(i), hi = Math.ceil(i)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo)
}

export function histogram(values: number[], bins = 40, lo?: number, hi?: number) {
  if (!values.length) return []
  const s = [...values].sort((a, b) => a - b)
  const a = lo ?? percentile(s, 0.005), b = hi ?? percentile(s, 0.995)
  const w = (b - a) / bins || 1
  const out = Array.from({ length: bins }, (_, i) => ({ x0: a + i * w, x1: a + (i + 1) * w, mid: a + (i + 0.5) * w, count: 0 }))
  for (const v of values) {
    const k = Math.min(bins - 1, Math.max(0, Math.floor((v - a) / w)))
    out[k].count++
  }
  return out
}

export function downloadText(name: string, text: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
