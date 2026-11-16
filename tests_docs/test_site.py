# this_file: tests_docs/test_site.py
"""Check the actual generated payload, routes and public source boundaries."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs'
PREFIX = '/fontlab-glyport/'
PAGES = ['index.html', 'installation/index.html', 'glyphs-cocoa-and-vanilla/index.html', 'development-and-limits/index.html', 'licence/index.html', 'guides/COMPATIBILITY/index.html', 'guides/GLYPH_INFO_MANAGER/index.html', 'guides/LAYER_IDENTITIES/index.html', 'guides/arabic-presentation/index.html', 'guides/custom-parameters/index.html', 'guides/glyph-descriptions/index.html', 'guides/legacy-and-ros/index.html', 'guides/production-metadata/index.html', 'guides/unicode-lookup/index.html']


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.links = []
        self.text = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for name in ('href', 'src'):
            if name in attrs:
                self.links.append(attrs[name])

    def handle_data(self, data):
        self.text.append(data)


class SiteTests(unittest.TestCase):
    def test_all_generated_internal_links_and_fragments_resolve(self):
        for path in SITE.rglob('*.html'):
            for link in Page(path.read_text()).links:
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue
                target = unquote(url.path)
                if target.startswith('/'):
                    self.assertTrue(target.startswith(PREFIX), (path, link))
                    dest = SITE / target.removeprefix(PREFIX)
                else:
                    dest = path.parent / target if target else path
                if dest.is_dir():
                    dest = dest / 'index.html'
                self.assertTrue(dest.is_file(), (path, link, dest))
                self.assertTrue(dest.resolve().is_relative_to(SITE.resolve()), link)
                if url.fragment and dest.suffix == '.html':
                    self.assertIn(unquote(url.fragment), Page(dest.read_text()).ids, (path, link))

    def test_pages_have_light_menu_footer_local_search_and_correct_canonical(self):
        for route in PAGES:
            page = Page((SITE / route).read_text())
            with self.subTest(route=route):
                self.assertEqual([attrs.get('mode') for tag, attrs in page.tags if tag == 'fontlab-menu'], ['light'])
                self.assertEqual([attrs.get('mode') for tag, attrs in page.tags if tag == 'fontlab-footer'], ['light'])
                self.assertEqual([attrs.get('data-md-color-scheme') for tag, attrs in page.tags if tag == 'body'], ['default'])
                search = [attrs for tag, attrs in page.tags if attrs.get('data-md-component') == 'search-query']
                self.assertEqual(len(search), 1)
                self.assertFalse(any(attrs.get('data-md-component') == 'palette' for _, attrs in page.tags))
                canonical = [attrs['href'] for tag, attrs in page.tags if attrs.get('rel') == 'canonical']
                self.assertEqual(canonical, ['https://fontlabcom.github.io/fontlab-glyport/' + route.removesuffix('index.html')])

    def test_search_indexes_every_authored_page(self):
        search = json.loads((SITE / 'search/search_index.json').read_text())
        locations = {row['location'].split('#')[0] for row in search['docs']}
        self.assertEqual(locations, {'', 'guides/arabic-presentation/', 'licence/', 'glyphs-cocoa-and-vanilla/', 'installation/', 'guides/custom-parameters/', 'guides/unicode-lookup/', 'guides/LAYER_IDENTITIES/', 'guides/legacy-and-ros/', 'guides/glyph-descriptions/', 'guides/production-metadata/', 'guides/COMPATIBILITY/', 'guides/GLYPH_INFO_MANAGER/', 'development-and-limits/'})
        text = ' '.join(row['text'] for row in search['docs'])
        for term in ('GlyphsApp', 'UnsupportedCapability', 'Vanilla'):
            self.assertTrue(term in text, f"Search must retain {term}")

    def test_attribution_downloads_are_exact_and_no_private_payload_is_published(self):
        for source, asset in (('LICENSE', 'assets/LICENSE'), ('NOTICE', 'assets/NOTICE'), ('LICENSE-UNICODE-3.0', 'assets/LICENSE-UNICODE-3.0'), ('realuse/fixtures/getgo/NOTICE', 'assets/legal/NOTICE'), ('realuse/fixtures/getgo/apache/LICENSE.txt', 'assets/legal/apache/LICENSE.txt'), ('realuse/fixtures/getgo/cc0/LICENSE.txt', 'assets/legal/cc0/LICENSE.txt')):
            self.assertEqual((ROOT / source).read_bytes(), (SITE / asset).read_bytes())
        self.assertTrue((SITE / '.nojekyll').is_file())
        private_markers = (b'/Users/', b'/Volumes/', b'/private/', b'ghp_', b'github_pat_', b'-----BEGIN PRIVATE KEY-----')
        sources = [path.read_bytes() for folder in ('src', 'Scripts', 'glyphs', 'examples') if (ROOT / folder).is_dir() for path in (ROOT / folder).rglob('*.py')]
        for path in SITE.rglob('*'):
            if path.is_file():
                self.assertNotIn('.DS_Store', path.parts)
                self.assertNotIn(path.suffix, ('.py', '.pyi', '.vfpy', '.whl', '.zip'))
                payload = path.read_bytes()
                for marker in private_markers:
                    self.assertFalse(marker in payload, (path, marker))
                for source in sources:
                    if len(source) > 80:
                        self.assertFalse(source in payload, path)

    def test_workflow_builds_every_main_push_and_requalifies_immutable_output(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/docs.yml').read_text())
        events = workflow.get('on', workflow.get(True))
        self.assertEqual(events['push'], {'branches': ['main']})
        self.assertNotIn('concurrency', workflow)
        build = workflow['jobs']['build']
        verify = workflow['jobs']['qualify-generated-output']
        self.assertNotIn('concurrency', build)
        self.assertEqual(verify['needs'], 'build')
        self.assertEqual(build['outputs']['epoch'], '${{ steps.epoch.outputs.value }}')
        for job, epoch in ((build, '${{ steps.epoch.outputs.value }}'), (verify, '${{ needs.build.outputs.epoch }}')):
            build_step = next(s for s in job['steps'] if s.get('run') == 'sh src_docs/build.sh')
            self.assertEqual(build_step['env']['SOURCE_DATE_EPOCH'], epoch)
        self.assertEqual(verify['steps'][0]['with']['ref'], '${{ needs.build.outputs.sha }}')
        self.assertEqual(verify['permissions'], {'contents': 'read'})
        for job in (build, verify):
            runs = '\n'.join(step.get('run', '') for step in job['steps'])
            self.assertIn('sh src_docs/build.sh', runs)
            self.assertIn('--require-hashes -r src_docs/requirements.txt', runs)
        self.assertIn('git diff --exit-code HEAD -- docs', '\n'.join(s.get('run', '') for s in verify['steps']))
        self.assertIn('git ls-files --others -- docs', '\n'.join(s.get('run', '') for s in verify['steps']))
        self.assertFalse(any('publish.sh' in s.get('run', '') for s in verify['steps']))

    def test_private_pages_hold_removes_automatic_request_and_permission(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/docs.yml').read_text())
        self.assertNotIn('pages', workflow['permissions'])
        for name, job in workflow['jobs'].items():
            with self.subTest(job=name):
                self.assertNotIn('pages', job['permissions'])
                commands = '\n'.join(step.get('run', '') for step in job['steps'])
                self.assertNotIn('request-pages.sh', commands)
                self.assertNotIn('/pages/builds', commands)

    def test_complete_catalogue_guides_and_readme_contract_survive(self):
        import hashlib
        def canonical(text):
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
            return re.sub(r'\s+', ' ', text.replace('`', '')).strip()
        readme = (ROOT / 'README.md').read_text().split('# Glyport\n', 1)[1]
        index = (ROOT / 'src_docs/md/index.md').read_text()
        self.assertIn(canonical(readme), canonical(index))
        expected = {'src_docs/md/guides/COMPATIBILITY.md': 'aed32e1ebd3b37ce041ffdc5567b3ea60b5da45afadb9d7ce4a0e7f4c9db965b', 'src_docs/md/guides/GLYPH_INFO_MANAGER.md': '99ef44c4f0043a9be0571d4bfc1015ac85a58ed387987073905f28be88428c65', 'src_docs/md/guides/LAYER_IDENTITIES.md': '75c9a92b4b3bb0a90b355ce82f3fa2352c24f99dc65b1588f7364673a1e5709e', 'src_docs/md/guides/arabic-presentation.md': '8082e3c2d448e73f474f5b33b7999786ab5193d28ff7902847ba4b1988bbacba', 'src_docs/md/guides/custom-parameters.md': 'ae864523a8de09eecacf8df5003dfba04f85cea9046777dfdcec61c72242b7d0', 'src_docs/md/guides/glyph-descriptions.md': '5fcb8a76401a7c23bab73d2c99f383582757d3debafaca69041d624c34e3bf1a', 'src_docs/md/guides/legacy-and-ros.md': '8735d1fdbdd3ecf87eccb7661bff6f39844607aedcd854b8a89288a0a7d653f5', 'src_docs/md/guides/production-metadata.md': '648f3f191ef02e91a901218aa41d5e92496b144d7abfc2926ef0c9b8823da377', 'src_docs/md/guides/unicode-lookup.md': 'fd24bd7df90914c359b53a14a7a62f1c4652131129dfa1e4f3981e921bb59f2e'}
        for name, digest in expected.items():
            body = (ROOT / name).read_text().split('---\n', 2)[-1]
            if name == 'src_docs/md/guides/COMPATIBILITY.md':
                alias = '<a id="issue-205--direct-public-api-and-live-outlines"></a>\n\n'
                self.assertEqual(body.count(alias), 1)
                body = body.replace(alias, '', 1)
                self.assertIn('issue-205--direct-public-api-and-live-outlines', Page((SITE / 'guides/COMPATIBILITY/index.html').read_text()).ids)
            self.assertEqual(hashlib.sha256(canonical(body).encode()).hexdigest(), digest, name)
        self.assertEqual(len(expected), 9)
        compatibility = ROOT / 'src_docs/md/guides/COMPATIBILITY.md'
        for name in ('Owned execution scopes', 'Runtime entry points', 'GlyphsApp host services', 'Cocoa backend selection', 'Execution receipts and errors', 'Python 2 source adaptation'):
            self.assertIn(name, compatibility.read_text())
        self.assertTrue((SITE / 'guides/GLYPH_INFO_MANAGER/index.html').is_file())
        self.assertTrue((SITE / 'guides/LAYER_IDENTITIES/index.html').is_file())
