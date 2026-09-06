import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MealSideLine } from './MealSideLine';

describe('MealSideLine', () => {
  it('renders "s chlebem · 2 krajíce"', () => {
    render(<MealSideLine side={{ key: 'chleb', name_cs: 'chléb', with_cs: 's chlebem', display: '2 krajíce' }} />);
    expect(screen.getByText(/s chlebem/)).toBeInTheDocument();
    expect(screen.getByText(/2 krajíce/)).toBeInTheDocument();
  });

  it('renders nothing without a side', () => {
    const { container } = render(<MealSideLine side={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
