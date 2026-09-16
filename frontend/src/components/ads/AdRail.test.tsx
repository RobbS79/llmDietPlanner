import { describe, it, expect, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { AdRail } from './AdRail';

afterEach(() => vi.unstubAllEnvs());

describe('AdRail', () => {
  it('renders nothing while ads are not enabled (no contract yet)', () => {
    vi.stubEnv('VITE_ADS_ENABLED', '');
    const { container } = render(<AdRail slot="plan-right" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('reserves a 300px-wide rail with a named slot when enabled', () => {
    vi.stubEnv('VITE_ADS_ENABLED', 'true');
    const { container } = render(<AdRail slot="plan-right" />);
    const aside = container.querySelector('aside');
    expect(aside).not.toBeNull();
    expect(aside!.querySelector('[data-ad-slot="plan-right"]')).not.toBeNull();
    expect(aside!.className).toContain('w-[300px]');
  });
});
