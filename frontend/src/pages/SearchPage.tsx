import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Search as SearchIcon, SlidersHorizontal, Sparkles, X } from 'lucide-react'
import type { Movie, RecommendationResponse } from '../types'
import { api } from '../services/api'
import MovieCard from '../components/MovieCard'
import { Card, EmptyState, PageHeader } from '../components/UI'

type SortMode='match'|'letterboxd'|'newest'|'popular'|'shortest'

export default function SearchPage(){
  const [q,setQ]=useState('')
  const [movies,setMovies]=useState<Movie[]>([])
  const [catalogue,setCatalogue]=useState<Movie[]>([])
  const [busy,setBusy]=useState(false)
  const [catalogueBusy,setCatalogueBusy]=useState(true)
  const [error,setError]=useState('')
  const [searched,setSearched]=useState(false)
  const [genre,setGenre]=useState('')
  const [yearFrom,setYearFrom]=useState('')
  const [yearTo,setYearTo]=useState('')
  const [minLetterboxd,setMinLetterboxd]=useState('')
  const [maxRuntime,setMaxRuntime]=useState('')
  const [sort,setSort]=useState<SortMode>('match')

  useEffect(()=>{
    api.get<RecommendationResponse>('/recommendations?limit=60')
      .then(r=>setCatalogue(r.recommendations))
      .catch((e:Error)=>setError(e.message))
      .finally(()=>setCatalogueBusy(false))
  },[])

  const search=async(query:string,signal?:AbortSignal)=>{
    const clean=query.trim()
    if(clean.length<2){setMovies([]);setSearched(false);setBusy(false);setError('');return}
    setBusy(true);setError('');setSearched(true)
    try{
      const r=await api.get<{results:Movie[];warning?:string}>(`/search?q=${encodeURIComponent(clean)}`,signal)
      setMovies(r.results); if(r.warning)setError(r.warning)
    }catch(e){if((e as Error).name!=='AbortError')setError((e as Error).message)}finally{if(!signal?.aborted)setBusy(false)}
  }

  useEffect(()=>{
    const controller=new AbortController()
    const timer=window.setTimeout(()=>void search(q,controller.signal),350)
    return()=>{window.clearTimeout(timer);controller.abort()}
  },[q])

  const base=q.trim().length>=2?movies:catalogue
  const genres=useMemo(()=>Array.from(new Set(base.flatMap(m=>m.genres??[]))).sort(),[base])
  const filtered=useMemo(()=>{
    const from=yearFrom?Number(yearFrom):null
    const to=yearTo?Number(yearTo):null
    const lb=minLetterboxd?Number(minLetterboxd):null
    const runtime=maxRuntime?Number(maxRuntime):null
    const out=base.filter(movie=>{
      if(genre && !(movie.genres??[]).includes(genre))return false
      if(from && movie.year && movie.year<from)return false
      if(to && movie.year && movie.year>to)return false
      if(lb && (movie.letterboxd_rating==null || movie.letterboxd_rating<lb))return false
      if(runtime && movie.runtime && movie.runtime>runtime)return false
      return true
    })
    return [...out].sort((a,b)=>{
      if(sort==='letterboxd')return (b.letterboxd_rating??-1)-(a.letterboxd_rating??-1)
      if(sort==='newest')return (b.year??0)-(a.year??0)
      if(sort==='popular')return (b.popularity??0)-(a.popularity??0)
      if(sort==='shortest')return (a.runtime??9999)-(b.runtime??9999)
      return (b.match_score??0)-(a.match_score??0)
    })
  },[base,genre,yearFrom,yearTo,minLetterboxd,maxRuntime,sort])

  const clearFilters=()=>{setGenre('');setYearFrom('');setYearTo('');setMinLetterboxd('');setMaxRuntime('');setSort('match')}
  const submit=(e:FormEvent)=>{e.preventDefault();void search(q)}
  const activeFilters=Boolean(genre||yearFrom||yearTo||minLetterboxd||maxRuntime||sort!=='match')

  return <>
    <PageHeader eyebrow="Search + browse" title="Movie Search" subtitle="Browse a personalized catalogue before typing, or search any title. Results use your taste model plus Letterboxd's public weighted average when available."/>
    <form onSubmit={submit} className="mb-4 flex gap-2">
      <div className="relative flex-1">
        <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 z-10 -translate-y-1/2 text-zinc-500" size={18}/>
        <input aria-label="Search movies" className="input search-input" value={q} onChange={e=>setQ(e.target.value)} placeholder="Search a movie, e.g. Perfect Blue…"/>
        {q&&<button type="button" aria-label="Clear search" onClick={()=>setQ('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"><X size={17}/></button>}
      </div>
      <button className="btn btn-primary" disabled={busy||q.trim().length<2}>{busy?'Searching…':'Search'}</button>
    </form>

    <Card className="mb-7 p-4">
      <div className="mb-3 flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-sm font-semibold"><SlidersHorizontal size={16}/> Filters</div>{activeFilters&&<button onClick={clearFilters} className="text-xs text-zinc-500 hover:text-white">Reset all</button>}</div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        <select className="input" value={genre} onChange={e=>setGenre(e.target.value)}><option value="">All genres</option>{genres.map(g=><option key={g} value={g}>{g}</option>)}</select>
        <input className="input" inputMode="numeric" value={yearFrom} onChange={e=>setYearFrom(e.target.value)} placeholder="Year from"/>
        <input className="input" inputMode="numeric" value={yearTo} onChange={e=>setYearTo(e.target.value)} placeholder="Year to"/>
        <select className="input" value={minLetterboxd} onChange={e=>setMinLetterboxd(e.target.value)}><option value="">Any LB rating</option><option value="2.5">LB 2.5+</option><option value="3">LB 3.0+</option><option value="3.5">LB 3.5+</option><option value="4">LB 4.0+</option></select>
        <select className="input" value={maxRuntime} onChange={e=>setMaxRuntime(e.target.value)}><option value="">Any runtime</option><option value="90">≤ 90 min</option><option value="120">≤ 2 hours</option><option value="150">≤ 2.5 hours</option></select>
        <select className="input" value={sort} onChange={e=>setSort(e.target.value as SortMode)}><option value="match">Best personal match</option><option value="letterboxd">Highest Letterboxd</option><option value="newest">Newest</option><option value="popular">Most popular</option><option value="shortest">Shortest</option></select>
      </div>
    </Card>

    {error&&<p role="status" className="mb-4 text-sm text-amber-300">{error}</p>}
    <div className="mb-4 flex items-end justify-between gap-3"><div><div className="flex items-center gap-2 font-semibold">{q.trim().length>=2?'Search results':<><Sparkles size={16} className="text-violet-300"/> Your catalogue</>}</div><p className="mt-1 text-xs text-zinc-500">{q.trim().length>=2?`${filtered.length} result${filtered.length===1?'':'s'} after filters`:'A rotating browse shelf ranked for your taste — no search required.'}</p></div></div>
    {(catalogueBusy&&!q.trim())||busy?<div className="py-16 text-center text-sm text-zinc-500">Loading movies…</div>:filtered.length?<div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">{filtered.map(m=><MovieCard key={m.id} movie={m}/>)}</div>:searched&&!busy?<EmptyState body="No titles match this search and filter combination. Try resetting a filter or changing the title."/>:<EmptyState body="Your catalogue will fill once MyBoxd has enough imported history and metadata."/>}
  </>
}
