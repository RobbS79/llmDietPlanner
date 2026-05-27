import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { isAccessTokenValid, tryRefreshToken } from '@/lib/auth';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

export const ProtectedRoute = ({ children }: { children: any }) => {
  const [state, setState] = useState<'checking' | 'ok' | 'denied'>(
    isAccessTokenValid() ? 'ok' : 'checking',
  );

  useEffect(() => {
    if (state !== 'checking') return;
    tryRefreshToken().then((ok) => setState(ok ? 'ok' : 'denied'));
  }, [state]);

  if (state === 'checking') return <LoadingScreen message="Ověřování..." />;
  if (state === 'denied') return <Navigate to="/login" replace />;
  return children;
};
