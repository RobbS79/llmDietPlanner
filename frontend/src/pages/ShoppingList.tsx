// frontend/src/pages/ShoppingList.tsx
// /nakup: one list for the picked dishes, anonymous until "Uložit si to".
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { SignupSheet } from '@/components/auth/SignupSheet';
import { PlanSheet } from '@/components/plan/PlanSheet';
import { dishesWord } from '@/components/discover/BasketTray';
import { composeList, formatAmount, formatDealDate, type ListLine } from '@/lib/discover';
import { attachBasketAfterLogin, readBasket, setPeople, toggleAtHome, type AttachResult } from '@/lib/basket';
import { useBasket } from '@/lib/useBasket';
import { isAccessTokenValid } from '@/lib/auth';

// Saving clears the basket, so the page keeps rendering what was saved from this snapshot.
type Snapshot = { ids: number[]; people: number; atHome: string[]; query: string };

export function ShoppingList() {
  const basket = useBasket();
  const [params] = useSearchParams();
  const [signup, setSignup] = useState(false);
  const [plan, setPlan] = useState(false);
  const [saved, setSaved] = useState<AttachResult | null>(null);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const attaching = useRef(false);
  const signedIn = isAccessTokenValid() || !!localStorage.getItem('refresh_token');

  const ids = snap?.ids ?? basket.recipeIds;
  const people = snap?.people ?? basket.people;
  const atHome = snap?.atHome ?? basket.atHome;
  // Keyed on the snapshot once taken, so the composed list stays cached after the basket clears.
  const { data } = useQuery({ queryKey: ['compose', ids, people], queryFn: () => composeList(ids, people), enabled: ids.length > 0 });

  const attach = async () => {
    if (attaching.current) return; // Strict Mode runs effects twice; attach once.
    attaching.current = true;
    const b = readBasket();
    setSnap({ ids: b.recipeIds, people: b.people, atHome: b.atHome, query: b.query });
    setSaved(await attachBasketAfterLogin());
  };

  useEffect(() => { if (signedIn && params.get('vitej') === '1') void attach(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Personal page: keep it out of search results.
  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const prev = meta?.content;
    if (meta) meta.content = 'noindex, nofollow';
    return () => { if (meta && prev !== undefined) meta.content = prev; };
  }, []);

  const save = async () => { if (!signedIn) { setSignup(true); return; } attaching.current = false; await attach(); };
  const changePeople = (n: number) => {
    if (snap) setSnap({ ...snap, people: Math.min(6, Math.max(1, n)) });
    else setPeople(n);
  };
  const markHome = (k: string) => {
    if (snap) setSnap({ ...snap, atHome: snap.atHome.includes(k) ? snap.atHome.filter((x) => x !== k) : [...snap.atHome, k] });
    else toggleAtHome(k);
  };
  const key = (l: ListLine) => `${l.canonical}|${l.unit}`;
  const row = (l: ListLine) => {
    const home = atHome.includes(key(l));
    return (
      <div key={key(l)} className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-kraft py-2.5 ${home ? 'opacity-45' : ''}`}>
        <input type="checkbox" id={`l-${key(l)}`} className="h-5 w-5 accent-green" />
        <label htmlFor={`l-${key(l)}`}>
          <span className={home ? 'line-through' : ''}>{l.name}</span>{' '}
          <span className="text-sm text-muted">{formatAmount(l.amount, l.unit)}</span>
          <small className="block text-[13px] text-muted">
            {/* EN: On sale: <shop>, until <date> · for <n> meals */}
            {l.deal ? `V akci: ${l.deal.shop}, do ${formatDealDate(l.deal.valid_until)}` : ''}
            {l.deal && l.needed_by > 1 ? ' · ' : ''}{l.needed_by > 1 ? `do ${l.needed_by} jídel` : ''}
          </small>
        </label>
        {/* EN: I have it at home */}
        <button type="button" onClick={() => markHome(key(l))} className="rounded-full border border-kraft px-2.5 py-1 text-[13px]">mám doma</button>
      </div>
    );
  };
  const lines = data?.lines ?? [];
  const deals = lines.filter((l) => l.deal);
  const rest = lines.filter((l) => !l.deal);

  return (
    <div className="min-h-screen bg-paper font-body text-ink">
      <PublicHeader />
      <main className="mx-auto max-w-[760px] px-5 pb-16">
        {/* EN: Back to recipes */}
        <Link to="/" className="font-semibold text-green underline">← Zpět k receptům</Link>
        {saved === 'saved' && (
          <div className="mt-4 rounded-2xl border border-kraft bg-white p-4">
            {/* EN: Hi, welcome to Uvařto. Your picked recipes are saved. Want to put a whole week together around them? */}
            <p className="font-display text-2xl font-bold">Ahoj, vítej v Uvařto.</p>
            <p className="mt-1">Tvoje vybrané recepty jsou uložené. Chceš k nim dát dohromady celý týden?</p>
            {/* EN: Yes, put a week together for me */}
            <button type="button" onClick={() => setPlan(true)} className="mt-3 rounded-xl bg-green px-4 py-2.5 font-bold text-white">Jo, poskládej mi týden</button>
          </div>
        )}
        {saved === 'limit' && (
          <div className="mt-4 rounded-2xl border border-kraft bg-white p-4">
            {/* EN: You've already saved 3 lists this month. Unlimited with a subscription. */}
            <p>Tento měsíc už máš uložené 3 seznamy. S předplatným bez omezení.</p>
            {/* EN: See the subscription */}
            <Link to="/pricing" className="mt-2 inline-block font-semibold text-green underline">Podívat se na předplatné</Link>
          </div>
        )}
        {/* EN: Shopping for N meals */}
        <h1 className="mt-3 font-display text-4xl font-bold">Nákup na {ids.length} {dishesWord(ids.length)}</h1>
        {/* EN: Nothing here yet. Find some recipes. */}
        {ids.length === 0 ? <p className="mt-4">Zatím tu nic není. <Link to="/" className="text-green underline">Najdi si recepty</Link>.</p> : (
          <>
            <div className="mt-3 flex items-center gap-3">
              {/* EN: For how many people */}
              <span>Pro kolik lidí</span>
              <button type="button" aria-label="Méně lidí" onClick={() => changePeople(people - 1)} className="h-9 w-9 rounded-full border border-kraft bg-white">−</button>
              <span className="w-6 text-center tabular-nums" aria-live="polite">{people}</span>
              <button type="button" aria-label="Více lidí" onClick={() => changePeople(people + 1)} className="h-9 w-9 rounded-full border border-kraft bg-white">+</button>
            </div>
            {/* EN: Tick off what you have at home with the "I have it at home" button. */}
            <p className="mt-2 text-[15px] text-muted">Co máš doma, odškrtni tlačítkem „mám doma“.</p>
            {/* EN: On sale this week */}
            {deals.length > 0 && <><h2 className="mt-5 text-[15px] font-semibold text-muted">Tento týden v akci</h2>{deals.map(row)}</>}
            {/* EN: Everything else */}
            <h2 className="mt-5 text-[15px] font-semibold text-muted">Ostatní</h2>{rest.map(row)}
            <div className="mt-6 grid max-w-[460px] gap-2.5">
              {/* EN: Save it */}
              {saved !== 'saved' && <button type="button" onClick={save} className="rounded-xl bg-green p-3.5 text-[17px] font-bold text-white">Uložit si to</button>}
              {/* EN: Make a whole week out of it */}
              <button type="button" onClick={() => setPlan(true)} className="rounded-xl border border-kraft bg-white p-3 font-semibold">Udělat z toho celý týden</button>
            </div>
          </>
        )}
      </main>
      {signup && <SignupSheet thumbs={(data?.recipes ?? []).map((r) => r.image_url)} onClose={() => setSignup(false)} />}
      {plan && <PlanSheet understood={[]} prompt={snap?.query ?? basket.query} onClose={() => setPlan(false)} />}
    </div>
  );
}

export default ShoppingList;
