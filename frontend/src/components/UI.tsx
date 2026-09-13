import type { ReactNode } from 'react'
import { AlertTriangle, LoaderCircle } from 'lucide-react'

export function PageHeader({eyebrow, title, subtitle, actions}:{eyebrow?:string,title:string,subtitle?:string,actions?:ReactNode}) {
  return <div className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end"><div>{eyebrow && <div className="mb-2 text-xs font-semibold uppercase tracking-[.22em] text-violet-300">{eyebrow}</div>}<h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>{subtitle && <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">{subtitle}</p>}</div>{actions}</div>
}
export function Card({children,className=''}:{children:ReactNode,className?:string}) { return <div className={`glass rounded-2xl border border-white/8 ${className}`}>{children}</div> }
export function Loading({text='Loading…'}:{text?:string}) { return <div className="grid min-h-48 place-items-center text-zinc-400"><div className="flex items-center gap-3"><LoaderCircle className="animate-spin" size={18}/>{text}</div></div> }
export function ErrorState({message}:{message:string}) { return <Card className="p-5"><div className="flex gap-3 text-amber-200"><AlertTriangle className="shrink-0" size={18}/><div><div className="font-semibold">Couldn’t load this section</div><div className="mt-1 text-sm text-zinc-400">{message}</div></div></div></Card> }
export function EmptyState({title='Nothing here yet',body}:{title?:string,body:string}) { return <Card className="p-8 text-center"><div className="font-semibold">{title}</div><p className="mx-auto mt-2 max-w-lg text-sm text-zinc-400">{body}</p></Card> }
export function Stat({label,value,hint}:{label:string,value:ReactNode,hint?:string}) { return <Card className="p-4"><div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-2 text-2xl font-bold">{value}</div>{hint && <div className="mt-1 text-xs text-zinc-500">{hint}</div>}</Card> }
export function Pill({children}:{children:ReactNode}) { return <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-300">{children}</span> }
export function ScoreRing({score=0}:{score?:number}) {
  const tone=score>=80?'border-emerald-400/30 bg-emerald-500/10 text-emerald-200':score>=62?'border-violet-400/30 bg-violet-500/10 text-violet-200':score>=42?'border-amber-400/30 bg-amber-500/10 text-amber-100':'border-rose-400/30 bg-rose-500/10 text-rose-200'
  return <div title="Personal match score from 0–100. It is a calibrated ranking score, not a literal probability." aria-label={`Personal match score ${Math.round(score)} out of 100`} className={`grid h-12 w-12 shrink-0 place-items-center rounded-full border text-xs font-bold ${tone}`}>{Math.round(score)}</div>
}
