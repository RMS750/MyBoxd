import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, setCsrfToken } from '../services/api'

export type Account = { id:number; name:string; email:string; created_at?:string|null; csrf_token?:string }
type AuthValue = {
  user: Account | null
  loading: boolean
  login: (email:string,password:string)=>Promise<void>
  register: (name:string,email:string,password:string)=>Promise<void>
  logout: ()=>Promise<void>
  refresh: ()=>Promise<void>
  setUser: (user:Account|null)=>void
}
const AuthContext=createContext<AuthValue|null>(null)

export function AuthProvider({children}:{children:ReactNode}){
  const [user,setUserState]=useState<Account|null>(null)
  const [loading,setLoading]=useState(true)
  const apply=(next:Account|null)=>{setUserState(next);setCsrfToken(next?.csrf_token)}
  const refresh=async()=>{try{const r=await api.get<{user:Account}>('/auth/me');apply(r.user)}catch(e){if(e instanceof ApiError&&e.status===401)apply(null);else throw e}}
  useEffect(()=>{refresh().catch(()=>apply(null)).finally(()=>setLoading(false));const onExpired=()=>apply(null);window.addEventListener('myboxd:session-expired',onExpired);return()=>window.removeEventListener('myboxd:session-expired',onExpired)},[])
  const login=async(email:string,password:string)=>{const r=await api.post<{user:Account}>('/auth/login',{email,password});apply(r.user)}
  const register=async(name:string,email:string,password:string)=>{const r=await api.post<{user:Account}>('/auth/register',{name,email,password});apply(r.user)}
  const logout=async()=>{try{await api.post('/auth/logout')}finally{apply(null)}}
  const setUser=(next:Account|null)=>apply(next)
  const value=useMemo(()=>({user,loading,login,register,logout,refresh,setUser}),[user,loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth(){const value=useContext(AuthContext);if(!value)throw new Error('useAuth must be used inside AuthProvider');return value}
