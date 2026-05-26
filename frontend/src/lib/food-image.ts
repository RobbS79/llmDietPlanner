const FALLBACK_CATEGORY = 'kure';

export function getFoodImageUrl(category?: string): string {
  const slug = category || FALLBACK_CATEGORY;
  return `/food-images/${slug}.webp`;
}
