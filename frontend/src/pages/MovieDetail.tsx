import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Clock3, ExternalLink, MessageSquareText, Star } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import type { Movie, MovieReview } from '../types'
import { api } from '../services/api'
import MovieRail from '../components/MovieRail'
import { Card, ErrorState, Loading, Pill, ScoreRing } from '../components/UI'
import { rating, runtime } from '../utils/format'

type ReviewResponse={reviews:MovieReview[];source:string;available:boolean}

function reviewDate(value?:string|null){if(!value)return null;const d=new Date(value);return Number.isNaN(d.getTime())?null:d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'})}

export default function MovieDetail(){
  const {id}=useParams()
  const [movie,setMovie]=useState<Movie|null>(null)
  const [similar,setSimilar]=useState<Movie[]>([])
  const [reviews,setReviews]=useState<MovieReview[]>([])
  const [reviewsAvailable,setReviewsAvailable]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  useEffect(()=>{
    if(!id)return
    let active=true
    setLoading(true);setError('');setSimilar([]);setReviews([])
    api.get<Movie>(`/movies/${id}`)
      .then(m=>{
        if(!active)return
        setMovie(m);setLoading(false)
        void api.get<{movies:Movie[]}>(`/movies/${id}/similar`).then(s=>{if(active)setSimilar(s.movies)}).catch(()=>{})
        void api.get<ReviewResponse>(`/movies/${id}/reviews`).then(r=>{if(active){setReviews(r.reviews);setReviewsAvailable(r.available)}}).catch(()=>{})
      })
      .catch((e:Error)=>{if(active){setError(e.message);setLoading(false)}})
    return()=>{active=false}
  },[id])
  const caveats=useMemo(()=>movie?.components?Object.entries(movie.components).sort((a,b)=>a[1]-b[1]).slice(0,2):[],[movie])
  if(loading)return <Loading text="Loading movie details…"/>
  if(error||!movie)return <ErrorState message={error||'Movie not found.'}/>
  return <>
    <Link to="/discover" className="mb-4 inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-white"><ArrowLeft size={15}/> Back to discover</Link>
    <div className="relative mb-8 overflow-hidden rounded-3xl border border-white/8 bg-zinc-950">{movie.backdrop_url&&<><img src={movie.backdrop_url} alt="" decoding="async" className="absolute inset-0 h-full w-full object-cover opacity-30"/><div className="absolute inset-0 bg-gradient-to-r from-black via-black/80 to-black/30"/></>}<div className="relative grid gap-6 p-6 sm:p-8 md:grid-cols-[220px_1fr]">{movie.poster_url?<img src={movie.poster_url} alt={`${movie.title} poster`} decoding="async" className="w-full max-w-[220px] rounded-2xl shadow-2xl"/>:<div className="grid aspect-[2/3] max-w-[220px] place-items-center rounded-2xl bg-white/5 text-sm text-zinc-600">No poster</div>}<div className="self-end"><div className="flex flex-wrap items-center gap-2">{movie.category&&<Pill>{movie.category}</Pill>}{movie.watched&&<Pill>Watched</Pill>}{movie.watchlist&&<Pill>On watchlist</Pill>}{movie.user_rating!=null&&<Pill>Your rating · {movie.user_rating}/5</Pill>}</div><h1 className="mt-3 font-display text-4xl font-bold sm:text-5xl">{movie.title}</h1>{movie.original_title&&movie.original_title!==movie.title&&<div className="mt-1 text-sm text-zinc-500">Original title: {movie.original_title}</div>}<div className="mt-3 flex flex-wrap gap-3 text-sm text-zinc-400"><span>{movie.year??'—'}</span><span className="flex items-center gap-1"><Clock3 size={14}/>{runtime(movie.runtime)}</span>{movie.letterboxd_rating!=null&&(movie.letterboxd_url?<a className="inline-flex items-center gap-1 hover:text-white" href={movie.letterboxd_url} target="_blank" rel="noreferrer"><Star size={14}/>{movie.letterboxd_rating.toFixed(2)}/5 Letterboxd <ExternalLink size={12}/></a>:<span className="flex items-center gap-1"><Star size={14}/>{movie.letterboxd_rating.toFixed(2)}/5 Letterboxd</span>)}{movie.community_rating!=null&&movie.community_source&&movie.community_source!=='Letterboxd'&&<span className="text-zinc-500">{movie.community_rating.toFixed(2)}/5 {movie.community_source}{movie.community_rating_count?` · ${movie.community_rating_count.toLocaleString()} ratings`:''}</span>}{movie.vote_average!=null&&movie.community_source!=='TMDB'&&<span className="text-zinc-500">{movie.vote_average.toFixed(1)}/10 TMDB{movie.vote_count?` · ${movie.vote_count.toLocaleString()} votes`:''}</span>}</div><div className="mt-4 flex flex-wrap gap-2">{movie.genres?.map(g=><Pill key={g}>{g}</Pill>)}</div><p className="mt-5 max-w-3xl leading-7 text-zinc-300">{movie.overview||'No overview is cached for this title yet.'}</p></div></div></div>
    <div className="mb-8 grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <Card className="p-5"><div className="flex items-center gap-4"><ScoreRing score={movie.match_score}/><div><div className="text-xs uppercase tracking-wider text-zinc-500">Personal match</div><div className="mt-1 text-2xl font-bold">{rating(movie.predicted_rating)} / 5 <span className="text-sm font-normal text-zinc-500">· {movie.confidence??'Unknown'} confidence</span></div><div className="mt-1 text-xs text-zinc-500">The 0–100 score is smoothly calibrated from your taste, negative signals and community reception.</div></div></div><dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 text-sm"><div><dt className="text-zinc-500">Director</dt><dd className="mt-1">{movie.director??'—'}</dd></div><div><dt className="text-zinc-500">Language</dt><dd className="mt-1">{movie.language??'—'}</dd></div><div><dt className="text-zinc-500">Countries</dt><dd className="mt-1">{movie.countries?.join(', ')||'—'}</dd></div><div><dt className="text-zinc-500">Letterboxd average</dt><dd className="mt-1">{movie.letterboxd_rating!=null?`${movie.letterboxd_rating.toFixed(2)} / 5${movie.letterboxd_rating_count?` · ${movie.letterboxd_rating_count.toLocaleString()} ratings`:''}`:'Not cached yet'}</dd></div><div><dt className="text-zinc-500">Popularity</dt><dd className="mt-1">{movie.popularity!=null?movie.popularity.toFixed(1):'—'}</dd></div>{movie.collection&&<div className="col-span-2"><dt className="text-zinc-500">Collection / franchise</dt><dd className="mt-1">{movie.collection}</dd></div>}</dl>{movie.actors?.length?<div className="mt-5"><div className="text-xs uppercase tracking-wider text-zinc-500">Cast</div><div className="mt-2 flex flex-wrap gap-2">{movie.actors.map(a=><Pill key={a}>{a}</Pill>)}</div></div>:null}</Card>
      <Card className="p-5"><div className="text-xs uppercase tracking-wider text-violet-300">Why it fits</div><p className="mt-2 leading-7 text-zinc-300">{movie.explanation||'There is not enough profile information to generate a strong explanation yet.'}</p>{movie.components&&<div className="mt-4 flex flex-wrap gap-2">{Object.entries(movie.components).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,v])=><Pill key={k}>{k.replaceAll('_',' ')} · {Math.round(v*100)}%</Pill>)}</div>}{caveats.length>0&&<div className="mt-5 border-t border-white/8 pt-4"><div className="text-xs uppercase tracking-wider text-zinc-500">Why it might not fit</div><p className="mt-2 text-sm leading-6 text-zinc-400">Your weakest current signals are {caveats.map(([k,v])=>`${k.replaceAll('_',' ')} (${Math.round(v*100)}%)`).join(' and ')}. These are model signals, not guarantees.</p></div>}</Card>
    </div>
    <section className="mb-8">
      <div className="mb-4 flex items-end justify-between gap-3"><div><div className="flex items-center gap-2 font-semibold"><MessageSquareText size={17}/> Reviews</div><p className="mt-1 text-xs text-zinc-500">Public TMDB user reviews, shown separately from your personal score.</p></div></div>
      {reviews.length>0?<div className="grid gap-4 lg:grid-cols-2">{reviews.map((review,index)=><Card key={review.id??`${review.author}-${index}`} className="p-5"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{review.author}</div><div className="mt-1 text-xs text-zinc-500">{reviewDate(review.created_at)??'Date unavailable'}{review.rating!=null?` · ${review.rating.toFixed(1)}/10`:''}</div></div>{review.url&&<a href={review.url} target="_blank" rel="noreferrer" className="text-zinc-500 hover:text-white" aria-label="Open full review"><ExternalLink size={16}/></a>}</div><p className="mt-4 whitespace-pre-line text-sm leading-6 text-zinc-300 line-clamp-[10]">{review.content}</p></Card>)}</div>:<Card className="p-6"><p className="text-sm text-zinc-500">{reviewsAvailable?'No TMDB user reviews are available for this movie yet.':'Reviews are unavailable for this title right now.'}</p></Card>}
    </section>
    {similar.length>0&&<MovieRail title="You may also like" subtitle="Calculated from MyBoxd semantic + metadata similarity, then personalized to your profile—not TMDB’s recommendation endpoint." movies={similar}/>} 
  </>
}
