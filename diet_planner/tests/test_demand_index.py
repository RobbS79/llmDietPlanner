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
