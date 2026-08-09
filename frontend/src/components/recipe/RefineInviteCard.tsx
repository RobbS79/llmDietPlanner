import { MessageCircle } from 'lucide-react';

/** One-tap openers. Tapping a chip opens the chat AND sends it as the first
 * message, so the shortest path to an alternative is a single tap — and the
 * chip labels double as a menu of what this conversation can actually do. */
const INTENT_CHIPS = [
  'Nemám na tohle chuť',
  'Chci něco rychlejšího',
  'Chci něco úplně jiného',
  'Mám doma jiné suroviny',
];

interface RefineInviteCardProps {
  /** Opens the chat; with `seed` the chat sends that text as message one. */
  onOpen: (seed?: string) => void;
}

/**
 * Entry point into the refine chat. Replaces the old bare "Vyměnit recept"
 * button, which read as a re-roll toggle and hid the fact that there is a
 * conversation behind it that can also fetch a brand-new recipe off the web.
 */
export const RefineInviteCard = ({ onOpen }: RefineInviteCardProps) => (
  <section
    aria-labelledby="refine-invite-title"
    className="rounded-2xl border border-line bg-card p-6 sm:p-8 max-w-2xl transition-colors hover:border-green/40"
  >
    <h2
      id="refine-invite-title"
      className="flex items-center gap-2 font-display text-lg font-black uppercase tracking-tighter italic text-ink"
    >
      <MessageCircle size={18} className="shrink-0 text-green" />
      Nesedí vám tohle jídlo?
    </h2>

    <p className="mt-2 text-sm leading-relaxed text-muted">
      Napište naší kuchařce, co byste chtěli jinak — najde vám jiné varianty
      a společně vyberete tu, která sedí.
    </p>

    <div className="mt-5 flex flex-wrap gap-2">
      {INTENT_CHIPS.map((chip) => (
        <button
          key={chip}
          type="button"
          onClick={() => onOpen(chip)}
          className="h-11 px-4 rounded-full border border-line bg-paper text-sm font-semibold text-ink hover:border-green/60 hover:text-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 transition-colors"
        >
          {chip}
        </button>
      ))}
    </div>

    <button
      type="button"
      onClick={() => onOpen()}
      className="mt-6 flex w-full sm:w-auto items-center justify-center gap-2 h-12 px-6 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl hover:bg-green-mid active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 focus-visible:ring-offset-2 transition-all"
    >
      <MessageCircle size={14} /> Poradit se s kuchařkou
    </button>
  </section>
);
