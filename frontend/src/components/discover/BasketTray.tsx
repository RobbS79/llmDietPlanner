import { useNavigate } from 'react-router-dom';
import { useBasket } from '@/lib/useBasket';
import { trackOpenList } from '@/lib/analytics';

export const dishesWord = (n: number) => (n === 1 ? 'jídlo' : n < 5 ? 'jídla' : 'jídel');

export function BasketTray() {
  const { recipeIds } = useBasket();
  const navigate = useNavigate();
  if (!recipeIds.length) return null;
  return (
    <div className="sticky bottom-3 z-10 my-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink py-3 pl-5 pr-3 text-white">
      {/* EN: "N dishes in the list" */}
      <span>{recipeIds.length} {dishesWord(recipeIds.length)} v seznamu</span>
      {/* EN: "Shopping list" */}
      <button type="button" onClick={() => { trackOpenList(recipeIds.length); navigate('/nakup'); }}
        className="rounded-xl bg-yellow-300 px-4 py-2.5 font-bold text-ink">Nákupní seznam</button>
    </div>
  );
}
