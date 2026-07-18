import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { ShoppingCart, UtensilsCrossed, BarChart3, ArrowRight, Check, ChefHat, Heart, Target, Wallet, Lightbulb, Search, SlidersHorizontal } from 'lucide-react';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { Receipt } from '@/components/ui/Receipt';
import { captureAttribution } from '@/lib/analytics';

const SAMPLE_PLAN = {
  days: [
    { day: 1, meals: ['Ovesná kaše s ovocem', 'Kuřecí wok s rýží', 'Losos s brokolicí'] },
    { day: 2, meals: ['Jogurt s granolou', 'Salát s tuňákem', 'Hovězí guláš s knedlíkem'] },
    { day: 3, meals: ['Vajíčka s avokádo', 'Treščí filé s brambory', 'Kuřecí curry s rýží'] },
  ],
  recipe: {
    name: 'Kuřecí wok s rýží',
    portions: '4 porce',
    ingredients: [
      { name: 'Kuřecí prsa', unit: '300 g', deal: false },
      { name: 'Rýže basmati', unit: '240 g', deal: false },
      { name: 'Paprika', unit: '2 ks', deal: true },
      { name: 'Brokolice', unit: '1/2 ks', deal: true },
      { name: 'Sójová omáčka', unit: '40 ml', deal: false },
    ],
    dealsHeadline: '2 z 5 surovin ve slevě tento týden',
    dealsFooter: 'Ušetříte na tom, co je zrovna v akci',
  },
};

const RECEIPT_ITEMS = SAMPLE_PLAN.recipe.ingredients.map((item) => ({
  name: item.name,
  meta: item.unit,
  deal: item.deal,
}));

export const Landing = () => {
  const navigate = useNavigate();
  const [showStickyCta, setShowStickyCta] = useState(false);

  useEffect(() => {
    // loadPixel() (called on App mount) already fires the init-time
    // fbq('track', 'PageView'), which serves as the landing-view signal.
    // We intentionally do NOT call trackLandingView() here — doing so would
    // fire a second PageView for the same visit and double-count landings.
    captureAttribution(window.location.search);

    const onScroll = () => setShowStickyCta(window.scrollY > 600);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-paper text-ink font-body overflow-hidden pb-20 sm:pb-0">
      <a href="#main-content" className="skip-to-content">
        Přejít na obsah
      </a>
      <PublicHeader />

      {/* Hero */}
      <section id="main-content" className="px-6 sm:px-12 pt-16 sm:pt-24 pb-20 max-w-7xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-14 items-center">
          {/* Left: copy */}
          <div>
            <div className="inline-flex items-center gap-2 bg-green-soft rounded-full px-4 py-1.5 mb-8">
              <span className="w-2 h-2 bg-green rounded-full" />
              <span className="text-[10px] font-bold text-green uppercase tracking-widest">Jídelníček podle vašeho cíle</span>
            </div>

            <h1 className="font-display text-5xl sm:text-7xl font-extrabold tracking-tight leading-[0.95] mb-8">
              Zhubnout, nabrat, nebo jen jíst líp?<br />
              <span className="text-paprika">Naplánujeme vám celý týden jídla.</span>
            </h1>

            <p className="text-lg sm:text-xl text-muted max-w-xl mb-4 leading-relaxed">
              Popíšete svůj cíl vlastními slovy — a dostanete <strong className="text-ink">jídelníček na míru s recepty, nutričními hodnotami (kalorie a makra) a nákupním seznamem.</strong> U některých surovin navíc rovnou vidíte aktuální slevy z letáků.
            </p>

            <p className="text-sm text-muted mb-10">Bez kreditní karty. Hotovo za méně než 60 sekund.</p>

            <div className="flex flex-col sm:flex-row gap-4">
              <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-bold text-base shadow-lg transition-all active:scale-[0.98] flex items-center justify-center gap-3">
                Vytvořit jídelníček zdarma <ArrowRight size={18} />
              </button>
              <a href="#how-it-works" className="border border-line text-ink px-10 py-4 rounded-2xl font-bold text-base hover:bg-kraft transition-all text-center">
                Jak to funguje
              </a>
            </div>
          </div>

          {/* Right: receipt signature */}
          <div className="lg:pl-6">
            <Receipt
              title={SAMPLE_PLAN.recipe.name}
              subtitle={`Ukázkový recept · ${SAMPLE_PLAN.recipe.portions}`}
              source="Nákupní seznam"
              items={RECEIPT_ITEMS}
              footnote={SAMPLE_PLAN.recipe.dealsHeadline}
              totalLabel={SAMPLE_PLAN.recipe.dealsFooter}
            />
          </div>
        </div>
      </section>

      {/* Honest stat band */}
      <section className="bg-kraft border-y border-line">
        <div className="px-6 sm:px-12 py-12 max-w-7xl mx-auto">
          <div className="flex flex-wrap gap-8 sm:gap-16 text-center sm:text-left">
            {[
              { value: '300+', label: 'Prověřených receptů' },
              { value: 'Kalorie a makra', label: 'U každého jídla' },
              { value: 'Nákupní seznam', label: 'Ke každému receptu' },
            ].map((stat) => (
              <div key={stat.label}>
                <p className="font-display text-2xl sm:text-3xl font-extrabold text-ink tracking-tight">{stat.value}</p>
                <p className="text-xs font-semibold text-muted mt-1">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Who is this for */}
      <section className="bg-kraft border-y border-line">
        <div className="px-6 sm:px-12 py-20 max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-[10px] font-bold text-green uppercase tracking-[0.3em] mb-4">Pro koho je to</p>
            <h2 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight">Vytvořeno pro lidi, kteří…</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: Heart, title: 'Chtějí jíst zdravěji', desc: 'Ale neví, kde začít a co vařit' },
              { icon: Target, title: 'Sledují makra a kalorie', desc: 'Ale nenávidí plánování jídel' },
              { icon: Wallet, title: 'Hlídají si rozpočet', desc: 'A chtějí nakupovat chytře — u každého receptu vidí, co je zrovna ve slevě' },
              { icon: Lightbulb, title: 'Vaří doma', desc: 'Ale dochází jim nápady na recepty' },
            ].map((item) => (
              <div key={item.title} className="bg-card border border-line rounded-2xl p-8 text-center hover:border-green/40 transition-all">
                <item.icon size={28} className="text-green mx-auto mb-4" />
                <h4 className="font-display font-bold text-base mb-2">{item.title}</h4>
                <p className="text-muted text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-paper">
        <div className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
          <div className="text-center mb-20">
            <p className="text-[10px] font-bold text-green uppercase tracking-[0.3em] mb-4">Jak to funguje</p>
            <h2 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight">Tři kroky k vašemu jídelníčku.</h2>
          </div>

          <div className="grid sm:grid-cols-3 gap-8">
            {[
              {
                step: '1',
                icon: UtensilsCrossed,
                title: 'Popište své cíle',
                desc: 'Řekněte nám vlastními slovy, co chcete — vysokoproteinová, levná, veganská, keto. Žádné dotazníky, žádné tabulky.',
              },
              {
                step: '2',
                icon: ChefHat,
                title: 'Sestavíme váš plán',
                desc: 'Vygenerujeme kompletní vícedenní jídelníček se snídaní, obědem, večeří, recepty a nutričními hodnotami.',
              },
              {
                step: '3',
                icon: ShoppingCart,
                title: 'Nakupujte s přehledem',
                desc: 'Ke každému receptu dostanete nákupní seznam. A hned vidíte, které suroviny jsou tento týden ve slevě — a ve kterém obchodě.',
              },
            ].map((item) => (
              <div key={item.step} className="bg-card border border-line rounded-3xl p-10 hover:border-green/40 transition-all">
                <div className="w-12 h-12 rounded-xl bg-green flex items-center justify-center text-2xl font-display font-extrabold text-white mb-8 shadow-lg">
                  {item.step}
                </div>
                <item.icon size={32} className="text-green mb-6" />
                <h3 className="font-display text-xl font-bold mb-4">{item.title}</h3>
                <p className="text-muted text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How the plan is made */}
      <section className="bg-kraft border-y border-line">
        <div className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-[10px] font-bold text-green uppercase tracking-[0.3em] mb-4">Jak vzniká váš jídelníček</p>
            <h2 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight">Transparentně a pod vaší kontrolou.</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: Search, title: 'Analyzuje vaše cíle', desc: 'Pochopí vaše stravovací potřeby, omezení i rozpočet' },
              { icon: ChefHat, title: 'Vytvoří vyvážená jídla', desc: 'Každý plán splňuje nutriční doporučení pro vaše cíle' },
              { icon: ShoppingCart, title: 'Najde slevy na suroviny', desc: 'Suroviny každého receptu porovná s aktuálními letáky velkých českých obchodů a ukáže, co je tento týden v akci' },
              { icon: SlidersHorizontal, title: 'Vy máte kontrolu', desc: 'Upravte, regenerujte nebo změňte cokoliv kdykoliv' },
            ].map((item) => (
              <div key={item.title} className="text-center">
                <div className="w-12 h-12 rounded-xl bg-green-soft flex items-center justify-center mx-auto mb-4">
                  <item.icon size={22} className="text-green" />
                </div>
                <h4 className="font-display font-bold text-base mb-2">{item.title}</h4>
                <p className="text-muted text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sample plan preview */}
      <section className="bg-paper">
        <div className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
          <div className="text-center mb-20">
            <p className="text-[10px] font-bold text-green uppercase tracking-[0.3em] mb-4">Ukázka</p>
            <h2 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight">Podívejte se, co dostanete.</h2>
          </div>

          <div className="grid lg:grid-cols-12 gap-8">
            {/* Plan preview */}
            <div className="lg:col-span-7 bg-card border border-line rounded-3xl p-8 sm:p-10">
              <div className="flex items-center gap-3 mb-8">
                <div className="px-3 py-1 bg-green-soft rounded-lg text-[10px] font-bold text-green uppercase tracking-widest">Ukázkový plán</div>
                <span className="text-xs font-semibold text-muted">3 dny · Praha</span>
              </div>

              <div className="space-y-6">
                {SAMPLE_PLAN.days.map((day) => (
                  <div key={day.day} className="flex gap-6 items-start">
                    <div className="w-10 h-10 rounded-xl bg-green text-white flex items-center justify-center font-display font-extrabold text-lg shrink-0 shadow-lg">
                      {day.day}
                    </div>
                    <div className="flex-1 space-y-2">
                      {day.meals.map((meal, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-[10px] font-bold text-muted uppercase tracking-widest w-20 shrink-0">
                            {['Snídaně', 'Oběd', 'Večeře'][i]}
                          </span>
                          <span className="text-sm font-semibold text-ink">{meal}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Shopping list preview */}
            <div className="lg:col-span-5 bg-card border border-line rounded-3xl p-8 sm:p-10">
              <div className="flex items-center gap-3 mb-2">
                <ShoppingCart size={18} className="text-green" />
                <h3 className="font-display text-lg font-bold">Nákupní seznam k receptu</h3>
                <span className="text-[10px] font-bold text-muted uppercase tracking-widest ml-auto">Suroviny</span>
              </div>
              <p className="text-xs font-semibold text-muted mb-8">{SAMPLE_PLAN.recipe.name} · {SAMPLE_PLAN.recipe.portions}</p>

              <div className="space-y-4 mb-8">
                {SAMPLE_PLAN.recipe.ingredients.map((item) => (
                  <div key={item.name} className="flex items-center justify-between border-b border-line pb-3">
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        {item.name}
                        {item.deal && <span className="ml-2 bg-paprika-soft text-paprika-strong font-bold text-[10px] px-1.5 py-0.5 rounded-md align-middle">ve slevě</span>}
                      </p>
                    </div>
                    <p className="font-price text-[13px] font-medium text-muted">{item.unit}</p>
                  </div>
                ))}
              </div>

              <div className="pt-6 border-t-2 border-dashed border-line text-center">
                <p className="font-display text-xl font-bold text-paprika-strong mb-1">{SAMPLE_PLAN.recipe.dealsHeadline}</p>
                <p className="text-[10px] font-bold text-muted uppercase tracking-widest">{SAMPLE_PLAN.recipe.dealsFooter}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="bg-kraft border-y border-line">
        <div className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: BarChart3, title: 'Nutriční hodnoty', desc: 'Kalorie, bílkoviny, sacharidy a tuky u každého jídla' },
              { icon: Wallet, title: 'Slevy u každého receptu', desc: 'U každého receptu vidíte, které suroviny jsou tento týden ve slevě a kde — podle aktuálních letáků českých obchodů' },
              { icon: ChefHat, title: 'Kompletní recepty', desc: 'Postup přípravy krok za krokem se všemi ingrediencemi' },
              { icon: Check, title: 'Interaktivní seznam', desc: 'Odškrtávejte položky přímo v telefonu při nákupu' },
            ].map((f) => (
              <div key={f.title} className="bg-card border border-line rounded-2xl p-8 hover:border-green/40 transition-all">
                <f.icon size={24} className="text-green mb-4" />
                <h4 className="font-display font-bold text-base mb-2">{f.title}</h4>
                <p className="text-muted text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-paper">
        <div className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
          <div className="bg-green-soft border border-line rounded-3xl p-12 sm:p-20 text-center">
            <h2 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight mb-6">
              Připraveni naplánovat týden jídla?
            </h2>
            <p className="text-muted text-lg mb-10 max-w-md mx-auto">
              Začněte se 2 jídelníčky zdarma. Bez kreditní karty.
            </p>
            <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-12 py-5 rounded-2xl font-bold text-base shadow-lg transition-all active:scale-[0.98] inline-flex items-center gap-3">
              Vytvořit můj první plán <ArrowRight size={18} />
            </button>
            <p className="text-muted text-xs font-semibold mt-6">Dostupné v Česku a na Slovensku</p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-ink text-paper">
        <div className="px-6 sm:px-12 py-14 max-w-7xl mx-auto">
          <div className="flex flex-col gap-8">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex flex-col gap-1">
                <span className="font-display font-extrabold text-2xl tracking-tight lowercase text-paper">vařto<span className="text-paprika">.</span></span>
                <span className="text-sm font-semibold text-paper/80">Vařte chytře, nakupujte s přehledem.</span>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-6">
                <a href="/recepty" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">Recepty</a>
                <a href="/pricing" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">Ceník</a>
                <a href="/o-nas" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">O nás</a>
                <a href="/privacy" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">Zásady ochrany soukromí</a>
                <a href="/terms" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">Obchodní podmínky</a>
                <a href="mailto:admin@kentakin.eu" className="text-xs font-semibold text-paper/80 hover:text-paper transition-colors">Kontakt</a>
              </div>
            </div>
            <p className="text-xs text-paper/80 text-center sm:text-left">&copy; {new Date().getFullYear()} Vařto. Všechna práva vyhrazena.</p>
          </div>
        </div>
      </footer>

      {/* Sticky mobile CTA */}
      {showStickyCta && (
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-paper/95 backdrop-blur-lg border-t border-line sm:hidden">
          <button onClick={() => navigate('/login')} className="w-full bg-green hover:bg-green-mid text-white py-4 rounded-xl font-bold text-sm transition-all active:scale-[0.98] flex items-center justify-center gap-2">
            Vytvořit jídelníček zdarma <ArrowRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
};
