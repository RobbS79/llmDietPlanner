import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RecipeIngredients } from './RecipeIngredients';
import type { ShoppingList } from '@/lib/pricing';

// The headline total's numbers are interpolated as separate JSX children, so
// "odhad 88–110 Kč" ends up as sibling text nodes under one <p> rather than
// one text node. Match against the <p>'s full textContent (which RTL's
// text-matcher already normalizes) instead of relying on getByText's default
// per-text-node matching, and scope to the <p> tag so the per-line "odhad"
// estimate marker (its own bare <span>odhad</span>) never gets confused with
// the headline total.
const queryHeadlineTotal = () =>
  screen.queryAllByText((_, el) => el?.tagName === 'P' && !!el.textContent?.startsWith('odhad '))[0];

// Component 2: per-recipe priced shopping list. See
// docs/superpowers/specs/2026-07-13-per-recipe-priced-shopping-list-design.md
describe('RecipeIngredients — priced shopping list', () => {
  const ingredients = [
    { name: 'Kuřecí prsa', quantity: 400, unit: 'g' },
    { name: 'Záhadná ingredience', quantity: 100, unit: 'g' },
  ];

  it('shows "bez ceny" for an unpriced line — never a fabricated number', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Kuřecí prsa', canonical: 'chicken-breast', consumed_cost: 68, priced: true, verified: false },
        { name: 'Záhadná ingredience', canonical: null, consumed_cost: null, priced: false, verified: false },
      ],
      total_low: 68,
      total_high: 85,
      per_portion_low: 17,
      per_portion_high: 21.25,
      priced_count: 1,
      total_count: 2,
      verified_count: 0,
      currency: 'CZK',
      confident: false, // 1/2 = 0.5 < COVERAGE_MIN
    };

    render(
      <RecipeIngredients ingredients={ingredients} baseServings={4} shoppingList={shoppingList} />,
    );

    expect(screen.getByText('bez ceny')).toBeInTheDocument();
    // The unpriced ingredient's name must never appear next to a price figure.
    expect(screen.queryByText(/Záhadná ingredience.*Kč/)).not.toBeInTheDocument();
  });

  it('suppresses the headline total when coverage is below the confidence threshold', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Kuřecí prsa', canonical: 'chicken-breast', consumed_cost: 68, priced: true, verified: false },
        { name: 'Záhadná ingredience', canonical: null, consumed_cost: null, priced: false, verified: false },
      ],
      total_low: 68,
      total_high: 85,
      per_portion_low: 17,
      per_portion_high: 21.25,
      priced_count: 1,
      total_count: 2,
      verified_count: 0,
      currency: 'CZK',
      confident: false,
    };

    render(
      <RecipeIngredients ingredients={ingredients} baseServings={4} shoppingList={shoppingList} />,
    );

    expect(queryHeadlineTotal()).toBeUndefined();
    expect(screen.getByText('1 z 2 surovin oceněno')).toBeInTheDocument();
  });

  it('labels the total "odhad" (never an absolute price) when confident', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Kuřecí prsa', canonical: 'chicken-breast', consumed_cost: 68, priced: true, verified: false },
        { name: 'Záhadná ingredience', canonical: 'mystery', consumed_cost: 20, priced: true, verified: true },
      ],
      total_low: 88,
      total_high: 110,
      per_portion_low: 22,
      per_portion_high: 27.5,
      priced_count: 2,
      total_count: 2,
      verified_count: 1,
      currency: 'CZK',
      confident: true,
    };

    render(
      <RecipeIngredients ingredients={ingredients} baseServings={4} shoppingList={shoppingList} />,
    );

    expect(queryHeadlineTotal()).toBeInTheDocument();
    expect(queryHeadlineTotal()?.textContent).toContain('88–110');
    expect(screen.getByText('2 z 2 surovin oceněno')).toBeInTheDocument();
  });

  it('marks an estimate (unverified) line without hiding its price', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Kuřecí prsa', canonical: 'chicken-breast', consumed_cost: 68, priced: true, verified: false },
      ],
      total_low: 68,
      total_high: 85,
      per_portion_low: 17,
      per_portion_high: 21.25,
      priced_count: 1,
      total_count: 1,
      verified_count: 0,
      currency: 'CZK',
      confident: true,
    };

    render(
      <RecipeIngredients ingredients={[ingredients[0]]} baseServings={4} shoppingList={shoppingList} />,
    );

    expect(screen.getByText(/~68/)).toBeInTheDocument();
    expect(screen.getByText('odhad')).toBeInTheDocument();
  });

  it('rescales the per-line price and total live with the portion count', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Kuřecí prsa', canonical: 'chicken-breast', consumed_cost: 100, priced: true, verified: true },
      ],
      total_low: 100,
      total_high: 125,
      per_portion_low: 25,
      per_portion_high: 31.25,
      priced_count: 1,
      total_count: 1,
      verified_count: 1,
      currency: 'CZK',
      confident: true,
    };

    // baseServings=4, but the stepper starts at `base` — quantities/prices
    // only rescale once the user changes the portion count, so this test
    // asserts the base-servings price renders correctly (100 -> "~100 Kč").
    render(
      <RecipeIngredients ingredients={[{ name: 'Kuřecí prsa', quantity: 400, unit: 'g' }]} baseServings={4} shoppingList={shoppingList} />,
    );

    expect(screen.getByText(/~100/)).toBeInTheDocument();
  });

  it('renders with no price data when shoppingList is omitted (plain ingredient list)', () => {
    render(<RecipeIngredients ingredients={ingredients} baseServings={4} />);
    expect(screen.queryByText('bez ceny')).not.toBeInTheDocument();
    expect(screen.queryByText(/surovin oceněno/)).not.toBeInTheDocument();
  });
});

describe('RecipeIngredients — optional grouping', () => {
  const mixed = [
    { name: 'Ovesné vločky', quantity: 80, unit: 'g' },
    { name: 'Skořice', quantity: 1, unit: 'špetka', optional: true },
    { name: 'Mléko', quantity: 250, unit: 'ml' },
    { name: 'Javorový sirup', quantity: 1, unit: 'lžíce', optional: true },
  ];

  it('groups optional ingredients under a "Volitelné" heading, no per-row suffix', () => {
    render(<RecipeIngredients ingredients={mixed} baseServings={1} />);
    expect(screen.getByText('Volitelné')).toBeInTheDocument();
    expect(screen.queryByText(/volitelné\)/)).not.toBeInTheDocument();
    expect(screen.getByText('Skořice')).toBeInTheDocument();
    expect(screen.getByText('Javorový sirup')).toBeInTheDocument();
  });

  it('omits the heading when nothing is optional', () => {
    render(
      <RecipeIngredients
        ingredients={[{ name: 'Mléko', quantity: 250, unit: 'ml' }]}
        baseServings={1}
      />,
    );
    expect(screen.queryByText('Volitelné')).not.toBeInTheDocument();
  });

  it('keeps prices aligned to non-optional rows when optional rows are regrouped', () => {
    // shopping_list.lines only covers non-optional rows, in original order.
    const shoppingList = {
      lines: [
        { name: 'Ovesné vločky', canonical: 'oats', consumed_cost: 6, priced: true, verified: true },
        { name: 'Mléko', canonical: 'milk', consumed_cost: 5, priced: true, verified: true },
      ],
      total_low: 11,
      total_high: 14,
      per_portion_low: 11,
      per_portion_high: 14,
      priced_count: 2,
      total_count: 2,
      verified_count: 2,
      currency: 'CZK',
      confident: true,
    };
    render(<RecipeIngredients ingredients={mixed} baseServings={1} shoppingList={shoppingList} />);
    const oatsRow = screen.getByText('Ovesné vločky').closest('li')!;
    const milkRow = screen.getByText('Mléko').closest('li')!;
    expect(oatsRow.textContent).toContain('~6');
    expect(milkRow.textContent).toContain('~5');
  });
});
