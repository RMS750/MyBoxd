import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Clock3, Star } from 'lucide-react'
import type { Movie } from '../types'
import { api } from '../services/api'
import { rating, runtime } from '../utils/format'
import { Pill, ScoreRing } from './UI'

export default function MovieCard({movie, compact=false}:{movie:Movie,compact?:boolean}) {
  const [poster,setPoster]=useState(movie.poster_url ?? null)
  const ref=useRef<HTMLDivElement|null>(null)

  useEffect(()=>{
    setPoster(movie.poster_url ?? null)
    if(movie.poster_url)return
    const node=ref.current
    if(!node)return
    let active=true
    let controller:AbortController|null=null
    const observer=new IntersectionObserver((entries)=>{
      if(!entries.some(e=>e.isIntersecting))return
      observer.disconnect()
      controller=new AbortController()
      api.get<{poster_url?:string|null}>(`/movies/${movie.id}/poster`,controller.signal)
        .then(r=>{if(active&&r.poster_url)setPoster(r.poster_url)})
        .catch(()=>{})
    },{rootMargin:'300px'})
    observer.observe(node)
    return()=>{active=false;observer.disconnect();controller?.abort()}
  },[movie.id,movie.poster_url])

  const community=movie.letterboxd_rating!=null
    ? `LB ${movie.letterboxd_rating.toFixed(2)}`
    : movie.community_rating!=null && movie.community_source
      ? `${movie.community_source==='MovieLens'?'ML':movie.community_source} ${movie.community_rating.toFixed(2)}`
      : null

  return <Link to={`/movies/${movie.id}`} className={`group overflow-hidden rounded-2xl border border-white/8 bg-white/[.035] transition hover:-translate-y-1 hover:border-white/15 hover:bg-white/[.055] ${compact ? 'flex' : 'block'}`}>
    <div ref={ref} className={compact ? 'w-24 shrink-0' : 'aspect-[2/3]'}>
      {poster ? <img className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" src={poster} alt={`${movie.title} poster`} loading="lazy" decoding="async"/> : <div className="grid h-full min-h-36 place-items-center bg-gradient-to-br from-zinc-800 to-zinc-950 p-3 text-center text-xs text-zinc-500">Loading poster…</div>}
    </div>
    <div className="p-3.5">
      <div className="flex items-start justify-between gap-2"><div><div className="line-clamp-1 font-semibold">{movie.title}</div><div className="mt-0.5 text-xs text-zinc-500">{movie.year ?? 'Year unknown'}</div></div>{movie.match_score != null && <ScoreRing score={movie.match_score}/>}</div>
      <div className="mt-3 flex flex-wrap gap-1.5">{movie.category && <Pill>{movie.category}</Pill>}{movie.predicted_rating != null && <Pill><Star size={11} className="mr-1"/> You {rating(movie.predicted_rating)}</Pill>}{community && <Pill>{community}</Pill>}{movie.runtime != null && <Pill><Clock3 size={11} className="mr-1"/> {runtime(movie.runtime)}</Pill>}</div>
      {movie.explanation && !compact && <p className="mt-3 line-clamp-3 text-xs leading-5 text-zinc-400">{movie.explanation}</p>}
    </div>
  </Link>
}
