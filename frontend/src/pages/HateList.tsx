import { useEffect, useState } from 'react'
import { Skull, TriangleAlert } from 'lucide-react'
import type { Movie, RecommendationResponse } from '../types'
import { api } from '../services/api'
import MovieCard from '../components/MovieCard'
import { Card, EmptyState, ErrorState, Loading, PageHeader } from '../components/UI'

export default function HateList(){
  const [movies,setMovies]=useState<Movie[]>([])
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  useEffect(()=>{api.get<RecommendationResponse>('/anti-recommendations?limit=60').then(r=>setMovies(r.recommendations)).catch((e:Error)=>setError(e.message)).finally(()=>setLoading(false))},[])
  if(loading)return <Loading text="Preparing your cinematic enemies list…"/>
  return <>
    <PageHeader eyebrow="Scientifically petty" title="Movies You’d Hate" subtitle="A deliberately mean ranking of unseen films that collide with your taste. Low personal fit, resemblance to your lowest-rated movies, and bad Letterboxd reception all count against them."/>
    <Card className="mb-6 p-4"><div className="flex gap-3"><Skull className="mt-0.5 shrink-0 text-rose-300" size={20}/><div><div className="font-semibold">This page is supposed to be funny, not prophetic.</div><p className="mt-1 text-sm leading-6 text-zinc-500">The lower the match score, the more MyBoxd thinks watching it would be an act of self-sabotage. A cult movie can still escape if your own history strongly suggests you’d love it.</p></div></div></Card>
    {error&&<ErrorState message={error}/>} 
    {!error&&movies.length===0&&<EmptyState title="Annoyingly, nothing is hate-worthy enough" body="MyBoxd does not have strong enough negative evidence yet. More rated history and metadata will make this page meaner."/>}
    {movies.length>0&&<><div className="mb-4 flex items-center gap-2 text-sm text-zinc-500"><TriangleAlert size={15}/> Ranked from most likely to ruin movie night downward.</div><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">{movies.map(movie=><MovieCard key={movie.id} movie={movie}/>)}</div></>}
  </>
}
