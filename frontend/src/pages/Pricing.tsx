import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Check, X, ArrowRight, ArrowLeft, HelpCircle } from 'lucide-react';
import axios from 'axios';
import { startCheckout, type BillingTier } from '@/lib/billing';
import { isAccessTokenValid } from '@/lib/auth';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { PromoCodeBox } from '@/components/pricing/PromoCodeBox';
import { trackCheckoutStarted } from '@/lib/analytics';
import {
  validatePromo, redeemPromo, getPendingPromo, setPendingPromo, clearPendingPromo,
  PROMO_REASON_TEXT, TERMINAL_REASONS, type PromoValidation, type PromoReason,
} from '@/lib/promo';

// Only limits the product enforces: plans (2 free for life; 7 / 30 a month paid)
// and saved shopping lists (3 a month free; unlimited paid). Deals are free on
// every tier and are never prices or savings. Copy: informal "ty".
const COMMON = [
  // EN: What's on sale right now / Nutrition values
  { text: 'Co je zrovna v akci', included: true },
  { text: 'Nutriční hodnoty', included: true },
];

const PLANS = [
  {
    name: 'Zdarma',
    price: 0,
    // EN: To try it out
    description: 'Na vyzkoušení',
    // EN: Find recipes
    cta: 'Najít recepty',
    highlighted: false,
    features: [
      // EN: 2 free plans / 3 saved shopping lists a month
      { text: '2 plány zdarma', included: true },
      { text: '3 uložené nákupní seznamy měsíčně', included: true },
      ...COMMON,
    ],
  },
  {
    name: 'Standard',
    tier: 'standard' as const,
    price: 99,
    // EN: A plan for every week
    description: 'Plán na každý týden',
    cta: 'Vybrat Standard',
    highlighted: true,
    features: [
      // EN: 7 plans a month / Unlimited shopping lists
      { text: '7 plánů měsíčně', included: true },
      { text: 'Nákupní seznamy bez omezení', included: true },
      ...COMMON,
    ],
  },
  {
    name: 'Premium',
    tier: 'premium' as const,
    price: 199,
    // EN: When you plan often
    description: 'Když plánuješ často',
    cta: 'Vybrat Premium',
    highlighted: false,
    features: [
      // EN: 30 plans a month / Unlimited shopping lists
      { text: '30 plánů měsíčně', included: true },
      { text: 'Nákupní seznamy bez omezení', included: true },
      ...COMMON,
    ],
  },
];

const FAQ = [
  {
    // EN: What do I get for free?
    q: 'Co mám zdarma?',
    // EN: Searching recipes, what's on sale and nutrition are free. With an account you save 3 shopping lists a month and build 2 week plans. A plan is a set of recipes for your request, each with nutrition and a shopping list.
    a: 'Hledání receptů, přehled akcí a nutriční hodnoty jsou zdarma. S účtem si uložíš 3 nákupní seznamy měsíčně a sestavíš si 2 plány na týden. Plán je sada receptů podle tvého zadání, každý recept s nutričními hodnotami a nákupním seznamem.',
  },
  {
    // EN: Do you show prices?
    q: 'Ukazujete ceny?',
    // EN: No. Shop prices change and we don't want to show you guesses. We show which ingredients are on sale right now, in which shop and until when.
    a: 'Ne. Ceny v obchodech se mění a nechceme ti ukazovat odhady. Ukážeme ti, které suroviny jsou zrovna v akci, v jakém obchodě a do kdy akce platí.',
  },
  {
    // EN: Where do the deals come from?
    q: 'Odkud berete akce?',
    // EN: From current leaflets of shops in Czechia. We never show a deal that has already ended.
    a: 'Z aktuálních letáků obchodů v Česku. Akci, která už skončila, nezobrazíme.',
  },
  {
    // EN: Can I cancel any time?
    q: 'Můžu předplatné kdykoliv zrušit?',
    // EN: Yes. Paid features stay until the end of the period you paid for.
    a: 'Ano, kdykoliv. Placené funkce ti zůstanou do konce zaplaceného období.',
  },
  {
    // EN: Do you handle dietary restrictions?
    q: 'Hlídáte dietní omezení?',
    // EN: Meat-free, vegan, gluten-free and lactose-free are checked on every recipe. Write them into the search or save them in settings. We leave out allergens like nuts or eggs by ingredient, but with an allergy always check the ingredients yourself.
    a: 'Bez masa, vegan, bez lepku a bez laktózy hlídáme u každého receptu. Stačí je napsat do hledání nebo si je uložit v nastavení. Alergeny jako ořechy nebo vejce vyřadíme podle surovin, ale při alergii si složení vždy zkontroluj.',
  },
];

// Search lives at / for visitors; signed-in users have the Dashboard there.
const searchPath = () => (isAccessTokenValid() ? '/hledat' : '/');

export const Pricing = () => {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [checkoutTier, setCheckoutTier] = useState<BillingTier | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  // Sent here by the plan paywall (api.ts interceptor on a 402).
  const [fromQuota] = useState(() => searchParams.get('reason') === 'quota');
  const [promoInput, setPromoInput] = useState(
    () => searchParams.get('promo')?.toUpperCase() || getPendingPromo() || '',
  );
  const [promo, setPromo] = useState<PromoValidation | null>(null);
  const [promoChecking, setPromoChecking] = useState(false);

  const applyPromo = useCallback(async (raw: string) => {
    const code = raw.trim().toUpperCase();
    if (!code) return;
    setPromoChecking(true);
    try {
      const v = await validatePromo(code);
      setPromo(v);
      if (v.valid) setPendingPromo(v.code);
      else if (getPendingPromo() === code) clearPendingPromo();
    } catch {
      setPromo({ valid: false, reason: 'stripe_error' });
    } finally {
      setPromoChecking(false);
    }
  }, []);

  // Auto-validate a code arriving via ?promo= or remembered from a previous visit.
  useEffect(() => {
    if (promoInput) applyPromo(promoInput);
    if (searchParams.has('promo')) {
      const next = new URLSearchParams(searchParams);
      next.delete('promo');
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clearPromo = () => {
    clearPendingPromo();
    setPromo(null);
    setPromoInput('');
  };

  const activePromo = promo?.valid ? promo : null;

  // CTA: free tier -> signup; paid tier -> promo redeem (grant or discounted
  // Checkout) or plain Stripe Checkout if logged in, otherwise login first
  // and bounce back here to buy.
  const handleSelectPlan = async (tier?: BillingTier) => {
    if (!tier) {
      navigate(searchPath());
      return;
    }
    if (!isAccessTokenValid()) {
      navigate('/login?next=/pricing');
      return;
    }
    setCheckoutError(null);
    setCheckoutTier(tier);
    const promoForTier = activePromo && activePromo.prices[tier] ? activePromo : null;
    try {
      if (promoForTier) {
        const result = await redeemPromo(promoForTier.code, tier);
        if (result.granted) {
          clearPendingPromo();
          navigate('/?promo=granted', { replace: true });
          return;
        }
        trackCheckoutStarted();
        window.location.href = result.url;
        return;
      }
      trackCheckoutStarted(); // fire InitiateCheckout right before Stripe redirect
      await startCheckout(tier); // redirects to Stripe on success
    } catch (err) {
      const reason: PromoReason | undefined = axios.isAxiosError(err)
        ? err.response?.data?.reason : undefined;
      if (reason && PROMO_REASON_TEXT[reason]) {
        setCheckoutError(PROMO_REASON_TEXT[reason]);
        if (TERMINAL_REASONS.includes(reason)) {
          clearPendingPromo();
          setPromo({ valid: false, reason });
        }
      } else {
        // EN: Couldn't start the payment. Please try again.
        setCheckoutError('Platbu se nepodařilo zahájit. Zkus to prosím znovu.');
      }
      setCheckoutTier(null);
    }
  };

  useEffect(() => {
    const schema = {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: FAQ.map(item => ({
        '@type': 'Question',
        name: item.q,
        acceptedAnswer: { '@type': 'Answer', text: item.a },
      })),
    };
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(schema);
    script.id = 'faq-schema';
    document.head.appendChild(script);
    return () => { document.getElementById('faq-schema')?.remove(); };
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink font-body">
      <PublicHeader />

      <main className="max-w-6xl mx-auto px-6 sm:px-12 py-12">
        <Link
          to="/"
          className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8"
        >
          <ArrowLeft size={14} /> Zpět na hlavní stránku
        </Link>

        <header className="text-center mb-16 space-y-6">
          <p className="text-sm font-semibold text-green">Ceník</p>
          <h1 className="font-display text-5xl sm:text-6xl font-extrabold tracking-tight leading-tight text-ink">
            Jednoduchý <span className="text-paprika">ceník.</span>
          </h1>
          <p className="text-muted text-lg max-w-md mx-auto">
            {/* EN: Start for free. Take a subscription once Uvařto is useful to you. */}
            Začni zdarma. Předplatné si vezmi, až ti Uvařto bude k užitku.
          </p>
        </header>

        {fromQuota && (
          <div role="status" className="max-w-md mx-auto mb-8 rounded-xl border border-line bg-card px-5 py-3 text-center text-ink">
            {/* EN: The next plan doesn't fit in your current plan. Pick a subscription below and carry on. */}
            Další plán už se do tvého tarifu nevejde. Vyber si předplatné níže a pokračuj.
          </div>
        )}

        {checkoutError && (
          <div className="max-w-md mx-auto mb-8 rounded-xl border border-paprika/40 bg-paprika-soft px-5 py-3 text-center text-sm text-paprika-strong">
            {checkoutError}
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-24">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-3xl transition-all flex flex-col ${
                plan.highlighted
                  ? 'bg-card border-2 border-green shadow-lg'
                  : 'bg-card border border-line'
              }`}
            >
              {/* Card header zone */}
              <div className={`rounded-t-3xl px-8 pt-8 pb-6 ${plan.highlighted ? 'bg-green-soft' : ''}`}>
                {plan.highlighted && (
                  <div className="inline-block px-3 py-1 bg-green text-white rounded-lg text-xs font-semibold mb-4">
                    Doporučeno
                  </div>
                )}

                <h2 className="font-display text-2xl font-bold text-ink mb-1">{plan.name}</h2>
                <p className="text-muted text-sm mb-6">{plan.description}</p>

                <div className="mb-2">
                  {(() => {
                    const tier = (plan as { tier?: BillingTier }).tier;
                    const deal = tier && activePromo ? activePromo.prices[tier] : undefined;
                    if (plan.price === 0) {
                      return (
                        <p className="font-price text-5xl font-bold text-ink">
                          0 <span className="text-muted text-lg font-normal">Kč</span>
                        </p>
                      );
                    }
                    if (deal) {
                      return (
                        <div>
                          <p className="font-price text-5xl font-bold text-ink">
                            {deal.discounted} <span className="text-muted text-lg font-normal">Kč/měsíc</span>
                          </p>
                          <p className="text-sm text-muted">
                            <s>{deal.original} Kč</s>
                            {deal.discounted === 0 && <span className="ml-2 font-bold text-green">bez platební karty</span>}
                          </p>
                        </div>
                      );
                    }
                    return (
                      <p className="font-price text-5xl font-bold text-ink">
                        {plan.price} <span className="text-muted text-lg font-normal">Kč/měsíc</span>
                      </p>
                    );
                  })()}
                </div>
              </div>

              {/* Card body */}
              <div className="px-8 pb-8 flex flex-col flex-1">
                <button
                  onClick={() => handleSelectPlan((plan as { tier?: BillingTier }).tier)}
                  disabled={checkoutTier !== null}
                  className={`w-full h-14 rounded-xl font-bold text-sm transition-all active:scale-[0.98] flex items-center justify-center gap-3 mb-8 mt-6 disabled:opacity-60 disabled:cursor-not-allowed ${
                    plan.highlighted
                      ? 'bg-green hover:bg-green-mid text-white shadow-md'
                      : 'bg-green hover:bg-green-mid text-white'
                  }`}
                >
                  {checkoutTier === (plan as { tier?: BillingTier }).tier
                    ? 'Přesměrování…'
                    : (() => {
                        const t = (plan as { tier?: BillingTier }).tier;
                        return t && activePromo?.prices[t]?.discounted === 0 ? 'Aktivovat zdarma' : plan.cta;
                      })()}{' '}
                  <ArrowRight size={16} />
                </button>

                <ul className="space-y-4 flex-1">
                  {plan.features.map((f) => (
                    <li key={f.text} className="flex items-center gap-3 text-sm">
                      {f.included ? (
                        <Check size={16} className="text-green shrink-0" />
                      ) : (
                        <X size={16} className="text-line shrink-0" />
                      )}
                      <span className={f.included ? 'text-ink' : 'text-muted'}>{f.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>

        <PromoCodeBox
          code={promoInput}
          onCodeChange={setPromoInput}
          validation={promo}
          checking={promoChecking}
          onApply={() => applyPromo(promoInput)}
          onClear={clearPromo}
        />

        <div className="text-center mb-16">
          <p className="text-muted text-sm">
            {/* EN: Standard costs less than one coffee a week. For that you get a plan for your goal every week, with nutrition and a shopping list that shows what's on sale right away. */}
            Standard stojí méně než jedno kafe týdně. Za to máš každý týden <strong className="text-ink">plán podle svého cíle</strong>, s nutričními hodnotami a nákupním seznamem, ve kterém rovnou vidíš suroviny v akci.
          </p>
        </div>

        {/* FAQ */}
        <section className="max-w-3xl mx-auto mb-24">
          <div className="text-center mb-12">
            <p className="text-sm font-semibold text-green mb-4">FAQ</p>
            <h2 className="font-display text-3xl sm:text-4xl font-bold text-ink">Časté dotazy</h2>
          </div>

          <div className="space-y-3">
            {FAQ.map((item, i) => (
              <div key={i} className="bg-card border border-line rounded-2xl overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="text-sm font-bold text-ink pr-4">{item.q}</span>
                  <HelpCircle
                    size={18}
                    className={`shrink-0 transition-colors ${openFaq === i ? 'text-green' : 'text-muted'}`}
                  />
                </button>
                {openFaq === i && (
                  <div className="px-6 pb-6 pt-0 bg-kraft">
                    <p className="text-sm text-ink leading-relaxed">{item.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="text-center pb-12">
          <div className="bg-green-soft border border-green/20 rounded-3xl p-12 sm:p-16">
            <h2 className="font-display text-3xl sm:text-4xl font-bold text-ink mb-4">
              {/* EN: Want to try it? */}
              Chceš to zkusit?
            </h2>
            {/* EN: Type what you feel like and you'll see recipes right away. No signup, no card. */}
            <p className="text-muted mb-8">Napiš, na co máš chuť, a hned uvidíš recepty. Bez registrace, bez karty.</p>
            <button
              onClick={() => navigate(searchPath())}
              className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-bold text-sm transition-all active:scale-[0.98] inline-flex items-center gap-3"
            >
              {/* EN: Find recipes */}
              Najít recepty <ArrowRight size={18} />
            </button>
          </div>
        </section>
      </main>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-line">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="font-display font-extrabold text-xl tracking-tight text-ink lowercase">
            uvařto<span className="text-paprika">.</span>
          </span>
          <div className="flex items-center gap-6">
            <Link to="/privacy" className="text-xs font-bold text-muted hover:text-ink transition-colors">
              Zásady ochrany soukromí
            </Link>
            <Link to="/terms" className="text-xs font-bold text-muted hover:text-ink transition-colors">
              Obchodní podmínky
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
