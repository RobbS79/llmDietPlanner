"""Parsing ranked dish lists into demand terms. Fixtures only — no network."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from diet_planner.services.demand_index import DemandTerm, parse_ranking

FIXTURES = Path(settings.BASE_DIR) / 'diet_planner' / 'tests' / 'fixtures' / 'demand'


class ParseRankingTests(TestCase):
    def _html(self, name):
        return (FIXTURES / name).read_text(encoding='utf-8')

    def test_toprecepty_yields_ranked_terms(self):
        terms = parse_ranking(self._html('toprecepty-top-star.html'),
                              source='toprecepty.cz', category='global')
        self.assertGreaterEqual(len(terms), 15)
        self.assertEqual(terms[0].rank, 1)
        self.assertEqual(terms[1].rank, 2)
        self.assertTrue(all(isinstance(t, DemandTerm) for t in terms))
        self.assertTrue(all(t.source == 'toprecepty.cz' for t in terms))
        self.assertTrue(all(t.category == 'global' for t in terms))

    def test_terms_are_non_empty_dish_names(self):
        terms = parse_ranking(self._html('toprecepty-top-star.html'),
                              source='toprecepty.cz', category='global')
        for t in terms[:15]:
            self.assertGreater(len(t.term), 3)
            self.assertNotIn('\n', t.term)

    def test_recepty_cz_parses_with_the_same_function(self):
        terms = parse_ranking(self._html('recepty-oblibene.html'),
                              source='recepty.cz', category='global')
        self.assertGreaterEqual(len(terms), 10)

    def test_duplicate_links_collapse_and_ranks_stay_dense(self):
        html = '''
          <div><a href="/recept/1-gulas/">Guláš</a></div>
          <div><a href="/recept/1-gulas/">Guláš</a></div>
          <div><a href="/recept/2-svickova/">Svíčková</a></div>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertEqual([(t.term, t.rank) for t in terms],
                         [('Guláš', 1), ('Svíčková', 2)])

    def test_navigation_links_are_ignored(self):
        """Only /recept/<id>-<slug>/ links are dishes; category and paging
        links share the page and must not become demand terms."""
        html = '''
          <a href="/kategorie/46-maso/">Maso</a>
          <a href="/recept/9-kureci-rizek/">Kuřecí řízek</a>
          <a href="/vsechny_recepty.php">Všechny recepty</a>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertEqual([t.term for t in terms], ['Kuřecí řízek'])

    def test_empty_html_yields_nothing_rather_than_raising(self):
        self.assertEqual(parse_ranking('', source='x', category='global'), [])

    def test_toprecepty_top_three_are_the_known_ranking_not_the_suggest_widget(self):
        """toprecepty.cz repeats a 'Mohlo by se vám líbit' suggestion widget
        (ancestor class b-suggest__item) twice, earlier in the document than
        the real ranking grid. If that widget were allowed to count, its five
        unrelated recipes would claim ranks 1-5 instead of the true top-star
        ranking. Values confirmed by manual inspection of the live page."""
        terms = parse_ranking(self._html('toprecepty-top-star.html'),
                              source='toprecepty.cz', category='global')
        self.assertEqual([t.term for t in terms[:3]], [
            'Andělsky nadýchaný perník',
            'Úžasný tvarohový moučník ke kávě',
            'Klasický hospodský guláš (vídeňský)',
        ])

    def test_suggestion_widget_link_does_not_claim_rank_one(self):
        """Minimal reproduction of toprecepty.cz's shape: a suggestion
        widget's recipe link appears before the real ranking grid's first
        item in document order, but must not be treated as rank 1."""
        html = '''
          <article class="b-horizontal b-suggest__item">
            <a href="/recept/999-tip-dish/">Tip Dish</a>
          </article>
          <article class="b-recipe">
            <a href="/recept/1-real-top-dish/">Real Top Dish</a>
          </article>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertNotIn('Tip Dish', [t.term for t in terms])
        self.assertEqual(terms[0].term, 'Real Top Dish')
        self.assertEqual(terms[0].rank, 1)

    def test_recepty_cz_wrapper_and_ellipsis_pattern_yields_full_clean_title(self):
        """Minimal reproduction of recepty.cz's triple-anchor card: an outer
        wrapper anchor carrying a prep-time badge and a nested, CSS-truncated
        title anchor, plus a separate 'více o <full title>' anchor lower in
        the same card. The clean, full, untruncated title must win."""
        html = '''
          <a href="/recept/168830-plny-nazev-receptu/" class="loading-placeholder">
            <div class="recommended-recipes__time">30 minut</div>
            <a href="/recept/168830-plny-nazev-receptu/"><p>Plný název…</p></a>
          </a>
          <p class="recommended-recipes__perex">
            <a href="/recept/168830-plny-nazev-receptu/">více o Plný název receptu</a>
          </p>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0].term, 'Plný název receptu')

    def test_recepty_cz_fixture_has_no_truncated_or_more_about_terms(self):
        """Fixture-level guard: no term from the real recepty.cz page should
        carry a CSS-truncation ellipsis or an unstripped 'více o' ('more
        about') prefix — both are card-chrome, not dish names."""
        terms = parse_ranking(self._html('recepty-oblibene.html'),
                              source='recepty.cz', category='global')
        self.assertTrue(terms)
        for t in terms:
            self.assertNotIn('…', t.term)
            self.assertFalse(t.term.lower().startswith('více o'))
