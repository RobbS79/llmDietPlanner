import { StrictMode } from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { RETURN_KEY } from '@/lib/storageKeys';
import { RETURN_MAX_AGE_MS, setReturnIntent } from '@/lib/returnIntent';
import { LoginSuccess } from './LoginSuccess';

const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname + l.search}</div>; };
const mount = (strict = false) => {
  const tree = (
    <MemoryRouter initialEntries={['/login/success?access=a&refresh=r']}>
      <Routes>
        <Route path="/login/success" element={<LoginSuccess />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
};

describe('LoginSuccess return routing', () => {
  beforeEach(() => { localStorage.clear(); });

  it('returns to the list when the signup sheet asked for it, once', async () => {
    setReturnIntent('/nakup');
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent('/nakup?vitej=1');
    expect(localStorage.getItem(RETURN_KEY)).toBeNull();
  });

  it('returns to the search with the plan sheet when a plan was started signed out', async () => {
    setReturnIntent('/hledat?plan=1');
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent('/hledat?plan=1');
  });

  it('goes home otherwise', async () => {
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/);
  });

  it('ignores any other stored return value', async () => {
    localStorage.setItem(RETURN_KEY, JSON.stringify({ path: 'https://evil.example', ts: Date.now() }));
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/);
  });

  it('ignores a stale return intent', async () => {
    localStorage.setItem(RETURN_KEY, JSON.stringify({ path: '/nakup', ts: Date.now() - RETURN_MAX_AGE_MS - 1000 }));
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/);
  });

  it('navigates once under Strict Mode, keeping the intent for the real run', async () => {
    setReturnIntent('/nakup');
    mount(true);
    expect(await screen.findByTestId('where')).toHaveTextContent('/nakup?vitej=1');
  });
});
