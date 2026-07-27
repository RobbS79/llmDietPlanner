import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipeRefineChat } from './RecipeRefineChat';
import { refinePreview, refineAccept, researchStatus } from '@/lib/refineRecipe';

vi.mock('@/lib/refineRecipe', () => ({
  refinePreview: vi.fn(), refineAccept: vi.fn(), researchStatus: vi.fn(),
}));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const CANDIDATE = {
  curated_recipe_id: 7, name: 'Kuřecí salát', description: '',
  food_category: '', preparation_time: 15, calories: 420, why: 'Odpovídá: kuřecí',
};

function setup() {
  const onAccepted = vi.fn();
  const onClose = vi.fn();
  render(
    <ToastProvider>
      <RecipeRefineChat mealId={MEAL_ID} onAccepted={onAccepted} onClose={onClose} />
    </ToastProvider>,
  );
  return { onAccepted, onClose };
}

async function send(text: string) {
  await userEvent.type(screen.getByPlaceholderText('Napište, na co máte chuť…'), text);
  await userEvent.click(screen.getByRole('button', { name: 'Odeslat' }));
}

describe('RecipeRefineChat', () => {
  // resetAllMocks also drains mockResolvedValueOnce queues a failed test leaves behind.
  beforeEach(() => vi.resetAllMocks());

  it('first turn shows the candidate card and the follow-up question', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: 'Chcete to spíš rychlé?', hint_matched: true,
    });
    setup();
    await send('něco s kuřecím');

    expect(refinePreview).toHaveBeenCalledWith(
      MEAL_ID, [{ role: 'user', text: 'něco s kuřecím' }], [],
    );
    expect(await screen.findByText(/Co třeba: Kuřecí salát\?/)).toBeInTheDocument();
    expect(screen.getByText(/Chcete to spíš rychlé\?/)).toBeInTheDocument();
    expect(screen.getByText('Odpovídá: kuřecí')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
  });

  it('typing again rejects the shown candidate and sends the transcript', async () => {
    vi.mocked(refinePreview)
      .mockResolvedValueOnce({ candidate: CANDIDATE, question: 'Rychlé?', hint_matched: true })
      .mockResolvedValueOnce({
        candidate: { ...CANDIDATE, curated_recipe_id: 8, name: 'Těstoviny' },
        question: null, hint_matched: true,
      });
    setup();
    await send('něco s kuřecím');
    await screen.findByText(/Co třeba: Kuřecí salát\?/);
    await send('něco jiného');

    const second = vi.mocked(refinePreview).mock.calls[1];
    expect(second[2]).toEqual([7]); // previous candidate now rejected
    // Transcript carries user turns AND the assistant turn.
    expect(second[1].map((m: any) => m.role)).toEqual(['user', 'assistant', 'user']);
  });

  it('unmatched turn uses the honest fallback phrasing', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: false,
    });
    setup();
    await send('něco s tofu');
    expect(
      await screen.findByText(/Přesně podle vašeho přání jsme nic nenašli, ale co třeba: Kuřecí salát\?/),
    ).toBeInTheDocument();
  });

  it('accept calls the API and bubbles the recipe up', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    vi.mocked(refineAccept).mockResolvedValue({ replaced: true, recipe: { name: 'Kuřecí salát' } });
    const { onAccepted } = setup();
    await send('něco s kuřecím');
    await userEvent.click(await screen.findByRole('button', { name: 'Použít tento recept' }));

    expect(refineAccept).toHaveBeenCalledWith(MEAL_ID, 7);
    expect(onAccepted).toHaveBeenCalledWith({ name: 'Kuřecí salát' });
  });

  it('shows no-alternatives message with a restart action', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: null, question: null, hint_matched: false, reason: 'no_alternatives',
    });
    setup();
    await send('cokoli');
    expect(
      await screen.findByText('Pro tento typ jídla už nemáme další alternativu.'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Začít znovu' }));
    // Restart clears everything: the input is usable again, transcript gone.
    expect(screen.queryByText('Pro tento typ jídla už nemáme další alternativu.')).toBeNull();
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toBeEnabled();
  });

  it('disables input after 8 user messages and shows the closing prompt', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: 'Ještě něco?', hint_matched: true,
    });
    setup();
    for (let i = 0; i < 8; i++) {
      await send(`zpráva ${i}`);
      await screen.findAllByText(/Co třeba: Kuřecí salát\?/);
    }
    expect(
      await screen.findByText('To je pro dnešek vše — vyberte si recept, nebo začněte znovu.'),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Napište, na co máte chuť…')).toBeNull();
    // The candidate is still acceptable after the cap.
    expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
  });

  it('a failed turn preserves state and restores the draft for retry', async () => {
    vi.mocked(refinePreview).mockRejectedValueOnce(new Error('boom'));
    setup();
    await send('něco s kuřecím');
    expect(
      await screen.findByText('Něco se nepovedlo, zkuste to prosím znovu.'),
    ).toBeInTheDocument();
    // The message was rolled back (not burned from the 8 budget) and the
    // draft text is back in the input.
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toHaveValue('něco s kuřecím');
    expect(refinePreview).toHaveBeenCalledTimes(1);
  });

  it('Enter key sends the message', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    setup();
    await userEvent.type(
      screen.getByPlaceholderText('Napište, na co máte chuť…'), 'něco s kuřecím{enter}',
    );
    expect(await screen.findByText(/Co třeba: Kuřecí salát\?/)).toBeInTheDocument();
    expect(refinePreview).toHaveBeenCalledTimes(1);
  });

  it('Zavřít calls onClose', async () => {
    const { onClose } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Zavřít' }));
    expect(onClose).toHaveBeenCalled();
  });

  describe('past suggestions stay clickable', () => {
    const CANDIDATE2 = { ...CANDIDATE, curated_recipe_id: 8, name: 'Těstoviny', why: null };

    /** Two preview turns: Kuřecí salát (7), then Těstoviny (8) active. */
    async function twoTurns() {
      vi.mocked(refinePreview)
        .mockResolvedValueOnce({ candidate: CANDIDATE, question: null, hint_matched: true })
        .mockResolvedValueOnce({ candidate: CANDIDATE2, question: null, hint_matched: true });
      const cb = setup();
      await send('něco s kuřecím');
      await screen.findByText(/Co třeba: Kuřecí salát\?/);
      await send('něco jiného');
      await screen.findByText(/Co třeba: Těstoviny\?/);
      return cb;
    }

    it('clicking a past suggestion line re-expands its card and collapses the displaced one', async () => {
      await twoTurns();
      const firstLine = screen.getByRole('button', { name: 'Zobrazit tento návrh' });
      expect(firstLine).toHaveTextContent('Co třeba: Kuřecí salát?');
      await userEvent.click(firstLine);
      // The old candidate is the full card again…
      expect(screen.getByText('Kuřecí salát')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
      // …and the displaced candidate's line became clickable (symmetric swap).
      expect(screen.getByRole('button', { name: 'Zobrazit tento návrh' }))
        .toHaveTextContent('Co třeba: Těstoviny?');
    });

    it('accepting a re-expanded old suggestion commits the old id', async () => {
      const { onAccepted } = await twoTurns();
      vi.mocked(refineAccept).mockResolvedValue({ replaced: true, recipe: { name: 'Kuřecí salát' } });
      await userEvent.click(screen.getByRole('button', { name: 'Zobrazit tento návrh' }));
      await userEvent.click(screen.getByRole('button', { name: 'Použít tento recept' }));
      expect(refineAccept).toHaveBeenCalledWith(MEAL_ID, 7);
      expect(onAccepted).toHaveBeenCalledWith({ name: 'Kuřecí salát' });
    });

    it('typing after re-expanding rejects the re-expanded candidate only', async () => {
      await twoTurns();
      vi.mocked(refinePreview).mockResolvedValueOnce({
        candidate: { ...CANDIDATE, curated_recipe_id: 9, name: 'Polévka' },
        question: null, hint_matched: true,
      });
      await userEvent.click(screen.getByRole('button', { name: 'Zobrazit tento návrh' }));
      await send('ještě něco jiného');
      const third = vi.mocked(refinePreview).mock.calls[2];
      // 7 was re-expanded and is implicitly rejected again (no duplicate);
      // 8 was displaced by a manual click, never rejected.
      expect(third[2]).toEqual([7]);
    });

    it('past-suggestion lines remain clickable after the 8-message cap', async () => {
      for (let i = 0; i < 8; i++) {
        vi.mocked(refinePreview).mockResolvedValueOnce({
          candidate: { ...CANDIDATE, curated_recipe_id: i + 1, name: `Recept ${i + 1}` },
          question: null, hint_matched: true,
        });
      }
      setup();
      for (let i = 0; i < 8; i++) {
        await send(`zpráva ${i}`);
        await screen.findByText(new RegExp(`Co třeba: Recept ${i + 1}\\?`));
      }
      await screen.findByText('To je pro dnešek vše — vyberte si recept, nebo začněte znovu.');
      const lines = screen.getAllByRole('button', { name: 'Zobrazit tento návrh' });
      expect(lines).toHaveLength(7);
      await userEvent.click(lines[0]);
      expect(screen.getByText('Recept 1')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
    });

    it('refinePreview payload carries only {role, text} entries', async () => {
      await twoTurns();
      const second = vi.mocked(refinePreview).mock.calls[1];
      for (const m of second[1]) {
        expect(Object.keys(m).sort()).toEqual(['role', 'text']);
      }
    });
  });

  describe('v2 agent replies', () => {
    /** RTL's asyncWrapper drains microtasks via a real `setTimeout(0)` and only
     * auto-advances it when a `jest` global exists — under vitest fake timers
     * every userEvent action would deadlock. Stub the one method it calls. */
    function useFakeTimersRtlSafe() {
      vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    }

    /** send() variant for fake-timer tests: delay:null keeps userEvent off the
     * (mocked) clock entirely. */
    async function sendFake(text: string) {
      const user = userEvent.setup({ delay: null });
      await user.type(screen.getByPlaceholderText('Napište, na co máte chuť…'), text);
      await user.click(screen.getByRole('button', { name: 'Odeslat' }));
    }

    it('renders reply_text verbatim when present', async () => {
      vi.mocked(refinePreview).mockResolvedValueOnce({
        candidate: null, question: null, hint_matched: null,
        reply_text: 'Menemen vám přijde snídaňový? Chcete něco vydatnějšího?',
        research_job_id: null,
      });
      setup();
      await send('Vypadá to jak snídaně');
      expect(await screen.findByText(/Chcete něco vydatnějšího/)).toBeInTheDocument();
      // A null candidate with reply_text is a conversational turn, NOT a dead end.
      expect(screen.queryByText('Pro tento typ jídla už nemáme další alternativu.')).toBeNull();
    });

    it('starts polling when research_job_id returned and pops the card on ready', async () => {
      useFakeTimersRtlSafe();
      try {
        vi.mocked(refinePreview).mockResolvedValueOnce({
          candidate: null, question: null, hint_matched: null,
          reply_text: 'Hledám recept na webu…', research_job_id: 42,
        });
        vi.mocked(researchStatus)
          .mockResolvedValueOnce({ status: 'searching', reply_text: null, candidate: null })
          .mockResolvedValueOnce({
            status: 'ready',
            reply_text: 'Našel jsem: Pravý ramen.',
            candidate: { curated_recipe_id: 7, name: 'Pravý ramen', description: '',
                         food_category: '', preparation_time: 40, calories: 600, why: null },
          });
        setup();
        await sendFake('pravý ramen');
        await act(async () => {});
        // Bubble text + persistent searching indicator both mention the search.
        expect(screen.getAllByText(/Hledám recept na webu/).length).toBeGreaterThan(0);
        await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
        await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
        expect(screen.getByText(/Našel jsem: Pravý ramen/)).toBeInTheDocument();
        expect(screen.getByText('Pravý ramen')).toBeInTheDocument(); // card
        expect(screen.getByRole('button', { name: 'Použít tento recept' })).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
        vi.unstubAllGlobals();
      }
    });

    it('renders failure reply_text and stops polling on failed', async () => {
      useFakeTimersRtlSafe();
      try {
        vi.mocked(refinePreview).mockResolvedValueOnce({
          candidate: null, question: null, hint_matched: null,
          reply_text: 'Hledám…', research_job_id: 43,
        });
        vi.mocked(researchStatus).mockResolvedValueOnce({
          status: 'failed',
          reply_text: 'Bohužel jsem na webu nenašel žádný vhodný recept.',
          candidate: null,
        });
        setup();
        await sendFake('jednorožčí guláš');
        await act(async () => {});
        await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
        expect(screen.getByText(/nenašel žádný vhodný recept/)).toBeInTheDocument();
        expect(vi.mocked(researchStatus)).toHaveBeenCalledTimes(1);
        await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
        expect(vi.mocked(researchStatus)).toHaveBeenCalledTimes(1); // stopped
      } finally {
        vi.useRealTimers();
        vi.unstubAllGlobals();
      }
    });
  });
});
