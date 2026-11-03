import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { syncConsentToServer } from '@/lib/analytics';
import { getPendingPromo } from '@/lib/promo';
import { afterLoginPath, takeReturnIntent } from '@/lib/returnIntent';

export const LoginSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  // Strict Mode runs effects twice; the return intent is read-once, so act once.
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const access = params.get('access');
    const refresh = params.get('refresh');
    if (access && refresh) {
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      syncConsentToServer();
      const back = takeReturnIntent();
      navigate(getPendingPromo() ? '/pricing' : afterLoginPath(back), { replace: true });
    } else {
      navigate('/login?error=auth_failed');
    }
  }, [params, navigate]);

  return <LoadingScreen message="Signing you in..." />;
};
