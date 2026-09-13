import { useState } from 'react'
import { Dice5, Sparkles } from 'lucide-react'
import type { Movie } from '../types'
import { api } from '../services/api'
import MovieCard from '../components/MovieCard'
import { Card, EmptyState, PageHeader } from '../components/UI'

type Mode='any'|'under90'|'under120'|'watchlist'|'hidden'|'safe'|'wild'
const modes:[Mode,string,string][]=[
  ['any','Anything','A personalized roll from your strongest candidates.'],
  ['under90','Under 90 min','A compact film that still fits your taste.'],
  ['under120','Under 2 hours','Keep the evening manageable.'],
  ['watchlist','Watchlist only','Finally pick something you already saved.'],
  ['hidden','Hidden gem','Lower-popularity candidates with strong fit.'],
  ['safe','Safe bet','Stay close to proven preferences.'],
  ['wild','Wild card','Take a defensible step outside your normal lane.'],
]

export default function Roulette(){
  const [mode,setMode]=useState<Mode>('any')
  const [movie,setMovie]=useState<Movie|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const roll=async()=>{
    setBusy(true);setError('')
    const body:Record<string,unknown>={}
    if(mode==='under90')body.max_runtime=90
    if(mode==='under120')body.max_runtime=120
    if(mode==='watchlist')body.watchlist_only=true
    if(mode==='hidden')body.hidden_gem=true
    if(mode==='safe')body.category='SAFE BET'
    if(mode==='wild')body.category='WILD CARD'
    try{setMovie(await api.post<Movie>('/roulette',body))}catch(e){setMovie(null);setError((e as Error).message)}finally{setBusy(false)}
  }
  return <>
    <PageHeader eyebrow="One decision, personalized" title="Movie Roulette" subtitle="The roll is random only within a personalized candidate pool. Better-matching films receive more weight, so chance adds variety without throwing away your taste model."/>
    <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <Card className="p-5"><h2 className="font-semibold">Choose the kind of roll</h2><div className="mt-4 space-y-2">{modes.map(([value,title,body])=><button key={value} onClick={()=>setMode(value)} className={`w-full rounded-xl border p-3 text-left transition ${mode===value?'border-violet-400/35 bg-violet-400/10':'border-white/8 bg-white/[.02] hover:bg-white/[.04]'}`}><div className="text-sm font-medium">{title}</div><div className="mt-1 text-xs leading-4 text-zinc-500">{body}</div></button>)}</div><button onClick={roll} disabled={busy} className="btn btn-primary mt-5 w-full py-3"><Dice5 className={busy?'animate-spin':''} size={17}/>{busy?'Rolling…':'Roll a movie'}</button>{error&&<p role="alert" className="mt-3 text-sm text-amber-300">{error}</p>}</Card>
      <div>{movie?<div className="mx-auto max-w-sm"><div className="mb-3 flex items-center justify-center gap-2 text-xs uppercase tracking-[.2em] text-violet-300"><Sparkles size={14}/> Your roll</div><MovieCard movie={movie}/></div>:!busy&&!error?<EmptyState title="Ready when you are" body="Choose a mode and roll. MyBoxd samples from ranked candidates rather than choosing a completely unrelated random film."/>:null}</div>
    </div>
  </>
}
