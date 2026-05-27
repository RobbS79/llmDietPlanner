import { Component, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { Dashboard } from '@/pages/Dashboard';
import { CreatePlan } from '@/pages/CreatePlan';
import { PlanView } from '@/pages/PlanView';
import { RecipePage } from '@/pages/RecipePage';
import { ShoppingListPage } from '@/pages/ShoppingListPage';
import { Login } from '@/pages/Login';
import { LoginSuccess } from '@/pages/LoginSuccess';
import { ForgotPassword } from '@/pages/ForgotPassword';
import { ResetPassword } from '@/pages/ResetPassword';
import { Landing } from '@/pages/Landing';
import { Privacy } from '@/pages/Privacy';
import { Terms } from '@/pages/Terms';
import { Pricing } from '@/pages/Pricing';
import { RecipeIndexPage } from '@/pages/RecipeIndexPage';
import { PublicRecipePage } from '@/pages/PublicRecipePage';
import { Onboarding } from '@/pages/Onboarding';
import { ToastProvider } from '@/components/ui/Toast';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { api } from '@/lib/api';
import { isAccessTokenValid } from '@/lib/auth';
import { AlertCircle } from 'lucide-react';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: any) { console.error('React crash:', error, info.componentStack); }
  render() {
    if (this.state.error) return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#09090b] text-white min-h-screen">
        <AlertCircle size={48} className="text-rose-500 mb-6" />
        <h1 className="text-3xl font-black tracking-tighter uppercase mb-4 italic">Něco se pokazilo<span className="text-rose-600 not-italic">.</span></h1>
        <p className="text-zinc-500 mb-2 text-sm max-w-md">{this.state.error.message}</p>
        <button onClick={() => { this.setState({ error: null }); window.location.href = '/'; }} className="mt-8 px-10 h-14 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl">Zpět na hlavní stránku</button>
      </div>
    );
    return this.props.children;
  }
}

const queryClient = new QueryClient();

function HomeRoute() {
  if (!isAccessTokenValid() && !localStorage.getItem('refresh_token')) return <Landing />;
  return <AuthenticatedHome />;
}

function AuthenticatedHome() {
  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/auth/profile/').then(res => res.data.data),
  });

  if (isLoading) return <LoadingScreen message="Nacitani..." />;
  if (profile && !profile.onboarding_completed) return <Navigate to="/onboarding" replace />;
  return <Dashboard />;
}

export default function App() {
  return (
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/login-success" element={<LoginSuccess />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/recepty" element={<RecipeIndexPage />} />
          <Route path="/recepty/:id/:slug" element={<PublicRecipePage />} />
          <Route path="/" element={<HomeRoute />} />
          <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
          <Route path="/create" element={<ProtectedRoute><CreatePlan /></ProtectedRoute>} />
          <Route path="/plan/:id" element={<ProtectedRoute><PlanView /></ProtectedRoute>} />
          <Route path="/plan/:id/recipe/:mealId" element={<ProtectedRoute><RecipePage /></ProtectedRoute>} />
          <Route path="/plan/:id/shopping-list" element={<ProtectedRoute><ShoppingListPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  );
}
