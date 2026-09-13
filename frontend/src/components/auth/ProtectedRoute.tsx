import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { Loading } from '../UI'
export default function ProtectedRoute(){const {user,loading}=useAuth();const location=useLocation();if(loading)return <div className="min-h-screen bg-[#08090c] text-zinc-100"><Loading text="Restoring your MyBoxd session…"/></div>;if(!user)return <Navigate to="/login" state={{from:location.pathname}} replace/>;return <Outlet/>}
