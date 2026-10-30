import json
from pathlib import Path
import unittest

from collect_public import encode_url


class PublicCollectionTests(unittest.TestCase):
    def test_cyrillic_urls_are_encoded_without_double_encoding(self):
        self.assertEqual(encode_url('https://example.org/ТН образец.pdf'),
                         'https://example.org/%D0%A2%D0%9D%20%D0%BE%D0%B1%D1%80%D0%B0%D0%B7%D0%B5%D1%86.pdf')
        self.assertEqual(encode_url('https://example.org/a%20b.pdf'), 'https://example.org/a%20b.pdf')

    def test_source_registry_does_not_accept_credentials_or_non_https(self):
        for url in ('file:///local.pdf', 'http://example.org/a.pdf','https://user:secret@example.org/a.pdf'):
            with self.assertRaises(ValueError):
                encode_url(url)

    def test_registered_sources_have_explicit_provenance_and_unique_ids(self):
        entries=json.loads(Path(__file__).with_name('public_sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(entries),len({e['id'] for e in entries}))
        for entry in entries:
            self.assertTrue(entry['family'])
            self.assertTrue(entry['kind'])
            self.assertTrue(entry['industry'])
            self.assertTrue(encode_url(entry['url']).startswith('https://'))

    def test_case_page_selections_fit_the_downloaded_source_lock(self):
        root=Path(__file__).parent
        plan=json.loads((root/'public_cases.json').read_text(encoding='utf-8'))
        sources={r['id']:r for r in json.loads((root/'public_sources.lock.json').read_text(encoding='utf-8'))}
        self.assertEqual(len(plan),len({c['id'] for c in plan}))
        for case in plan:
            source=sources[case['source']]
            self.assertEqual(source['download_status'],'downloaded')
            self.assertEqual(len(case['pages']),len(set(case['pages'])))
            self.assertTrue(all(1<=p<=source['page_count'] for p in case['pages']))

    def test_lock_preserves_failures_instead_of_claiming_every_download_succeeded(self):
        root=Path(__file__).parent
        entries=json.loads((root/'public_sources.json').read_text(encoding='utf-8'))
        lock=json.loads((root/'public_sources.lock.json').read_text(encoding='utf-8'))
        self.assertEqual({r['id'] for r in entries},{r['id'] for r in lock})
        for record in lock:
            if record['download_status']=='downloaded':
                self.assertEqual(len(record['sha256']),64)
                self.assertGreater(record['page_count'],0)
            else:
                self.assertIn('error',record)


if __name__=='__main__':
    unittest.main()
