// EN: goals = "I want to lose weight", "I cook ahead into boxes", "I cook for the family", "Just spare me the thinking"
export const GOALS = ['Chci zhubnout', 'Vařím dopředu do krabiček', 'Vařím pro rodinu', 'Jen ať nemusím vymýšlet'] as const;
// EN: counts = "5 dinners", "5 lunches and 5 dinners", "I'll set it up myself"
export const COUNT_OPTIONS = ['5 večeří', '5 obědů a 5 večeří', 'Nastavím si sám'] as const;
type Counts = { breakfasts: number; lunches: number; dinners: number; small_meals: number; snacks: number };
const ZERO: Counts = { breakfasts: 0, lunches: 0, dinners: 0, small_meals: 0, snacks: 0 };

export function countsFor(answer: string): Counts | null {
  if (answer === '5 večeří') return { ...ZERO, dinners: 5 };
  if (answer === '5 obědů a 5 večeří') return { ...ZERO, lunches: 5, dinners: 5 };
  return null;
}

// The plan API requires a prompt of at least 10 characters (DietaryGoalCreateRequest).
const FALLBACK = 'Jen ať nemusím vymýšlet';
export function goalPrompt(goal: string | null, search: string): string {
  const text = [goal, search.trim()].filter(Boolean).join('. ');
  if (!text) return FALLBACK;
  return text.length >= 10 ? text : `${text}. ${FALLBACK}`;
}
