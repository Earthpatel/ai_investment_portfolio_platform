import { useState, type ReactNode } from 'react'
import { Info, AlertTriangle, Loader2 } from 'lucide-react'

export function Card({ title, subtitle, right, children, className = '', tone }: {
  title?: ReactNode; subtitle?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; tone?: 'ai' | 'warn'
}) {
  const ring = tone === 'ai' ? 'border-ai/40' : tone === 'warn' ? 'border-warn/40' : 'border-line'
  return (
    <section className={`rounded-2xl border ${ring} bg-panel p-5 fade-in ${className}`}>
      {(title || right) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone, tip }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: 'gain' | 'loss' | 'warn' | 'ai'; tip?: string }) {
  const color = tone === 'gain' ? 'text-gain' : tone === 'loss' ? 'text-loss' : tone === 'warn' ? 'text-warn' : tone === 'ai' ? 'text-ai' : ''
  return (
    <div className="rounded-xl border border-line bg-panel-2/60 p-3.5">
      <div className="flex items-center gap-1 text-[12px] text-muted">{label}{tip && <Tip text={tip} />}</div>
      <div className={`num mt-1 text-xl font-semibold ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[12px] text-faint">{sub}</div>}
    </div>
  )
}

export function Tip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button type="button" aria-label="Explain" onClick={() => setOpen(o => !o)} onBlur={() => setOpen(false)}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} className="text-faint hover:text-accent">
        <Info size={13} />
      </button>
      {open && (
        <span role="tooltip" className="absolute left-1/2 top-5 z-50 w-64 -translate-x-1/2 rounded-lg border border-line bg-panel p-2.5 text-[12px] font-normal leading-snug text-ink shadow-xl">
          {text}
        </span>
      )}
    </span>
  )
}

export function Button({ children, onClick, variant = 'primary', disabled, title, type = 'button', className = '' }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost' | 'ai' | 'danger'; disabled?: boolean; title?: string; type?: 'button' | 'submit'; className?: string
}) {
  const v = {
    primary: 'bg-accent text-white hover:brightness-110',
    ghost: 'border border-line bg-panel-2 text-ink hover:border-accent/60',
    ai: 'bg-ai text-white hover:brightness-110',
    danger: 'border border-loss/40 text-loss hover:bg-loss/10',
  }[variant]
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${v} ${className}`}>
      {children}
    </button>
  )
}

export function Field({ label, tip, children, hint }: { label: ReactNode; tip?: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-1 text-[12px] font-medium text-muted">{label}{tip && <Tip text={tip} />}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-faint">{hint}</span>}
    </label>
  )
}

export const inputCls = 'w-full rounded-lg border border-line bg-panel-2 px-3 py-2 text-[13px] outline-none focus:border-accent'

export function NumberInput({ value, onChange, min, max, step = 1, prefix, suffix }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; prefix?: string; suffix?: string
}) {
  return (
    <div className="flex items-center rounded-lg border border-line bg-panel-2 focus-within:border-accent">
      {prefix && <span className="pl-3 text-[13px] text-faint">{prefix}</span>}
      <input type="number" value={Number.isFinite(value) ? value : ''} min={min} max={max} step={step}
        onChange={e => {
          const v = parseFloat(e.target.value)
          if (!isNaN(v)) onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v)))
        }}
        className="num w-full bg-transparent px-3 py-2 text-[13px] outline-none" />
      {suffix && <span className="pr-3 text-[13px] text-faint">{suffix}</span>}
    </div>
  )
}

/** Slider and number box bound to the same value (they can never disagree). */
export function SliderNumber({ value, onChange, min, max, step = 1, suffix }: { value: number; onChange: (v: number) => void; min: number; max: number; step?: number; suffix?: string }) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(parseFloat(e.target.value))} className="flex-1" aria-label="slider" />
      <div className="w-28"><NumberInput value={value} onChange={onChange} min={min} max={max} step={step} suffix={suffix} /></div>
    </div>
  )
}

export function Segmented<T extends string | number>({ options, value, onChange, size = 'md' }: {
  options: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; size?: 'sm' | 'md'
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-panel-2 p-1" role="radiogroup">
      {options.map(o => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded-md ${size === 'sm' ? 'px-2 py-1 text-[11px]' : 'px-2.5 py-1.5 text-[12px]'} font-medium transition ${o.value === value ? 'bg-accent text-white' : 'text-muted hover:text-ink'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Alert({ tone = 'warn', children }: { tone?: 'warn' | 'loss' | 'ai' | 'info'; children: ReactNode }) {
  const c = { warn: 'border-warn/40 bg-warn/10 text-warn', loss: 'border-loss/40 bg-loss/10 text-loss', ai: 'border-ai/40 bg-ai/10 text-ai', info: 'border-accent/30 bg-accent/10 text-accent' }[tone]
  return (
    <div className={`flex gap-2 rounded-xl border px-3.5 py-2.5 text-[13px] ${c}`}>
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <div className="text-ink/90">{children}</div>
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-[13px] text-muted"><Loader2 size={15} className="animate-spin" />{label}</span>
}

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
      <h1 className="mt-1 font-display text-[28px] font-semibold tracking-tight">{title}</h1>
      {children && <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-muted">{children}</p>}
    </div>
  )
}

export const CHART = {
  accent: 'var(--accent)', gain: 'var(--gain)', loss: 'var(--loss)', ai: 'var(--ai)', warn: 'var(--warn)', muted: 'var(--muted)', grid: 'var(--grid)',
  series: ['#3b82f6', '#34d399', '#a78bfa', '#fbbf24', '#f87171', '#22d3ee', '#f472b6', '#94a3b8', '#84cc16', '#fb923c'],
}
