import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from '@/components/ui/Toast';
import { Landing } from '@/pages/Landing';
import { Login } from '@/pages/Login';
import { Pricing } from '@/pages/Pricing';
import { Privacy } from '@/pages/Privacy';
import { Terms } from '@/pages/Terms';
import { ForgotPassword } from '@/pages/ForgotPassword';

export function render(url: string): string {
  const queryClient = new QueryClient();

  const html = renderToString(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <StaticRouter location={url}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/" element={<Landing />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </StaticRouter>
      </ToastProvider>
    </QueryClientProvider>
  );

  return html;
}
