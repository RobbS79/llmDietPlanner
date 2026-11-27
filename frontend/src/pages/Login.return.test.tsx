import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RETURN_KEY } from '@/lib/storageKeys';
import { setReturnIntent } from '@/lib/returnIntent';
import { Login } from './Login';

const mount = (path: string) => render(
  <QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><Login /></MemoryRouter></QueryClientProvider>);

describe('Login return intent', () => {
  beforeEach(() => { localStorage.clear(); });

  it('drops a leftover return intent when opened without next', () => {
    setReturnIntent('/nakup');
    mount('/login');
    expect(localStorage.getItem(RETURN_KEY)).toBeNull();
  });

  it('keeps an allowlisted next as the intent, so Google returns there too', () => {
    mount('/login?mode=register&next=%2Fhledat%3Fplan%3D1');
    expect(JSON.parse(localStorage.getItem(RETURN_KEY)!).path).toBe('/hledat?plan=1');
  });
});
