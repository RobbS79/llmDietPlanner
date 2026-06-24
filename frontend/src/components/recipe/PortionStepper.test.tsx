import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PortionStepper } from './PortionStepper';

describe('PortionStepper', () => {
  it('renders the count with the right Czech plural', () => {
    render(<PortionStepper value={5} onChange={() => {}} />);
    expect(screen.getByText(/5 porcí/)).toBeInTheDocument();
  });

  it('increments and decrements within bounds', async () => {
    const onChange = vi.fn();
    render(<PortionStepper value={4} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText('Více porcí'));
    expect(onChange).toHaveBeenLastCalledWith(5);
    await userEvent.click(screen.getByLabelText('Méně porcí'));
    expect(onChange).toHaveBeenLastCalledWith(3);
  });

  it('disables decrement at the minimum', () => {
    render(<PortionStepper value={1} onChange={() => {}} />);
    expect(screen.getByLabelText('Méně porcí')).toBeDisabled();
  });

  it('disables increment at the maximum', () => {
    render(<PortionStepper value={20} onChange={() => {}} />);
    expect(screen.getByLabelText('Více porcí')).toBeDisabled();
  });
});
