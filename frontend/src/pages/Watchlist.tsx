import { useEffect, useMemo, useState } from 'react'
import type { Movie, RecommendationResponse } from '../types'
import { api } from '../services/api'
import MovieCard from '../components/MovieCard'
import { EmptyState, ErrorState, Loading, PageHeader } from '../components/UI'

const sorts=[['best','Best match'],['predicted','Predicted rating'],['shortest','Shortest'],['longest','Longest'],['popular','Most popular'],['obscure','Most obscure'],['newest','Newest'],['oldest','Oldest']]

export default function Watchlist(){
  const [sort,setSort]=useState('best')
  const [movies,setMovies]=useState<Movie[]>([])
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [genre,setGenre]=useState('')
  const [maxRuntime,setMaxRuntime]=useState(0)
  const [query,setQuery]=useState('')

  useEffect(()=>{setLoading(true);setError('');api.get<RecommendationResponse>(`/watchlist/ranked?sort=${sort}`).then(r=>setMovies(r.recommendations)).catch((e:Error)=>setError(e.message)).finally(()=>setLoading(false))},[sort])
  const genres=useMemo(()=>Array.from(new Set(movies.flatMap(m=>m.genres||[]))).sort(),[movies])
  const filtered=useMemo(()=>movies.filter(m=>(!genre||(m.genres||[]).includes(genre))&&(!maxRuntime||!m.runtime||m.runtime<=maxRuntime)&&(!query||m.title.toLowerCase().includes(query.toLowerCase()))),[movies,genre,maxRuntime,query])

  return <>
    <PageHeader eyebrow="Prioritize what you already saved" title="Ranked watchlist" subtitle="Your Letterboxd watchlist ordered by MyBoxd’s predicted fit, with client-side filters that do not trigger extra metadata calls." actions={<select aria-label="Sort watchlist" className="input w-auto min-w-44" value={sort} onChange={e=>setSort(e.target.value)}>{sorts.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>}/>
    <div className="mb-5 grid gap-2 sm:grid-cols-3"><input aria-label="Filter watchlist by title" className="input" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Filter by title…"/><select aria-label="Filter watchlist by genre" className="input" value={genre} onChange={e=>setGenre(e.target.value)}><option value="">All genres</option>{genres.map(g=><option key={g}>{g}</option>)}</select><select aria-label="Filter watchlist by runtime" className="input" value={maxRuntime} onChange={e=>setMaxRuntime(Number(e.target.value))}><option value={0}>Any runtime</option><option value={90}>Under 90 minutes</option><option value={120}>Under 2 hours</option><option value={150}>Under 2½ hours</option></select></div>
    {loading?<Loading text="Ranking your watchlist…"/>:error?<ErrorState message={error}/>:filtered.length?<div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{filtered.map(m=><MovieCard key={m.id} movie={m}/>)}</div>:<EmptyState title={movies.length?'No films match those filters':'Your watchlist is empty'} body={movies.length?'Try widening the genre/runtime filters.':'Import a Letterboxd watchlist and MyBoxd will rank it by predicted enjoyment.'}/>} 
  </>
}
