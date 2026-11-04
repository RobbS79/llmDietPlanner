import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TurnstileGate } from './TurnstileGate';

describe('TurnstileGate', () => {
  afterEach(() => { vi.unstubAllEnvs(); delete window.turnstile; });

  it('says it cannot verify instead of showing an empty box when the bundle has no site key', () => {
    vi.stubEnv('VITE_TURNSTILE_SITE_KEY', '');
    render(<TurnstileGate onToken={() => {}} />);
    expect(screen.getByText('Teď to nejde ověřit. Zkus to prosím za chvíli.')).toBeInTheDocument();
    expect(screen.queryByText(/nejsi robot/)).toBeNull();
  });

  it('renders the widget with the site key', () => {
    vi.stubEnv('VITE_TURNSTILE_SITE_KEY', 'site-key');
    const renderWidget = vi.fn();
    window.turnstile = { render: renderWidget };
    render(<TurnstileGate onToken={() => {}} />);
    expect(screen.getByText('Jen rychlé ověření, že nejsi robot.')).toBeInTheDocument();
    expect(renderWidget).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ sitekey: 'site-key' }));
  });
});
