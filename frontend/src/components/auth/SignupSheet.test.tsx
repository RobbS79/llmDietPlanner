import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { RETURN_KEY } from '@/lib/storageKeys';
import { SignupSheet } from './SignupSheet';

const mount = (props: Partial<Parameters<typeof SignupSheet>[0]> = {}) =>
  render(<MemoryRouter><SignupSheet thumbs={['/a.webp']} onClose={() => {}} {...props} /></MemoryRouter>);

describe('SignupSheet', () => {
  beforeEach(() => { localStorage.clear(); });

  it('leads with Google and reassures', () => {
    mount();
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Pokračovat přes Google/ })).toBeInTheDocument();
    expect(screen.getByText('Zdarma, bez karty. První 2 plány máš u nás zadarmo.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nebo e-mailem' })).toHaveAttribute('href', '/login?mode=register&next=%2Fnakup');
  });

  it('carries the plan return intent to email and Google', async () => {
    mount({ returnTo: '/hledat?plan=1' });
    expect(screen.getByRole('link', { name: 'Nebo e-mailem' })).toHaveAttribute('href', '/login?mode=register&next=%2Fhledat%3Fplan%3D1');
    await userEvent.click(screen.getByRole('button', { name: /Pokračovat přes Google/ }));
    expect(JSON.parse(localStorage.getItem(RETURN_KEY)!).path).toBe('/hledat?plan=1');
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    mount({ onClose });
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('moves focus in and keeps Tab inside the dialog', async () => {
    mount();
    const google = screen.getByRole('button', { name: /Pokračovat přes Google/ });
    expect(google).toHaveFocus();
    screen.getByRole('button', { name: 'Teď ne' }).focus();
    await userEvent.tab();
    expect(google).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Teď ne' })).toHaveFocus();
  });
});
