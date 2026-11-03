// frontend/src/pages/Landing.tsx
// The landing page IS the product (spec 2026-11-03): ask, see real recipes,
// pick, get one shopping list. Copy: docs copy deck, informal "ty".
// SSR: entry-server.tsx prerenders this page, so window/localStorage are only
// touched in effects and event handlers, never during render.
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { RecipeCard } from '@/components/discover/RecipeCard';
import { RecipeSheet } from '@/components/discover/RecipeSheet';
import { DealsStrip } from '@/components/discover/DealsStrip';
import { BasketTray } from '@/components/discover/BasketTray';
import { TurnstileGate } from '@/components/discover/TurnstileGate';
import { PlanSheet } from '@/components/plan/PlanSheet';
import { captureAttribution, trackAddToList, trackSearch, trackViewRecipe, type SearchSource } from '@/lib/analytics';
import { isAccessTokenValid } from '@/lib/auth';
import { searchRecipes, type DiscoverResult } from '@/lib/discover';
import { setQuery, toggleRecipe } from '@/lib/basket';
import { useBasket } from '@/lib/useBasket';

// EN: Quick dinner under 30 minutes / What to cook from minced meat / I have potatoes and eggs at home /
//     Something with chicken / Lighter meals for weight loss / Meat-free
const EXAMPLES = ['Rychlá večeře do 30 minut', 'Co uvařit z mletého masa', 'Mám doma brambory a vajíčka',
  'Něco s kuřecím masem', 'Lehčí jídla na hubnutí', 'Bez masa'];

export const Landing = () => {
  const [params, setParams] = useSearchParams();
  const basket = useBasket();
  const [text, setText] = useState(params.get('q') ?? '');
  const [query, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [challenge, setChallenge] = useState(false);
  const [limited, setLimited] = useState(false);
  const [failed, setFailed] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  // Back from login after starting a plan signed out: the prompt is the saved search.
  const [planFromLogin, setPlanFromLogin] = useState(false);

  useEffect(() => { captureAttribution(window.location.search); }, []);

  // `source` is only for the Meta Search event; URL-driven re-runs and paging send none.
  const run = useCallback(async (q: string, p = 0, token?: string, source?: SearchSource) => {
    setLoading(true); setChallenge(false); setLimited(false); setFailed(false);
    try {
      const r = await searchRecipes(q, p, token);
      setResult(r); setQ(q); setPage(p); setQuery(q);
      if (p === 0 && source) trackSearch(source);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { code?: string } } };
      if (e.response?.data?.code === 'CHALLENGE_REQUIRED') { setQ(q); setPage(p); setChallenge(true); }
      else if (e.response?.status === 429) { setResult(null); setLimited(true); }
      else { setResult(null); setFailed(true); }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const q = params.get('q');
    if (q) run(q);
    if (params.get('plan') === '1') {
      if (isAccessTokenValid() || localStorage.getItem('refresh_token')) { setPlanFromLogin(true); setPlanOpen(true); }
      const next = new URLSearchParams(params);
      next.delete('plan');
      setParams(next, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // TurnstileGate re-renders the widget whenever onToken changes, so keep it stable.
  const onToken = useCallback((t: string) => { run(query, page, t); }, [run, query, page]);

  const submit = (q: string, source: SearchSource) => {
    const t = q.trim(); if (!t) return; setText(t); setParams({ q: t }, { replace: true }); run(t, 0, undefined, source);
  };
  const toggle = (id: number) => { if (!basket.recipeIds.includes(id)) trackAddToList(id); toggleRecipe(id); };
  const open = (id: number) => { trackViewRecipe(id); setOpenId(id); };

  return (
    <div className="min-h-screen bg-paper font-body text-ink">
      {/* EN: Skip to content */}
      <a href="#main-content" className="skip-to-content">Přejít na obsah</a>
      <PublicHeader />
      <main id="main-content" className="mx-auto max-w-[1080px] px-5">
        <section className="max-w-3xl pb-2 pt-8 sm:pt-12">
          {/* EN: What to cook today? */}
          <h1 className="font-display text-5xl font-extrabold leading-none tracking-tight sm:text-7xl">Co dnes uvařit?</h1>
          {/* EN: Type what you feel like or what you have at home. You'll see recipes right away, plus what's on sale right now. */}
          <p className="mb-6 mt-4 max-w-prose text-xl text-muted">Napiš, na co máš chuť nebo co máš doma. Hned uvidíš recepty i to, co je zrovna v akci.</p>
          <form onSubmit={(e) => { e.preventDefault(); submit(text, 'typed'); }} className="flex gap-2 rounded-2xl border-2 border-ink bg-white p-1.5">
            {/* EN: What do you want to cook */}
            <label htmlFor="discover-q" className="sr-only">Co chceš uvařit</label>
            {/* EN: For example: something quick from chicken breasts */}
            <input id="discover-q" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" maxLength={300}
              placeholder="Třeba: něco rychlého z kuřecích prsou" className="min-w-0 flex-1 bg-transparent px-3 py-3 text-lg outline-none" />
            {/* EN: Find recipes */}
            <button type="submit" className="whitespace-nowrap rounded-xl bg-green px-5 font-bold text-white">Najít recepty</button>
          </form>
          <div className="mt-3.5 flex flex-wrap gap-2">
            {EXAMPLES.map((c) => (
              <button key={c} type="button" onClick={() => submit(c, 'chip')}
                className="rounded-full border border-kraft bg-white px-3.5 py-1.5 text-[15px] hover:border-ink">{c}</button>
            ))}
          </div>
          {/* EN: Want the whole week sorted? Put a plan together for me */}
          <p className="mt-4 text-muted">Chceš mít jasno na celý týden?{' '}
            <button type="button" onClick={() => { setPlanFromLogin(false); setPlanOpen(true); }} className="font-semibold text-green underline underline-offset-2">Poskládej mi plán</button></p>
        </section>

        {challenge && <TurnstileGate onToken={onToken} />}

        {/* EN: That's enough searching for today. Try again tomorrow. */}
        {limited && <p className="py-6">Na dnešek už je hledání dost. Zkus to zase zítra.</p>}
        {/* EN: Something went wrong. Please try again. */}
        {failed && <p role="alert" className="py-6">Něco se nepovedlo. Zkus to prosím znovu.</p>}

        <section aria-live="polite" className={loading || result ? 'pt-6' : undefined}>
          {/* EN: Searching the collection… */}
          {loading && <p className="text-muted">Hledám ve sbírce…</p>}
          {result && !loading && (
            <>
              <p className="flex flex-wrap items-center gap-2 text-[15px] text-muted">
                {/* EN: Looking for: <tags> */}
                {result.exact && result.understood.length > 0 && <>Hledám: {result.understood.map((u) => (
                  <span key={u} className="rounded-full bg-green-soft px-3 py-1 font-semibold text-green">{u}</span>))}</>}
                {/* EN: We picked a few popular recipes. Try typing an ingredient, e.g. "from zucchini". */}
                {!result.understood.length && result.exact && 'Vybrali jsme pár oblíbených receptů. Zkus napsat surovinu, třeba „z cukety“.'}
                {/* EN: We found nothing exact for that in the collection. Here's what's closest. */}
                {!result.exact && result.recipes.length > 0 && 'Na tohle jsme ve sbírce nic přesného nenašli. Tady je, co je nejblíž.'}
              </p>
              {/* EN: Uvařto is a kitchen helper, not medical advice. Discuss eating with an illness with your doctor. */}
              {result.medical_note && (
                <p className="mt-2 text-sm text-muted">Uvařto je pomocník do kuchyně, ne zdravotní rada. Jídelníček při nemoci probírej s lékařem.</p>
              )}
              {result.recipes.length === 0
                // EN: We couldn't find anything for that. Try writing it differently, e.g. a single ingredient: "from potatoes" or "with rice".
                ? <p className="py-6">Na tohle jsme nic nenašli. Zkus to napsat jinak, třeba jednu surovinu: „z brambor“ nebo „s rýží“.</p>
                : (
                  <div className="my-4 grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-5">
                    {result.recipes.map((r) => (
                      <RecipeCard key={r.id} recipe={r} picked={basket.recipeIds.includes(r.id)} onToggle={toggle} onOpen={open} />))}
                  </div>
                )}
              {result.has_more && (
                // EN: Show me something else
                <button type="button" onClick={() => run(query, page + 1)} className="rounded-xl border border-kraft bg-white px-4 py-3 font-semibold">
                  Ukaž mi něco jiného</button>
              )}
            </>
          )}
        </section>

        <BasketTray />
        <DealsStrip onPick={(q) => submit(q, 'deal')} />
      </main>

      {openId !== null && <RecipeSheet id={openId} picked={basket.recipeIds.includes(openId)} onToggle={toggle} onClose={() => setOpenId(null)} />}
      {planOpen && <PlanSheet understood={planFromLogin ? [] : result?.understood ?? []} prompt={planFromLogin ? basket.query : query}
        onClose={() => setPlanOpen(false)} />}
    </div>
  );
};

export default Landing;
