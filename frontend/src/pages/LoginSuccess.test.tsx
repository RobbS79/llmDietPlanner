import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { LoginSuccess } from './LoginSuccess';

const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname + l.search}</div>; };
const mount = () => render(
  <MemoryRouter initialEntries={['/login/success?access=a&refresh=r']}>
    <Routes>
      <Route path="/login/success" element={<LoginSuccess />} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
);

describe('LoginSuccess return routing', () => {
  beforeEach(() => localStorage.clear());

  it('returns to the list when the signup sheet asked for it, once', async () => {
    localStorage.setItem('uvarto.return.v1', '/nakup');
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent('/nakup?vitej=1');
    expect(localStorage.getItem('uvarto.return.v1')).toBeNull();
  });

  it('goes home otherwise', async () => {
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/);
  });

  it('ignores any other stored return value', async () => {
    localStorage.setItem('uvarto.return.v1', 'https://evil.example');
    mount();
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/);
  });
});
