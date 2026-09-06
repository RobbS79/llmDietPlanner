export interface MealSide {
  key: string;
  name_cs: string;
  with_cs: string;
  display: string;
}

/** "s chlebem · 2 krajíce" under a plan-card dish name. Copy comes from the
 * backend příloha table (services/priloha.py), already in the right case. */
export const MealSideLine = ({ side }: { side: MealSide | null | undefined }) => {
  if (!side) return null;
  return (
    <p className="text-sm font-bold text-muted italic tracking-wide mb-4 relative z-10">
      {side.with_cs} · {side.display}
    </p>
  );
};
