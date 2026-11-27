import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { HomeRoute } from './App';

const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname + l.search}</div>; };

describe('HomeRoute', () => {
  beforeEach(() => { localStorage.clear(); });

  it('sends a signed-in user with a search to /hledat, keeping the query', async () => {
    localStorage.setItem('refresh_token', 'r');
    render(
      <MemoryRouter initialEntries={['/?q=kure']}>
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/hledat" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('where')).toHaveTextContent('/hledat?q=kure');
  });
});
