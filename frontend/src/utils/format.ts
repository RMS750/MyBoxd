export const pct = (v?: number | null) => `${Math.round(v ?? 0)}%`
export const rating = (v?: number | null) => v == null ? '—' : v.toFixed(1)
export const runtime = (m?: number | null) => !m ? '—' : m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`
export const titleCase = (s: string) => s.replaceAll('_', ' ').replace(/\b\w/g, (x) => x.toUpperCase())
