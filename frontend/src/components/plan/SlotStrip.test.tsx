import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlotStrip } from './SlotStrip';
import type { DayMealEntry } from '@/lib/planMeals';

const e = {} as DayMealEntry;

describe('SlotStrip', () => {
  it('one pill per section, anchored to the section id', () => {
    render(<SlotStrip sections={[
      { slot: 'breakfast', label: 'Snídaně', isMain: true, entries: [e] },
      { slot: 'dinner', label: 'Večeře', isMain: true, entries: [e, e, e] },
    ]} />);
    const links = screen.getAllByRole('link');
    expect(links.map(l => l.getAttribute('href'))).toEqual(['#slot-breakfast', '#slot-dinner']);
    expect(links[1]).toHaveTextContent('Večeře');
    expect(links[1]).toHaveTextContent('3');
  });

  it('renders nothing without sections', () => {
    const { container } = render(<SlotStrip sections={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
