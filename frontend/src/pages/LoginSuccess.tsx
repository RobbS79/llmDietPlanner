import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { syncConsentToServer } from '@/lib/analytics';

export const LoginSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const access = params.get('access');
    const refresh = params.get('refresh');
    if (access && refresh) {
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      syncConsentToServer();
      navigate('/', { replace: true });
    } else {
      navigate('/login?error=auth_failed');
    }
  }, [params, navigate]);

  return <LoadingScreen message="Signing you in..." />;
};
