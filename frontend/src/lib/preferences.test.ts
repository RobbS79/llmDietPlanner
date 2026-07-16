import { describe, it, expect } from 'vitest';
import {
  GOALS,
  DIETARY_STYLES,
  ALLERGIES,
  COOKING_SKILLS,
  COOKING_TIMES,
  DEFAULT_PREFERENCES,
  toggleMultiValue,
  buildPreferencesPrompt,
} from './preferences';

describe('option arrays', () => {
  it('expose the canonical ids (guards against accidental edits)', () => {
    expect(GOALS.map(o => o.id)).toEqual(['lose_weight', 'eat_healthy', 'save_money', 'save_time']);
    expect(DIETARY_STYLES.map(o => o.id)).toEqual(['none', 'vegetarian', 'vegan', 'gluten_free', 'keto', 'high_protein']);
    expect(ALLERGIES.map(o => o.id)).toEqual(['none', 'lactose', 'gluten', 'nuts', 'eggs', 'fish', 'soy']);
    expect(COOKING_SKILLS.map(o => o.id)).toEqual(['beginner', 'intermediate', 'advanced']);
    expect(COOKING_TIMES.map(o => o.id)).toEqual(['15min', '30min', '60min', 'unlimited']);
  });
});

describe('DEFAULT_PREFERENCES', () => {
  it('matches the onboarding initial state', () => {
    expect(DEFAULT_PREFERENCES).toEqual({
      goal: '',
      dietary_styles: [],
      allergies: [],
      household_size: 2,
      weekly_budget: 1500,
      cooking_skill: '',
      cooking_time: '',
      country: 'CZ',
      shop: 'ROHLIK',
    });
  });
});

describe('toggleMultiValue', () => {
  it('adds and removes a normal value', () => {
    expect(toggleMultiValue([], 'vegan')).toEqual(['vegan']);
    expect(toggleMultiValue(['vegan'], 'vegan')).toEqual([]);
  });
  it('selecting a normal value clears "none"', () => {
    expect(toggleMultiValue(['none'], 'vegan')).toEqual(['vegan']);
  });
  it('selecting "none" clears everything', () => {
    expect(toggleMultiValue(['vegan', 'keto'], 'none')).toEqual(['none']);
  });
  it('toggling "none" off when already set empties the list', () => {
    expect(toggleMultiValue(['none'], 'none')).toEqual([]);
  });
});

describe('buildPreferencesPrompt', () => {
  it('reproduces the CreatePlan prompt string exactly', () => {
    const { prompt, restrictions } = buildPreferencesPrompt({
      goal: 'lose_weight',
      dietary_styles: ['vegetarian', 'none'],
      allergies: ['lactose'],
      household_size: 2,
      weekly_budget: 1500,
      cooking_skill: 'beginner',
      cooking_time: '30min',
      country: 'CZ',
    });
    expect(prompt).toBe(
      'Chci zhubnout. vegetariánská strava. bez laktózy. Pro 2 osoby. Rozpočet 1500 CZK/týden. jednoduché recepty pro začátečníky. Max 30 minut na přípravu.'
    );
    expect(restrictions).toBe('bez laktózy');
  });
  it('omits unlimited cooking time and uses EUR for SK', () => {
    const { prompt } = buildPreferencesPrompt({
      goal: 'save_money',
      dietary_styles: ['none'],
      allergies: ['none'],
      household_size: 1,
      weekly_budget: 80,
      cooking_skill: 'advanced',
      cooking_time: 'unlimited',
      country: 'SK',
    });
    expect(prompt).toBe('Chci šetřit za jídlo. Pro 1 osobu. Rozpočet 80 EUR/týden. i složitější recepty.');
  });
});
