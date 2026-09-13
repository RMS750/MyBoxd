import type { Movie } from '../types'
import MovieCard from './MovieCard'
import { EmptyState } from './UI'

export default function MovieRail({title, subtitle, movies}:{title:string,subtitle?:string,movies:Movie[]}) {
  return <section className="mb-8"><div className="mb-3"><h2 className="font-display text-xl font-semibold">{title}</h2>{subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}</div>{movies.length ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">{movies.slice(0,6).map((m) => <MovieCard key={m.id} movie={m}/>)}</div> : <EmptyState body="Import your Letterboxd data and enrich metadata to populate this section."/>}</section>
}
