import { useState } from 'react'
import type { FormEvent } from 'react'
import { SlidersHorizontal, Sparkles } from 'lucide-react'
import type { Movie } from '../types'
import { api } from '../services/api'
import MovieRail from '../components/MovieRail'
import { Card, EmptyState, PageHeader } from '../components/UI'

type SliderKey='darkness'|'pace'|'experimental'|'mainstream'|'emotional_intensity'
type FormState={
  prompt:string;mood:string;max_runtime:number;min_runtime:number;genres:string;avoid:string;
  darkness:number;pace:number;experimental:number;mainstream:number;company:string;decade:string;
  language:string;country:string;emotional_intensity:number
}
const initial:FormState={prompt:'I have 2 hours and want something psychological and weird but not completely depressing.',mood:'',max_runtime:0,min_runtime:0,genres:'',avoid:'',darkness:50,pace:50,experimental:50,mainstream:50,company:'',decade:'',language:'',country:'',emotional_intensity:50}
function Slider({label,value,onChange,left,right,touched}:{label:string;value:number;onChange:(n:number)=>void;left:string;right:string;touched:boolean}){return <label className="block text-xs text-zinc-400"><div className="mb-1 flex justify-between"><span>{label}{!touched&&<span className="ml-1 text-zinc-600">(infer)</span>}</span><span className="text-zinc-600">{value}/100</span></div><input className="w-full accent-violet-400" type="range" min="0" max="100" value={value} onChange={e=>onChange(Number(e.target.value))}/><div className="mt-1 flex justify-between text-[10px] text-zinc-600"><span>{left}</span><span>{right}</span></div></label>}

export default function WatchTonight(){
  const [form,setForm]=useState<FormState>(initial)
  const [touched,setTouched]=useState<Partial<Record<SliderKey,boolean>>>({})
  const [movies,setMovies]=useState<Movie[]>([])
  const [interpreted,setInterpreted]=useState<Record<string,unknown>|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [searched,setSearched]=useState(false)
  const patch=<K extends keyof FormState>(key:K,value:FormState[K])=>setForm(x=>({...x,[key]:value}))
  const slider=(key:SliderKey,value:number)=>{patch(key,value);setTouched(x=>({...x,[key]:true}))}
  const submit=async(e:FormEvent)=>{
    e.preventDefault(); setBusy(true); setError(''); setSearched(true)
    try{
      const r=await api.post<{interpreted:Record<string,unknown>;recommendations:Movie[]}>('/recommendations/context',{
        prompt:form.prompt,mood:form.mood||null,max_runtime:form.max_runtime||null,min_runtime:form.min_runtime||null,
        genres:form.genres?form.genres.split(',').map(x=>x.trim()).filter(Boolean):[],avoid:form.avoid?form.avoid.split(',').map(x=>x.trim()).filter(Boolean):[],
        darkness:touched.darkness?form.darkness:null,pace:touched.pace?form.pace:null,experimental:touched.experimental?form.experimental:null,
        mainstream:touched.mainstream?form.mainstream:null,company:form.company||null,decade:form.decade?Number(form.decade):null,
        language:form.language||null,country:form.country||null,emotional_intensity:touched.emotional_intensity?form.emotional_intensity:null,limit:5,
      })
      setMovies(r.recommendations); setInterpreted(r.interpreted)
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <>
    <PageHeader eyebrow="Context-aware picks" title="What should I watch tonight?" subtitle="Describe the vibe naturally, then optionally add explicit constraints. Untouched controls are inferred from your sentence instead of silently overriding it."/>
    <Card className="mb-8 p-5 sm:p-6"><form onSubmit={submit} className="space-y-5"><textarea aria-label="Describe what you want to watch" className="input min-h-28 resize-y" value={form.prompt} onChange={e=>patch('prompt',e.target.value)} placeholder="Something beautiful and strange under two hours…"/><div className="grid gap-3 md:grid-cols-4"><label className="text-xs text-zinc-400">Mood<input className="input mt-1" value={form.mood} onChange={e=>patch('mood',e.target.value)} placeholder="reflective, tense…"/></label><label className="text-xs text-zinc-400">Min runtime<input className="input mt-1" type="number" min={0} max={400} value={form.min_runtime||''} onChange={e=>patch('min_runtime',Number(e.target.value)||0)} placeholder="Infer"/></label><label className="text-xs text-zinc-400">Max runtime<input className="input mt-1" type="number" min={30} max={400} value={form.max_runtime||''} onChange={e=>patch('max_runtime',Number(e.target.value)||0)} placeholder="Infer"/></label><label className="text-xs text-zinc-400">Watching with<select className="input mt-1" value={form.company} onChange={e=>patch('company',e.target.value)}><option value="">Infer / any</option><option value="alone">Alone</option><option value="family">Family</option><option value="friends">Friends</option></select></label></div><div className="grid gap-3 md:grid-cols-2"><label className="text-xs text-zinc-400">Genres <span className="text-zinc-600">(comma separated)</span><input className="input mt-1" value={form.genres} onChange={e=>patch('genres',e.target.value)} placeholder="Science Fiction, Mystery"/></label><label className="text-xs text-zinc-400">Movies/themes to avoid<input className="input mt-1" value={form.avoid} onChange={e=>patch('avoid',e.target.value)} placeholder="gore, musicals, grief"/></label></div><details className="rounded-2xl border border-white/8 bg-black/15 p-4"><summary className="cursor-pointer text-sm font-semibold text-zinc-300">Advanced vibe controls</summary><div className="mt-5 grid gap-6 md:grid-cols-2 xl:grid-cols-5"><Slider label="Tone" value={form.darkness} touched={!!touched.darkness} onChange={n=>slider('darkness',n)} left="Light" right="Dark"/><Slider label="Pace" value={form.pace} touched={!!touched.pace} onChange={n=>slider('pace',n)} left="Slow" right="Fast"/><Slider label="Familiarity" value={form.experimental} touched={!!touched.experimental} onChange={n=>slider('experimental',n)} left="Familiar" right="Experimental"/><Slider label="Popularity" value={form.mainstream} touched={!!touched.mainstream} onChange={n=>slider('mainstream',n)} left="Obscure" right="Mainstream"/><Slider label="Emotion" value={form.emotional_intensity} touched={!!touched.emotional_intensity} onChange={n=>slider('emotional_intensity',n)} left="Gentle" right="Intense"/></div><div className="mt-5 grid gap-3 md:grid-cols-4"><label className="text-xs text-zinc-400">Release decade<input className="input mt-1" value={form.decade} onChange={e=>patch('decade',e.target.value)} placeholder="1990"/></label><label className="text-xs text-zinc-400">Language code<input className="input mt-1" value={form.language} onChange={e=>patch('language',e.target.value)} placeholder="ja, en, fr"/></label><label className="text-xs text-zinc-400">Country<input className="input mt-1" value={form.country} onChange={e=>patch('country',e.target.value)} placeholder="Japan"/></label><div className="self-end text-[11px] leading-4 text-zinc-600">Family mode is a taste/context signal, not a content-rating guarantee.</div></div></details><button className="btn btn-primary" disabled={busy}><Sparkles size={16}/>{busy?'Finding your movie…':'Find 5 strong matches'}</button>{error&&<p role="alert" className="text-sm text-amber-300">{error}</p>}</form></Card>
    {interpreted&&<Card className="mb-8 p-4"><div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400"><SlidersHorizontal size={14}/> Rule parser interpretation</div><pre className="overflow-auto text-xs leading-5 text-zinc-500">{JSON.stringify(interpreted,null,2)}</pre></Card>}
    {movies.length>0?<MovieRail title="Tonight’s picks" subtitle="Ranked using both your constraints and your learned taste." movies={movies}/>:searched&&!busy&&!error?<EmptyState title="No strong match found" body="Try relaxing one constraint or removing an exclusion. MyBoxd will not invent a result that fails your filters."/>:null}
  </>
}
