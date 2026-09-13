import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { BarChart3, BrainCircuit, Clapperboard, Compass, Dice5, Dna, FlaskConical, ListVideo, LogOut, Menu, Search, Settings, Skull, UploadCloud, Users, WandSparkles, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const nav = [
  ['Dashboard', '/dashboard', Clapperboard],
  ['Discover', '/discover', Compass],
  ['Watch Tonight', '/tonight', WandSparkles],
  ['Movie Search', '/search', Search],
  ['Watchlist', '/watchlist', ListVideo],
  ['Movies You’d Hate', '/hate', Skull],
  ['Roulette', '/roulette', Dice5],
  ['Taste DNA', '/taste-dna', Dna],
  ['Stats', '/stats', BarChart3],
  ['Evaluation', '/evaluation', FlaskConical],
  ['Compare', '/compare', Users],
] as const

function NavItems({onNavigate}:{onNavigate?:()=>void}){return <nav className="space-y-1">{nav.map(([label,path,Icon])=><NavLink onClick={onNavigate} key={path} to={path} className={({isActive})=>`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${isActive?'bg-white/10 text-white':'text-zinc-400 hover:bg-white/5 hover:text-white'}`}><Icon size={17}/><span>{label}</span></NavLink>)}</nav>}

function FooterLinks({onNavigate,onLogout}:{onNavigate?:()=>void,onLogout:()=>void}){return <div className="space-y-1 border-t border-white/8 pt-3"><NavLink onClick={onNavigate} to="/import" className="flex min-h-10 items-center gap-2 rounded-xl px-3 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"><UploadCloud size={15}/> Import data</NavLink><NavLink onClick={onNavigate} to="/settings" className="flex min-h-10 items-center gap-2 rounded-xl px-3 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"><Settings size={15}/> Settings</NavLink><button onClick={onLogout} className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-xs text-zinc-400 hover:bg-white/5 hover:text-white"><LogOut size={15}/> Logout</button></div>}

export default function Layout(){
  const {user,logout}=useAuth(); const navigate=useNavigate(); const [mobile,setMobile]=useState(false)
  const doLogout=async()=>{await logout();navigate('/')}
  return <div className="min-h-screen bg-[#08090c] text-zinc-100">
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-white/8 bg-[#0b0d11]/95 backdrop-blur lg:flex lg:flex-col">
      <div className="shrink-0 p-5 pb-3"><NavLink to="/dashboard" className="flex items-center gap-3 px-2"><div className="grid h-10 w-10 place-items-center rounded-2xl bg-white text-zinc-950"><BrainCircuit size={22}/></div><div className="font-display text-xl font-bold tracking-tight">MyBoxd</div></NavLink></div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3"><NavItems/></div>
      <div className="shrink-0 bg-[#0b0d11] p-5 pt-3"><FooterLinks onLogout={doLogout}/><div className="mt-3 border-t border-white/8 px-3 pt-3"><div className="truncate text-xs font-medium text-zinc-300">{user?.name}</div><div className="truncate text-[11px] text-zinc-600">{user?.email}</div></div></div>
    </aside>
    <header className="sticky top-0 z-30 flex min-h-14 items-center justify-between border-b border-white/8 bg-[#08090c]/90 px-4 backdrop-blur lg:hidden"><NavLink to="/dashboard" className="flex items-center gap-2 font-bold"><BrainCircuit size={20}/> MyBoxd</NavLink><button className="grid h-10 w-10 place-items-center rounded-xl border border-white/8" aria-label="Open navigation" onClick={()=>setMobile(true)}><Menu size={19}/></button></header>
    {mobile&&<div className="fixed inset-0 z-50 bg-black/65 backdrop-blur-sm lg:hidden" onClick={()=>setMobile(false)}><div className="ml-auto flex h-full w-[min(86vw,340px)] flex-col border-l border-white/10 bg-[#0b0d11] p-5" onClick={e=>e.stopPropagation()}><div className="mb-4 flex shrink-0 items-center justify-between"><div className="font-display text-lg font-bold">MyBoxd</div><button className="grid h-10 w-10 place-items-center rounded-xl border border-white/8" aria-label="Close navigation" onClick={()=>setMobile(false)}><X size={18}/></button></div><div className="min-h-0 flex-1 overflow-y-auto"><NavItems onNavigate={()=>setMobile(false)}/></div><div className="shrink-0 pt-4"><FooterLinks onNavigate={()=>setMobile(false)} onLogout={doLogout}/></div></div></div>}
    <main className="min-h-screen lg:pl-64"><div className="mx-auto max-w-[1500px] p-4 sm:p-6 lg:p-8"><Outlet/></div></main>
  </div>
}
