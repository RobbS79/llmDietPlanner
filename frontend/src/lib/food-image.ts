const FALLBACK_CATEGORY = 'kure';

export function getFoodImageUrl(category?: string): string {
  const slug = category || FALLBACK_CATEGORY;
  return `/static/food-images/${slug}.webp`;
}
