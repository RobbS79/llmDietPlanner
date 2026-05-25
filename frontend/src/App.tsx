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

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/login-success" element={<LoginSuccess />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/create" element={<ProtectedRoute><CreatePlan /></ProtectedRoute>} />
          <Route path="/plan/:id" element={<ProtectedRoute><PlanView /></ProtectedRoute>} />
          <Route path="/plan/:id/recipe/:mealId" element={<ProtectedRoute><RecipePage /></ProtectedRoute>} />
          <Route path="/plan/:id/shopping-list" element={<ProtectedRoute><ShoppingListPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
