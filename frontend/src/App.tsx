import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
import { ToastProvider } from '@/components/ui/Toast';

const queryClient = new QueryClient();

function HomeRoute() {
  if (localStorage.getItem('access_token')) return <Dashboard />;
  return <Landing />;
}

export default function App() {
  return (
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
          <Route path="/" element={<HomeRoute />} />
          <Route path="/create" element={<ProtectedRoute><CreatePlan /></ProtectedRoute>} />
          <Route path="/plan/:id" element={<ProtectedRoute><PlanView /></ProtectedRoute>} />
          <Route path="/plan/:id/recipe/:mealId" element={<ProtectedRoute><RecipePage /></ProtectedRoute>} />
          <Route path="/plan/:id/shopping-list" element={<ProtectedRoute><ShoppingListPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
