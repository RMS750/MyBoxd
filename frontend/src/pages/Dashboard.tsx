import { useEffect, useState } from 'react'
import { ArrowRight, Dice5, LockKeyhole, Sparkles, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Movie, RecommendationResponse, Stats, TasteDNA } from '../types'
import { api } from '../services/api'
import { useAuth } from '../context/AuthContext'
import MovieRail from '../components/MovieRail'
import { Card, ErrorState, Loading, PageHeader, Stat } from '../components/UI'

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState<Stats | null>(null)
  const [dna, setDna] = useState<TasteDNA | null>(null)
  const [recs, setRecs] = useState<Movie[]>([])
  const [gems, setGems] = useState<Movie[]>([])
  const [watch, setWatch] = useState<Movie[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      // Keep the first authenticated render fast. Recommendation discovery can
      // involve TMDB work, so it loads only after the basic dashboard is visible.
      const [s, d, w] = await Promise.all([
        api.get<Stats>('/stats'),
        api.get<TasteDNA>('/profile/taste-dna'),
        api.get<RecommendationResponse>('/watchlist/ranked'),
      ])
      setStats(s)
      setDna(d)
      setWatch(w.recommendations)
      setLoading(false)

      if ((s.total_watched ?? 0) > 0) {
        void api.get<{top:Movie[];gems:Movie[]}>('/discover-feed')
          .then((feed) => {
            setRecs(feed.top.slice(0,12))
            setGems(feed.gems.slice(0,6))
          })
          .catch((e: Error) => setError(e.message))
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  if (loading) return <Loading text="Loading your dashboard…" />
  const empty = (stats?.total_watched ?? 0) === 0

  return <>
    <PageHeader
      eyebrow="Your movie mind"
      title={`Welcome back${user?.name ? `, ${user.name.split(' ')[0]}` : ''}`}
      subtitle="A living model of what you watch, what you love, and what you are most likely to enjoy next."
      actions={<Link to="/roulette" className="btn btn-secondary"><Dice5 size={16}/> Movie Roulette</Link>}
    />
    {error && <div className="mb-5"><ErrorState message={error}/></div>}

    {empty && <Card className="mb-8 overflow-hidden p-6 sm:p-8">
      <div className="grid gap-6 md:grid-cols-[1.2fr_.8fr] md:items-center">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs text-violet-200"><Sparkles size={13}/> Build your taste model</div>
          <h2 className="font-display text-2xl font-bold sm:text-3xl">Start with your Letterboxd export.</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-zinc-400">Use the dedicated import flow so MyBoxd can validate your files, match the full library with TMDB, and build your private taste model without leaving metadata half-finished.</p>
          <div className="mt-4 flex items-center gap-2 text-xs text-emerald-300"><LockKeyhole size={14}/> Your Letterboxd data is private to your account.</div>
        </div>
        <div className="rounded-2xl border border-dashed border-white/15 bg-black/20 p-5 text-center">
          <UploadCloud className="mx-auto mb-3 text-zinc-400"/>
          <div className="font-semibold">Import Letterboxd</div>
          <div className="mt-1 text-xs text-zinc-500">ZIP or CSV export files</div>
          <Link to="/import" className="btn btn-primary mt-4 w-full">Open importer</Link>
        </div>
      </div>
    </Card>}

    {!empty && <>
      <div className="mb-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Watched" value={stats?.total_watched ?? 0}/>
        <Stat label="Average rating" value={`${stats?.average_rating ?? '—'} / 5`}/>
        <Stat label="5-star films" value={`${stats?.five_star_percentage ?? 0}%`}/>
        <Stat label="Taste signal" value={dna?.dimensions?.psychological != null ? `${dna.dimensions.psychological}/100` : 'Ready'} hint="Psychological dimension"/>
      </div>
      {dna?.summary && <Card className="mb-8 overflow-hidden p-6">
        <div className="flex items-start justify-between gap-5">
          <div>
            <div className="mb-2 text-xs uppercase tracking-[.2em] text-violet-300">Taste DNA</div>
            <p className="max-w-4xl font-display text-xl leading-8 text-zinc-100">“{dna.summary}”</p>
          </div>
          <Link to="/taste-dna" className="btn btn-secondary shrink-0">Explore <ArrowRight size={15}/></Link>
        </div>
      </Card>}
      <MovieRail title="Top recommendations" subtitle="Highest-scoring unseen movies from your hybrid taste model." movies={recs}/>
      <MovieRail title="Hidden gems" subtitle="Strong matches with a lower popularity profile." movies={gems}/>
      <MovieRail title="Watchlist picks" subtitle="Your existing watchlist, ranked by predicted enjoyment." movies={watch}/>
    </>}
  </>
}
