import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { Zap, ShoppingCart, UtensilsCrossed, BarChart3, ArrowRight, Check, ChefHat, List, Star, Quote, Heart, Target, Wallet, Lightbulb, Search, Shield, SlidersHorizontal } from 'lucide-react';

const SAMPLE_PLAN = {
  days: [
    { day: 1, meals: ['Ovesná kaše s ovocem', 'Kuřecí wok s rýží', 'Losos s brokolicí'] },
    { day: 2, meals: ['Jogurt s granolou', 'Salát s tuňákem', 'Hovězí guláš s knedlíkem'] },
    { day: 3, meals: ['Vajíčka s avokádo', 'Treščí filé s brambory', 'Kuřecí curry s rýží'] },
  ],
  shoppingList: [
    { name: 'Kuřecí prsa', price: '159', unit: '1 kg' },
    { name: 'Losos filet', price: '219', unit: '400 g' },
    { name: 'Ovesné vločky', price: '42', unit: '500 g' },
    { name: 'Brokolice', price: '39', unit: '1 ks' },
    { name: 'Rýže basmati', price: '55', unit: '1 kg' },
  ],
  total: '1,247',
  currency: 'CZK',
  store: 'Rohlik.cz',
};

export const Landing = () => {
  const navigate = useNavigate();
  const [showStickyCta, setShowStickyCta] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowStickyCta(window.scrollY > 600);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-[#09090b] text-white overflow-hidden pb-20 sm:pb-0">
      <a href="#main-content" className="skip-to-content">
        Přejít na obsah
      </a>
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-400 flex items-center justify-center shadow-lg">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter uppercase italic">
            Diet<span className="text-emerald-500 not-italic">Planner.</span>
          </span>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/recepty')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors hidden sm:block">
            Recepty
          </button>
          <button onClick={() => navigate('/pricing')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors hidden sm:block">
            Ceník
          </button>
          <button onClick={() => navigate('/login')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors">
            Přihlásit se
          </button>
          <button onClick={() => navigate('/login')} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all">
            Začít zdarma
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section id="main-content" className="relative px-6 sm:px-12 pt-16 sm:pt-24 pb-20 max-w-7xl mx-auto">
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-emerald-600/[0.06] blur-[180px] rounded-full" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[700px] h-[700px] bg-teal-600/[0.03] blur-[220px] rounded-full" />

        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 bg-emerald-600/10 border border-emerald-500/20 rounded-full px-4 py-1.5 mb-8">
            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">AI jídelníček s cenami z obchodu</span>
          </div>

          <h1 className="text-5xl sm:text-7xl font-black tracking-tighter leading-[0.9] mb-8">
            Víte, co budete jíst<br />
            <span className="text-emerald-500">i kolik to bude stát.</span>
          </h1>

          <p className="text-lg sm:text-xl text-zinc-400 max-w-xl mb-4 leading-relaxed">
            AI vytvoří personalizovaný jídelníček s recepty, nutričními hodnotami a nákupním seznamem s <strong className="text-white">reálními cenami z vašeho obchodu.</strong>
          </p>

          <p className="text-sm text-zinc-500 mb-12">Bez kreditní karty. Hotovo za méně než 60 sekund.</p>

          <div className="flex flex-col sm:flex-row gap-4">
            <button onClick={() => navigate('/login')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] flex items-center justify-center gap-3">
              Vytvořit jídelníček zdarma <ArrowRight size={18} />
            </button>
            <a href="#how-it-works" className="border border-zinc-700 text-zinc-300 px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest hover:border-zinc-500 transition-all text-center">
              Jak to funguje
            </a>
          </div>
        </div>
      </section>

      {/* Social proof - metrics */}
      <section className="px-6 sm:px-12 pb-20 max-w-7xl mx-auto">
        <div className="flex flex-wrap gap-8 sm:gap-16 text-center sm:text-left">
          {[
            { value: '500+', label: 'Vygenerovaných plánů' },
            { value: '97%', label: 'Přesnost cen' },
            { value: '<60s', label: 'Čas generování' },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="text-2xl sm:text-3xl font-black text-white tracking-tighter">{stat.value}</p>
              <p className="text-xs font-bold text-zinc-500 uppercase tracking-widest mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Testimonials */}
      <section className="px-6 sm:px-12 pb-20 max-w-7xl mx-auto">
        <div className="grid sm:grid-cols-3 gap-6">
          {[
            {
              quote: 'Ušetřil jsem skoro 400 Kč za týden. Konečně vím, co budu vařit a kolik to bude stát.',
              name: 'Marek T.',
              location: 'Praha',
            },
            {
              quote: 'Dřív jsem nad jídelníčkem strávila 2 hodiny týdně. Teď za 60 sekund mám plán i nákup z Rohlíku. Ušetřím čas i nervy.',
              name: 'Kateřina S.',
              location: 'Brno',
            },
            {
              quote: 'Zhubl jsem 3 kg za měsíc bez hladovění. AI mi přesně spočítá kalorie a vybere recepty, co mě baví.',
              name: 'Tomáš K.',
              location: 'Bratislava',
            },
          ].map((t) => (
            <div key={t.name} className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8">
              <Quote size={20} className="text-emerald-500/40 mb-4" />
              <p className="text-sm text-zinc-300 leading-relaxed mb-6">{t.quote}</p>
              <div className="flex items-center gap-3">
                <div className="flex gap-0.5">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} size={12} className="text-amber-500 fill-amber-500" />
                  ))}
                </div>
                <span className="text-xs font-bold text-zinc-500">{t.name}, {t.location}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Who is this for */}
      <section className="px-6 sm:px-12 pb-20 max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">Pro koho je to</p>
          <h2 className="text-3xl sm:text-4xl font-black tracking-tighter">Vytvořeno pro lidi, kteří...</h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            { icon: Heart, title: 'Chtějí jíst zdravěji', desc: 'Ale neví, kde začít a co vařit' },
            { icon: Target, title: 'Sledují makra a kalorie', desc: 'Ale nenávidí plánování jídel' },
            { icon: Wallet, title: 'Chtějí šetřit za jídlo', desc: 'A vědět přesně, kolik utratí před nákupem' },
            { icon: Lightbulb, title: 'Vaří doma', desc: 'Ale dochází jim nápady na recepty' },
          ].map((item) => (
            <div key={item.title} className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8 text-center hover:border-emerald-500/20 transition-all">
              <item.icon size={28} className="text-emerald-500 mx-auto mb-4" />
              <h4 className="font-black text-sm uppercase tracking-tight mb-2">{item.title}</h4>
              <p className="text-zinc-500 text-xs leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">Jak to funguje</p>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter">Tři kroky k vašemu jídelníčku.</h2>
        </div>

        <div className="grid sm:grid-cols-3 gap-8">
          {[
            {
              step: '1',
              icon: UtensilsCrossed,
              title: 'Popište své cíle',
              desc: 'Řekněte nám, co chcete — vysoko proteinová, levná, veganská, keto — vlastními slovy. Vyberte zemi a oblíbený obchod.',
            },
            {
              step: '2',
              icon: ChefHat,
              title: 'AI vytvoří plán',
              desc: 'Naše AI vygeneruje kompletní vícedenní jídelníček se snídaní, obědem, večeří, recepty a nutričními hodnotami.',
            },
            {
              step: '3',
              icon: ShoppingCart,
              title: 'Nakupujte s reálními cenami',
              desc: 'Dostanete nákupní seznam s aktuálními cenami z vašeho obchodu. Víte přesně, co koupit a kolik to bude stát.',
            },
          ].map((item) => (
            <div key={item.step} className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-10 hover:border-emerald-500/20 transition-all group">
              <div className="w-12 h-12 rounded-xl bg-emerald-600 flex items-center justify-center text-2xl font-black italic mb-8 shadow-lg group-hover:shadow-emerald-500/20 transition-shadow">
                {item.step}
              </div>
              <item.icon size={32} className="text-emerald-500 mb-6" />
              <h3 className="text-xl font-black tracking-tight mb-4">{item.title}</h3>
              <p className="text-zinc-500 text-sm leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* AI transparency */}
      <section className="px-6 sm:px-12 pb-24 max-w-7xl mx-auto">
        <div className="bg-zinc-900/30 border border-zinc-800 rounded-3xl p-8 sm:p-12">
          <div className="text-center mb-12">
            <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">Jak naše AI funguje</p>
            <h2 className="text-3xl sm:text-4xl font-black tracking-tighter">Transparentně a pod vaší kontrolou.</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: Search, title: 'Analyzuje vaše cíle', desc: 'Pochopí vaše stravovací potřeby, omezení i rozpočet' },
              { icon: ChefHat, title: 'Vytvoří vyvážená jídla', desc: 'Každý plán splňuje nutriční doporučení pro vaše cíle' },
              { icon: ShoppingCart, title: 'Ověřuje reálné ceny', desc: 'Stahuje aktuální ceny z vašeho oblíbeného obchodu' },
              { icon: SlidersHorizontal, title: 'Vy máte kontrolu', desc: 'Upravte, regenerujte nebo změňte cokoliv kdykoliv' },
            ].map((item) => (
              <div key={item.title} className="text-center">
                <div className="w-12 h-12 rounded-xl bg-emerald-600/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-4">
                  <item.icon size={22} className="text-emerald-400" />
                </div>
                <h4 className="font-black text-sm tracking-tight mb-2">{item.title}</h4>
                <p className="text-zinc-500 text-xs leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sample plan preview */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">Ukázka</p>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter">Podívejte se, co dostanete.</h2>
        </div>

        <div className="grid lg:grid-cols-12 gap-8">
          {/* Plan preview */}
          <div className="lg:col-span-7 bg-zinc-900/50 border border-zinc-800 rounded-3xl p-8 sm:p-10">
            <div className="flex items-center gap-3 mb-8">
              <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-[9px] font-black text-emerald-400 uppercase tracking-widest">Ukázkový plán</div>
              <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">3 dny • Praha</span>
            </div>

            <div className="space-y-6">
              {SAMPLE_PLAN.days.map((day) => (
                <div key={day.day} className="flex gap-6 items-start">
                  <div className="w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center font-black text-lg italic shrink-0 shadow-lg">
                    {day.day}
                  </div>
                  <div className="flex-1 space-y-2">
                    {day.meals.map((meal, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest w-20 shrink-0">
                          {['Snídaně', 'Oběd', 'Večeře'][i]}
                        </span>
                        <span className="text-sm font-bold text-zinc-300">{meal}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Shopping list preview */}
          <div className="lg:col-span-5 bg-zinc-900/50 border border-zinc-800 rounded-3xl p-8 sm:p-10">
            <div className="flex items-center gap-3 mb-8">
              <ShoppingCart size={18} className="text-emerald-500" />
              <h3 className="text-lg font-black uppercase tracking-tight italic">Nákupní seznam</h3>
              <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest ml-auto">{SAMPLE_PLAN.store}</span>
            </div>

            <div className="space-y-4 mb-8">
              {SAMPLE_PLAN.shoppingList.map((item) => (
                <div key={item.name} className="flex items-center justify-between border-b border-zinc-800 pb-3">
                  <div>
                    <p className="text-sm font-bold text-white">{item.name}</p>
                    <p className="text-[10px] font-bold text-zinc-600">{item.unit}</p>
                  </div>
                  <p className="text-sm font-black text-emerald-400 tabular-nums">{item.price} {SAMPLE_PLAN.currency}</p>
                </div>
              ))}
              <div className="text-center text-zinc-500 text-xs font-bold">+ 12 dalších položek...</div>
            </div>

            <div className="pt-6 border-t-2 border-emerald-600/30">
              <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-1">Odhadovaná cena celkem</p>
              <p className="text-4xl font-black tracking-tighter">
                {SAMPLE_PLAN.total} <span className="text-emerald-500 text-lg">{SAMPLE_PLAN.currency}</span>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            { icon: BarChart3, title: 'Nutriční hodnoty', desc: 'Kalorie, bílkoviny, sacharidy a tuky u každého jídla' },
            { icon: List, title: 'Tisk a export', desc: 'Vezmete si nákupní seznam do obchodu nebo ho sdílíte' },
            { icon: ChefHat, title: 'Kompletní recepty', desc: 'Postup přípravy krok za krokem se všemi ingrediencemi' },
            { icon: Check, title: 'Interaktivní seznam', desc: 'Odškrtávejte položky přímo v telefonu při nákupu' },
          ].map((f) => (
            <div key={f.title} className="bg-zinc-950 border border-zinc-800/50 rounded-2xl p-8 hover:border-zinc-700 transition-all">
              <f.icon size={24} className="text-emerald-500 mb-4" />
              <h4 className="font-black text-sm uppercase tracking-tight mb-2">{f.title}</h4>
              <p className="text-zinc-600 text-xs leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border border-emerald-500/10 rounded-3xl p-12 sm:p-20 text-center">
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter mb-6">
            Připraveni plánovat své jídlo?
          </h2>
          <p className="text-zinc-400 text-lg mb-10 max-w-md mx-auto">
            Začněte s 10 plány zdarma. Bez kreditní karty.
          </p>
          <button onClick={() => navigate('/login')} className="bg-white text-black px-12 py-5 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3">
            Vytvořit můj první plán <ArrowRight size={18} />
          </button>
          <p className="text-zinc-500 text-xs font-bold mt-6 uppercase tracking-widest">Dostupné v Česku a na Slovensku</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-zinc-900">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Zap size={16} className="text-emerald-500" />
              <span className="text-sm font-black tracking-tighter uppercase italic text-zinc-600">DietPlanner.</span>
            </div>
            <div className="flex items-center gap-6">
              <a href="/recepty" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Recepty</a>
              <a href="/pricing" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Ceník</a>
              <a href="/privacy" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Zásady ochrany soukromí</a>
              <a href="/terms" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Obchodní podmínky</a>
              <a href="mailto:support@dietplanner.cz" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Kontakt</a>
            </div>
          </div>
          <p className="text-xs text-zinc-500 text-center sm:text-left">&copy; {new Date().getFullYear()} DietPlanner. All rights reserved.</p>
        </div>
      </footer>

      {/* Sticky mobile CTA */}
      {showStickyCta && (
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-[#09090b]/95 backdrop-blur-lg border-t border-zinc-800 sm:hidden">
          <button onClick={() => navigate('/login')} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-4 rounded-xl font-black uppercase text-xs tracking-widest transition-all active:scale-[0.98] flex items-center justify-center gap-2">
            Vytvořit jídelníček zdarma <ArrowRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
};
