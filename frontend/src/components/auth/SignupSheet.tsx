// Signup only at the moment of keeping (spec 2026-11-03). The basket is
// already in localStorage; LoginSuccess sends the user back to /nakup.
import { Link } from 'react-router-dom';

export const RETURN_KEY = 'uvarto.return.v1';

export function SignupSheet({ thumbs, onClose }: { thumbs: string[]; onClose: () => void }) {
  const google = () => {
    try { localStorage.setItem(RETURN_KEY, '/nakup'); } catch { /* ignore */ }
    window.location.href = `${import.meta.env.VITE_API_URL || ''}/api/auth/google/login/`;
  };
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="signup-h" className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex w-full max-w-[480px] flex-col gap-4 rounded-t-3xl bg-paper p-6 sm:rounded-3xl">
        <h2 id="signup-h" className="font-display text-3xl font-bold">Uložit si to</h2>
        {/* EN: So your picked recipes and shopping list don't get lost. */}
        <p>Ať ti vybrané recepty a nákupní seznam neutečou.</p>
        {thumbs.length > 0 && (
          <div className="flex gap-2">{thumbs.slice(0, 6).map((t) => (
            <img key={t} src={t} alt="" className="h-14 w-14 rounded-xl object-cover" />))}</div>
        )}
        {/* EN: Continue with Google */}
        <button type="button" onClick={google} className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-kraft bg-white p-3.5 font-bold">
          Pokračovat přes Google
        </button>
        {/* EN: Or by email */}
        <Link to="/login?mode=register&next=/nakup" className="self-center font-semibold text-green underline">Nebo e-mailem</Link>
        {/* EN: Free, no card. Your first 2 plans are on us. */}
        <p className="text-center text-xs text-muted">Zdarma, bez karty. První 2 plány máš u nás zadarmo.</p>
        {/* EN: Not now */}
        <button type="button" onClick={onClose} className="self-center text-muted underline">Teď ne</button>
      </div>
    </div>
  );
}
