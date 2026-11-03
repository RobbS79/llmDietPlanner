import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SignupSheet } from './SignupSheet';

describe('SignupSheet', () => {
  it('leads with Google and reassures', () => {
    render(<MemoryRouter><SignupSheet thumbs={['/a.webp']} onClose={() => {}} /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Pokračovat přes Google/ })).toBeInTheDocument();
    expect(screen.getByText('Zdarma, bez karty. První 2 plány máš u nás zadarmo.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nebo e-mailem' })).toHaveAttribute('href', '/login?mode=register&next=/nakup');
  });
});
