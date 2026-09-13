import { useEffect, useState } from 'react'
import type { Movie } from '../types'
import { api } from '../services/api'
import MovieRail from '../components/MovieRail'
import { EmptyState, ErrorState, Loading, PageHeader } from '../components/UI'

type Feed={top:Movie[];safe:Movie[];gems:Movie[];wild:Movie[];anti:Movie[];candidate_count?:number;catalogue_backed?:boolean}

export default function Discover(){
  const [feed,setFeed]=useState<Feed|null>(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)
  useEffect(()=>{
    api.get<Feed>('/discover-feed')
      .then(setFeed)
      .catch((e:Error)=>setError(e.message))
      .finally(()=>setLoading(false))
  },[])

  if(loading)return <Loading text="Ranking your local movie catalogue…"/>
  const sections=feed??{top:[],safe:[],gems:[],wild:[],anti:[]}
  const nothing=[sections.top,sections.safe,sections.gems,sections.wild,sections.anti].every(rows=>rows.length===0)
  return <>
    <PageHeader title="Discover" subtitle="One ranking pass, five different jobs: best overall fits, safe bets, genuinely obscure high-match films, wild cards, and likely misses."/>
    {error&&<div className="mb-6"><ErrorState message={error}/></div>}
    {nothing&&!error&&<EmptyState title="No discovery pool yet" body="Import your Letterboxd history and install the local catalogue to populate discovery."/>}
    <MovieRail title="Top Matches" subtitle="Your highest personal match scores. Specialist rails no longer steal stronger films from this list." movies={sections.top}/>
    <MovieRail title="Safe Bets" subtitle="High-confidence films that score strongly against your personal baseline." movies={sections.safe}/>
    <MovieRail title="Hidden Gems" subtitle="Lower-popularity movies with strong personal-match scores and enough audience evidence to trust." movies={sections.gems}/>
    <MovieRail title="Wild Cards" subtitle="More novel choices that still have enough positive signal to be worth the risk." movies={sections.wild}/>
    <MovieRail title="Movies You’d Hate (probably)" subtitle="Low-fit picks driven by your negative history and public reception." movies={sections.anti}/>
  </>
}
