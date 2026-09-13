import { useState } from 'react'
import { CheckCircle2, FileArchive, LoaderCircle, LockKeyhole, UploadCloud } from 'lucide-react'
import { api } from '../services/api'
import { Card, PageHeader } from '../components/UI'

type ImportResult={
  movies:number;movies_created:number;rows_processed:number;mode:'merge'|'replace';
  tmdb_enriched:number;tmdb_unmatched:number;source_files:string[];errors:string[];warnings:string[];
  metadata_total:number;metadata_enriched_total:number;metadata_remaining:number;metadata_unmatched_total:number
}
type EnrichResult={
  enriched:number;unmatched:number;metadata_total:number;metadata_enriched_total:number;
  metadata_remaining:number;metadata_unmatched_total:number;warning?:string|null
}
const labels=['Uploading & validating files','Parsing Letterboxd data','Matching every film with TMDB metadata','Rebuilding your taste profile']

export default function ImportData(){
  const [files,setFiles]=useState<File[]>([])
  const [mode,setMode]=useState<'merge'|'replace'>('merge')
  const [busy,setBusy]=useState(false)
  const [result,setResult]=useState<ImportResult|null>(null)
  const [error,setError]=useState('')
  const [progress,setProgress]=useState('')

  const run=async()=>{
    if(!files.length)return
    setBusy(true); setError(''); setResult(null); setProgress('Uploading and parsing your Letterboxd export…')
    try{
      const status=await api.get<{tmdb_configured:boolean}>('/settings')
      if(!status.tmdb_configured){
        throw new Error('TMDB is not configured yet. Add TMDB_API_KEY on the server and restart MyBoxd before importing so your full library can be analyzed automatically.')
      }
      const initial=await api.upload<ImportResult>('/import',files,{mode})
      let merged={...initial}
      setProgress(`Metadata: ${merged.metadata_enriched_total}/${merged.metadata_total} matched so far…`)

      // Continue in bounded requests until every imported title has been attempted.
      // This avoids the old “first ~120 movies only” bug and is safer for hosted APIs
      // than one giant multi-minute request.
      let guard=0
      while(merged.metadata_remaining>0 && guard<50){
        guard++
        const batch=await api.post<EnrichResult>('/movies/enrich?limit=120')
        merged={
          ...merged,
          tmdb_enriched:merged.tmdb_enriched+batch.enriched,
          tmdb_unmatched:merged.tmdb_unmatched+batch.unmatched,
          metadata_total:batch.metadata_total,
          metadata_enriched_total:batch.metadata_enriched_total,
          metadata_remaining:batch.metadata_remaining,
          metadata_unmatched_total:batch.metadata_unmatched_total,
          warnings:batch.warning?[...merged.warnings,batch.warning]:merged.warnings,
        }
        setProgress(`Metadata: ${merged.metadata_enriched_total}/${merged.metadata_total} matched · ${merged.metadata_remaining} still to attempt…`)
        if(batch.warning)break
      }
      setResult(merged); setFiles([])
      setProgress('')
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }

  return <>
    <PageHeader eyebrow="Private data import" title="Import Letterboxd" subtitle="Upload the full Letterboxd export ZIP or common CSV files. MyBoxd automatically works through the complete library in safe TMDB batches—visitors never need terminal commands."/>
    <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
      <Card className="p-6">
        <label className="grid min-h-64 cursor-pointer place-items-center rounded-2xl border border-dashed border-white/15 bg-black/15 p-8 text-center transition hover:border-white/25 hover:bg-white/[.02]">
          <div><UploadCloud className="mx-auto text-zinc-400" size={32}/><div className="mt-4 font-semibold">Choose Letterboxd files</div><p className="mt-2 text-sm text-zinc-500">ZIP or ratings.csv, watched.csv, watchlist.csv, diary.csv and reviews.csv</p><input className="hidden" type="file" multiple accept=".zip,.csv,text/csv,application/zip" onChange={e=>setFiles(Array.from(e.target.files??[]))}/></div>
        </label>
        {files.length>0&&<div className="mt-4 rounded-2xl border border-white/8 bg-white/[.02] p-4"><div className="mb-2 text-xs uppercase tracking-wider text-zinc-500">Selected</div>{files.map(f=><div key={`${f.name}-${f.size}`} className="flex items-center gap-2 py-1.5 text-sm text-zinc-300"><FileArchive size={15} className="text-zinc-500"/><span className="truncate">{f.name}</span><span className="ml-auto text-xs text-zinc-600">{(f.size/1024/1024).toFixed(1)} MB</span></div>)}</div>}
        <fieldset className="mt-4 grid grid-cols-2 gap-2" disabled={busy}>
          {([['merge','Merge','Keep existing valid records and update overlapping titles.'],['replace','Replace','Reset your private movie data only after this upload parses successfully.']] as const).map(([value,title,body])=><label key={value} className={`cursor-pointer rounded-xl border p-3 ${mode===value?'border-violet-400/40 bg-violet-400/10':'border-white/8 bg-white/[.02]'}`}><input className="sr-only" type="radio" name="import-mode" value={value} checked={mode===value} onChange={()=>setMode(value)}/><div className="text-sm font-semibold">{title}</div><div className="mt-1 text-xs leading-4 text-zinc-500">{body}</div></label>)}
        </fieldset>
        <button onClick={run} disabled={!files.length||busy} className="btn btn-primary mt-4 w-full py-3 disabled:opacity-40">{busy?<><LoaderCircle className="animate-spin" size={16}/> Analyzing…</>:'Import & analyze'}</button>
        {busy&&progress&&<p className="mt-3 text-center text-xs text-zinc-500">{progress}</p>}
        {error&&<div role="alert" className="mt-4 rounded-xl border border-amber-400/15 bg-amber-400/5 p-3 text-sm text-amber-200">{error}</div>}
      </Card>
      <div className="space-y-5">
        <Card className="p-5"><div className="flex items-center gap-2 text-sm font-semibold"><LockKeyhole size={16} className="text-emerald-300"/> Privacy model</div><p className="mt-2 text-sm leading-6 text-zinc-500">Uploaded bytes are processed in memory; MyBoxd stores normalized viewing data in your private account records and does not keep the raw export as a public file.</p></Card>
        <Card className="p-5"><div className="text-xs uppercase tracking-[.2em] text-zinc-500">Import pipeline</div><div className="mt-4 space-y-3">{labels.map(label=><div key={label} className={`flex items-center gap-3 text-sm ${result?'text-zinc-100':busy?'text-zinc-300':'text-zinc-600'}`}>{result?<CheckCircle2 size={17} className="text-emerald-300"/>:busy?<LoaderCircle size={16} className="animate-spin text-violet-300"/>:<span className="h-4 w-4 rounded-full border border-white/10"/>}{label}</div>)}</div>{busy&&<p className="mt-4 text-xs leading-5 text-zinc-500">Large libraries can take several minutes because MyBoxd checks TMDB in safe batches. Leave this page open; the app continues automatically.</p>}</Card>
        {result&&<Card className="p-5"><div className="text-xs uppercase tracking-[.2em] text-emerald-300">Import complete · {result.mode}</div><div className="mt-3 grid grid-cols-2 gap-3 text-sm"><div><span className="text-zinc-500">Movies</span><div className="text-xl font-bold">{result.movies}</div></div><div><span className="text-zinc-500">TMDB metadata</span><div className="text-xl font-bold">{result.metadata_enriched_total}/{result.metadata_total}</div></div><div><span className="text-zinc-500">Rows read</span><div className="text-xl font-bold">{result.rows_processed}</div></div><div><span className="text-zinc-500">No confident TMDB match</span><div className="text-xl font-bold">{result.metadata_unmatched_total}</div></div></div>{result.errors?.length>0&&<details className="mt-4 text-xs text-zinc-500"><summary className="cursor-pointer">Show skipped/invalid rows</summary><ul className="mt-2 list-disc space-y-1 pl-4">{result.errors.slice(0,40).map((e,i)=><li key={`${i}-${e}`}>{e}</li>)}</ul></details>}{result.warnings?.length>0&&<p className="mt-4 text-xs leading-5 text-zinc-500">{result.warnings.join(' ')}</p>}</Card>}
      </div>
    </div>
  </>
}
