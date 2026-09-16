import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PublicHeader } from '@/components/layout/PublicHeader';

/**
 * Customer journey: how to write a prompt for the planner.
 *
 * The example prompts are not invented — they are rephrased from what Czech
 * and Slovak users actually search for (Google Trends CZ + Google/Seznam
 * autocomplete, Sept 2026). Source and rationale: docs/customer-journey-prompting.md.
 * Keep every claim here DB-derivable; no "30-minute recipes", no savings numbers.
 */

const JOURNEY = [
  {
    step: '1',
    title: 'Profil',
    desc: 'Jednou při registraci: stravovací styl (vegetarián, vegan, bezlepkové, keto, vysokoproteinové), alergie, počet osob, čas na vaření a úroveň vaření. Vařto to bere v potaz u každého plánu — nemusíte to psát znovu.',
  },
  {
    step: '2',
    title: 'Zadání',
    desc: 'Krok „Cíle“: jedno textové pole. Napište vlastními slovy, co chcete. Zvolíte zemi a město kvůli slevovým letákům.',
  },
  {
    step: '3',
    title: 'Nastavení jídel',
    desc: 'Krok „Jídla“: která jídla dne chcete (snídaně, oběd, večeře, svačinky) a na kolik dní (1–30).',
  },
  {
    step: '4',
    title: 'Plán',
    desc: 'Za pár minut máte jídelníček: recepty s postupem, kalorie a makra na porci, nákupní seznam ke každému receptu a přehled, které suroviny jsou tento týden v akci.',
  },
  {
    step: '5',
    title: 'Doladění',
    desc: 'U každého receptu je tlačítko „Poradit se s kuchařkou“. Napište „vyměň to za něco rychlejšího“ nebo „něco z kuřete“ a vyberte si z nabídky.',
  },
];

const FORMULA = [
  { part: 'Cíl nebo situace', example: '„chci zhubnout“, „potřebuju navařit na týden“, „rychlé večeře po práci“' },
  { part: 'Z čeho / co chci vařit', example: '„chci vařit z kuřecích prsou a cukety“, „klasická česká kuchyně“' },
  { part: 'Co nechci', example: '„bez hub“, „nic pálivého“, „ne pořád tofu“' },
  { part: 'Čísla', example: '„1 500 kcal denně“, „max 30 minut“, „pro 4 lidi“' },
];

const TIPS = [
  {
    title: 'Pište „chci vařit z…“, ne jen „mám v lednici…“.',
    desc: 'Vařto hledá v zadání suroviny, které chcete použít. „Mám kýtu“ je pro něj informace; „chci uvařit z kýty“ je pokyn.',
  },
  {
    title: 'Alergie a stravovací styl patří do profilu, ne do zadání.',
    desc: 'V profilu jsou závazné pro každý plán i pro každou výměnu receptu.',
  },
  {
    title: 'Chcete jen večeře? V kroku „Jídla“ odškrtněte snídani a oběd.',
    desc: 'Nepište to do zadání — plán by stejně obsahoval všechna jídla, která máte zaškrtnutá.',
  },
];

const SITUATIONS: { title: string; intro?: string; prompts: string[]; tip?: string }[] = [
  {
    title: '„Mám maso a zeleninu, co z toho uvařit?“',
    intro: 'Nejčastější otázka Čechů vůbec. V září vede cuketa, celoročně kuřecí prsa, vepřová kýta a mleté maso.',
    prompts: [
      'Chci tenhle týden vařit hlavně z kuřecích prsou, cukety a brambor. Obědy a večeře na 3 dny, nic složitého.',
      'Koupila jsem kilo vepřové kýty. Chci ji využít v obědech tento týden, k tomu jednoduché večeře bez masa.',
      'Máme spoustu cuket ze zahrady — chci recepty, kde se cuketa opravdu spotřebuje, na celý týden.',
    ],
    tip: 'Pojmenujte suroviny konkrétně („kuřecí prsa“, ne „kuře“) a řekněte, ve kterém jídle dne je chcete.',
  },
  {
    title: '„Chci zhubnout, ale vařit si doma“',
    intro: 'Domácí verze krabičkové diety. Uveďte denní kalorie nebo cílovou váhu a kolik jídel denně chcete (svačinky zapněte v kroku „Jídla“).',
    prompts: [
      'Chci zhubnout 10 kg. 1 500 kcal denně, 5 jídel, jednoduchá domácí jídla jako z krabičkové diety.',
      'Jídelníček na hubnutí pro ženu po padesátce, sedavé zaměstnání, žádné extrémy, obyčejné české suroviny.',
      'Hubnu, chodím 3× týdně do posilovny. Hodně bílkovin, večeře lehké, obědy normální.',
    ],
  },
  {
    title: '„Keto, málo sacharidů, hodně bílkovin“',
    intro: 'Zaškrtněte v profilu Keto / Low-carb nebo Vysokoproteinové a v zadání upřesněte, jak přísně.',
    prompts: [
      'Keto jídelníček na týden. Domácí a levné suroviny, ne drahé speciality.',
      'Lehké večeře bohaté na bílkoviny, do 500 kcal, na celý týden. Obědy klidně s přílohou.',
    ],
  },
  {
    title: '„Rychle, levně, pro rodinu“',
    prompts: [
      'Večeře pro rodinu se dvěma dětmi (5 a 9 let), max 30 minut, nic pálivého, žádné houby ani ryby.',
      'Levné a jednoduché obědy a večeře pro 2 studenty na týden, ať se suroviny vzájemně využijí.',
      'Rychlé večeře po práci z mletého masa, brambor a těstovin, 4 porce.',
    ],
    tip: 'Čas na vaření a počet osob nastavte v profilu; v zadání pak stačí říct, co děti (ne)jedí.',
  },
  {
    title: '„Bez masa, bez lepku“',
    intro: 'Styl nastavte v profilu (Vegetarián, Vegan, Bezlepkové) — pak Vařto nenabídne maso ani při výměně receptu. V zadání řekněte, co vás na bezmasé kuchyni nudí.',
    prompts: [
      'Vegetariánský jídelníček na týden. Ne pořád tofu a čočka — chci i klasiku jako smažený sýr, bramborák, halušky.',
      'Bezlepkové obědy a večeře pro dítě (8 let) na týden, jednoduché, česká kuchyně.',
    ],
  },
  {
    title: '„Sport, nabírání svalů“',
    prompts: [
      'Nabírám svalovou hmotu, 80 kg, trénuju 4× týdně. Zhruba 3 000 kcal a hodně bílkovin, 5 jídel denně.',
      'Jídelníček pro syna (14 let, fotbal 4× týdně) — vydatné obědy a svačiny do školy.',
    ],
  },
  {
    title: '„Pro seniory / měkká strava“',
    prompts: [
      'Jídelníček pro babičku (80 let) na týden. Měkká, nenáročná jídla, klasická česká kuchyně, malé porce.',
    ],
  },
];

const LIMITS = [
  {
    title: 'Léčebné diety',
    desc: 'Jídelníček při cukrovce, vysokém cholesterolu, na žlučník nebo při refluxu patří k nejhledanějším — Vařto ale není zdravotnický nástroj a takové zadání zohlední jen jako obecné přání. Máte-li dietní protokol od lékaře nebo nutričního specialisty, nahrajte ho v kroku „Cíle“ a plán se od něj odvine. Léčbu vždy konzultujte s lékařem.',
  },
  {
    title: 'Cena na porci',
    desc: 'Vařto neukazuje odhad ceny („do 100 Kč na porci“ nesplní). Ukazuje, které suroviny jsou tento týden ve slevě v českých obchodech.',
  },
  {
    title: 'Alergie na ořechy, vejce, ryby a sóju',
    desc: 'Jsou v profilu, ale Vařto je zatím nedokáže stoprocentně vyloučit. Vždy zkontrolujte seznam ingrediencí.',
  },
  {
    title: 'Jazyk',
    desc: 'Zadání pište česky nebo slovensky; plán je česky.',
  },
];

const SectionLabel = ({ children }: { children: string }) => (
  <p className="text-[10px] font-bold text-green uppercase tracking-[0.3em] mb-3">{children}</p>
);

const PromptCard = ({ text }: { text: string }) => (
  <blockquote className="bg-card border border-line rounded-2xl px-5 py-4 text-base font-semibold text-ink leading-relaxed">
    {text}
  </blockquote>
);

export const HowToPrompt = () => (
  <div className="min-h-screen bg-paper text-ink font-body">
    <PublicHeader />

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpět na hlavní stránku
      </Link>

      <SectionLabel>Jak to funguje</SectionLabel>
      <h1 className="font-display text-4xl sm:text-5xl font-black tracking-tighter mb-6">
        Jak napsat zadání, ze kterého vznikne <span className="text-paprika">dobrý jídelníček.</span>
      </h1>
      <p className="text-base text-muted leading-relaxed mb-14 max-w-2xl">
        Průvodce od prvního přihlášení k prvnímu plánu. Příklady zadání nejsou vymyšlené — vycházejí
        z toho, co lidé v Česku a na Slovensku opravdu hledají, když řeší, co vařit.
      </p>

      {/* 1. Journey */}
      <section className="mb-16">
        <SectionLabel>Krok za krokem</SectionLabel>
        <h2 className="font-display text-2xl font-black tracking-tight mb-8">Co se s vaším zadáním stane</h2>
        <ol className="space-y-5">
          {JOURNEY.map((item) => (
            <li key={item.step} className="flex gap-5">
              <div className="shrink-0 w-10 h-10 rounded-xl bg-green flex items-center justify-center font-display font-extrabold text-white shadow-md">
                {item.step}
              </div>
              <div>
                <h3 className="font-display font-bold text-lg mb-1">{item.title}</h3>
                <p className="text-sm text-muted leading-relaxed">{item.desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* 2. Formula */}
      <section className="mb-16 border-t border-line pt-12">
        <SectionLabel>Vzorec</SectionLabel>
        <h2 className="font-display text-2xl font-black tracking-tight mb-3">Čtyři části dobrého zadání</h2>
        <p className="text-sm text-muted leading-relaxed mb-8">Nemusíte mít všechny, ale každá pomůže.</p>
        <div className="grid sm:grid-cols-2 gap-4 mb-10">
          {FORMULA.map((f) => (
            <div key={f.part} className="bg-kraft border border-line rounded-2xl p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-green mb-2">{f.part}</p>
              <p className="text-sm text-ink leading-relaxed">{f.example}</p>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          {TIPS.map((t) => (
            <div key={t.title} className="flex gap-4">
              <span className="shrink-0 mt-2 w-2 h-2 rounded-full bg-paprika" />
              <p className="text-sm leading-relaxed">
                <strong className="text-ink">{t.title}</strong> <span className="text-muted">{t.desc}</span>
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Situations */}
      <section className="mb-16 border-t border-line pt-12">
        <SectionLabel>Příklady</SectionLabel>
        <h2 className="font-display text-2xl font-black tracking-tight mb-10">Nejčastější situace a jak je zadat</h2>
        <div className="space-y-12">
          {SITUATIONS.map((s) => (
            <div key={s.title}>
              <h3 className="font-display text-xl font-bold mb-2">{s.title}</h3>
              {s.intro && <p className="text-sm text-muted leading-relaxed mb-4">{s.intro}</p>}
              <div className="space-y-3">
                {s.prompts.map((p) => <PromptCard key={p} text={p} />)}
              </div>
              {s.tip && <p className="text-xs text-muted leading-relaxed mt-3"><strong className="text-ink">Tip:</strong> {s.tip}</p>}
            </div>
          ))}
        </div>
      </section>

      {/* 4. Limits */}
      <section className="mb-16 border-t border-line pt-12">
        <SectionLabel>Na rovinu</SectionLabel>
        <h2 className="font-display text-2xl font-black tracking-tight mb-8">Co Vařto zatím neumí</h2>
        <div className="space-y-6">
          {LIMITS.map((l) => (
            <div key={l.title}>
              <h3 className="font-display font-bold text-base mb-1">{l.title}</h3>
              <p className="text-sm text-muted leading-relaxed">{l.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 5. After the first plan */}
      <section className="mb-12 border-t border-line pt-12">
        <SectionLabel>Po prvním plánu</SectionLabel>
        <div className="space-y-4 text-sm leading-relaxed">
          <p><strong className="text-ink">Nelíbí se vám jeden recept?</strong> <span className="text-muted">„Poradit se s kuchařkou“ u receptu — napište, co místo něj chcete („něco z ryby“, „rychlejší“, „bez smetany“).</span></p>
          <p><strong className="text-ink">Nesedí celý plán?</strong> <span className="text-muted">Vraťte se ke kroku „Cíle“ a zpřesněte zadání podle vzorce výše. Nejčastější důvod slabého plánu je zadání bez surovin a bez čísel.</span></p>
          <p><strong className="text-ink">První plány jsou zdarma,</strong> <span className="text-muted">bez platební karty.</span></p>
        </div>
      </section>

      <div className="pt-10 border-t border-line">
        <Link
          to="/login"
          className="inline-flex items-center gap-2 rounded-xl bg-green hover:bg-green-mid px-6 py-3 text-sm font-bold text-white transition-colors"
        >
          Vytvořit jídelníček zdarma
        </Link>
      </div>
    </main>
  </div>
);
