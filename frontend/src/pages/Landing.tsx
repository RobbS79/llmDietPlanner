import { useNavigate } from 'react-router-dom';
import { Zap, ShoppingCart, UtensilsCrossed, BarChart3, ArrowRight, Check, ChefHat, List } from 'lucide-react';

const SAMPLE_PLAN = {
  days: [
    { day: 1, meals: ['Ovesna kase s ovocem', 'Kurecí wok s ryzi', 'Losos s brokolicí'] },
    { day: 2, meals: ['Jogurt s granolou', 'Salat s tunakem', 'Hovezi gulas s knedlikem'] },
    { day: 3, meals: ['Vajicka s avokado', 'Tresci file s brambory', 'Kurecí curry s ryzi'] },
  ],
  shoppingList: [
    { name: 'Kurecí prsa', price: '159', unit: '1 kg' },
    { name: 'Losos filet', price: '219', unit: '400 g' },
    { name: 'Ovesne vlocky', price: '42', unit: '500 g' },
    { name: 'Brokolice', price: '39', unit: '1 ks' },
    { name: 'Ryze basmati', price: '55', unit: '1 kg' },
  ],
  total: '1,247',
  currency: 'CZK',
  store: 'Rohlik.cz',
};

export const Landing = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#09090b] text-white overflow-hidden">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-indigo-400 flex items-center justify-center shadow-lg">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter uppercase italic">
            Diet<span className="text-indigo-500 not-italic">Planner.</span>
          </span>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/login')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors">
            Sign In
          </button>
          <button onClick={() => navigate('/login')} className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all">
            Get Started
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative px-6 sm:px-12 pt-16 sm:pt-24 pb-20 max-w-7xl mx-auto">
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-indigo-600/[0.06] blur-[180px] rounded-full" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[700px] h-[700px] bg-purple-600/[0.03] blur-[220px] rounded-full" />

        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 bg-indigo-600/10 border border-indigo-500/20 rounded-full px-4 py-1.5 mb-8">
            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest">AI-Powered Meal Planning</span>
          </div>

          <h1 className="text-5xl sm:text-7xl font-black tracking-tighter leading-[0.9] mb-8">
            Know what you'll eat<br />
            <span className="text-indigo-500">and what you'll spend.</span>
          </h1>

          <p className="text-lg sm:text-xl text-zinc-400 max-w-xl mb-12 leading-relaxed">
            AI generates your personalized meal plan with recipes, nutrition data, and a shopping list with <strong className="text-white">real prices from your local store.</strong>
          </p>

          <div className="flex flex-col sm:flex-row gap-4">
            <button onClick={() => navigate('/login')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] flex items-center justify-center gap-3">
              Create Your Plan <ArrowRight size={18} />
            </button>
            <a href="#how-it-works" className="border border-zinc-700 text-zinc-300 px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest hover:border-zinc-500 transition-all text-center">
              See How It Works
            </a>
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="px-6 sm:px-12 pb-20 max-w-7xl mx-auto">
        <div className="flex flex-wrap gap-8 sm:gap-16 text-center sm:text-left">
          {[
            { value: 'AI-Generated', label: 'Personalized plans' },
            { value: 'Real Prices', label: 'From CZ & SK stores' },
            { value: 'Full Recipes', label: 'Step-by-step instructions' },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="text-2xl sm:text-3xl font-black text-white tracking-tighter">{stat.value}</p>
              <p className="text-xs font-bold text-zinc-600 uppercase tracking-widest mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-[10px] font-black text-indigo-500 uppercase tracking-[1em] mb-4">How It Works</p>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter">Three steps to your meal plan.</h2>
        </div>

        <div className="grid sm:grid-cols-3 gap-8">
          {[
            {
              step: '1',
              icon: UtensilsCrossed,
              title: 'Describe Your Goals',
              desc: 'Tell us what you want — high protein, budget-friendly, vegan, keto — in your own words. Pick your country and preferred grocery store.',
            },
            {
              step: '2',
              icon: ChefHat,
              title: 'AI Creates Your Plan',
              desc: 'Our AI generates a complete multi-day meal plan with breakfast, lunch, dinner, recipes, and full nutritional breakdown.',
            },
            {
              step: '3',
              icon: ShoppingCart,
              title: 'Shop with Real Prices',
              desc: 'Get a shopping list with actual prices from your local store. Know exactly what to buy and what it will cost before you shop.',
            },
          ].map((item) => (
            <div key={item.step} className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-10 hover:border-indigo-500/20 transition-all group">
              <div className="w-12 h-12 rounded-xl bg-indigo-600 flex items-center justify-center text-2xl font-black italic mb-8 shadow-lg group-hover:shadow-indigo-500/20 transition-shadow">
                {item.step}
              </div>
              <item.icon size={32} className="text-indigo-500 mb-6" />
              <h3 className="text-xl font-black tracking-tight mb-4">{item.title}</h3>
              <p className="text-zinc-500 text-sm leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Sample plan preview */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-[10px] font-black text-indigo-500 uppercase tracking-[1em] mb-4">Preview</p>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter">See what you get.</h2>
        </div>

        <div className="grid lg:grid-cols-12 gap-8">
          {/* Plan preview */}
          <div className="lg:col-span-7 bg-zinc-900/50 border border-zinc-800 rounded-3xl p-8 sm:p-10">
            <div className="flex items-center gap-3 mb-8">
              <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-[9px] font-black text-emerald-400 uppercase tracking-widest">Sample Plan</div>
              <span className="text-[10px] font-black text-zinc-700 uppercase tracking-widest">3-Day • Prague</span>
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
                        <span className="text-[9px] font-black text-zinc-700 uppercase tracking-widest w-20 shrink-0">
                          {['Breakfast', 'Lunch', 'Dinner'][i]}
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
              <ShoppingCart size={18} className="text-indigo-500" />
              <h3 className="text-lg font-black uppercase tracking-tight italic">Shopping List</h3>
              <span className="text-[9px] font-black text-zinc-700 uppercase tracking-widest ml-auto">{SAMPLE_PLAN.store}</span>
            </div>

            <div className="space-y-4 mb-8">
              {SAMPLE_PLAN.shoppingList.map((item) => (
                <div key={item.name} className="flex items-center justify-between border-b border-zinc-800 pb-3">
                  <div>
                    <p className="text-sm font-bold text-white">{item.name}</p>
                    <p className="text-[10px] font-bold text-zinc-600">{item.unit}</p>
                  </div>
                  <p className="text-sm font-black text-indigo-400 tabular-nums">{item.price} {SAMPLE_PLAN.currency}</p>
                </div>
              ))}
              <div className="text-center text-zinc-700 text-xs font-bold">+ 12 more items...</div>
            </div>

            <div className="pt-6 border-t-2 border-indigo-600/30">
              <p className="text-[9px] font-black text-zinc-700 uppercase tracking-widest mb-1">Estimated Total</p>
              <p className="text-4xl font-black tracking-tighter">
                {SAMPLE_PLAN.total} <span className="text-indigo-500 text-lg">{SAMPLE_PLAN.currency}</span>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            { icon: BarChart3, title: 'Nutrition Data', desc: 'Calories, protein, carbs, and fat for every meal' },
            { icon: List, title: 'Print & Export', desc: 'Take your shopping list to the store or share it' },
            { icon: ChefHat, title: 'Full Recipes', desc: 'Step-by-step cooking instructions with ingredients' },
            { icon: Check, title: 'Interactive List', desc: 'Check off items as you shop with your phone' },
          ].map((f) => (
            <div key={f.title} className="bg-zinc-950 border border-zinc-800/50 rounded-2xl p-8 hover:border-zinc-700 transition-all">
              <f.icon size={24} className="text-indigo-500 mb-4" />
              <h4 className="font-black text-sm uppercase tracking-tight mb-2">{f.title}</h4>
              <p className="text-zinc-600 text-xs leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 sm:px-12 py-24 max-w-7xl mx-auto">
        <div className="bg-gradient-to-br from-indigo-600/10 to-purple-600/5 border border-indigo-500/10 rounded-[3rem] p-12 sm:p-20 text-center">
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter mb-6">
            Ready to plan your meals?
          </h2>
          <p className="text-zinc-400 text-lg mb-10 max-w-md mx-auto">
            Start with 10 free meal plans. No credit card required.
          </p>
          <button onClick={() => navigate('/login')} className="bg-white text-black px-12 py-5 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3">
            Get Started Free <ArrowRight size={18} />
          </button>
          <p className="text-zinc-700 text-xs font-bold mt-6 uppercase tracking-widest">Available in Czechia & Slovakia</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-zinc-900">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-indigo-500" />
            <span className="text-sm font-black tracking-tighter uppercase italic text-zinc-600">DietPlanner.</span>
          </div>
          <p className="text-xs text-zinc-800">&copy; {new Date().getFullYear()} DietPlanner. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
};
