"""Local report filing behavior; fixtures never use the user's archive."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from shared import report_archive as archive


class ReportArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base/'archive root'
        self.source = self.base/'報告 run'
        self.source.mkdir()
        self.report = b'# Report\r\n\r\n| P |\r\n| --- |\r\n| 0.61 |\r\n'
        (self.source/'report.md').write_bytes(self.report)
        (self.source/'forecast.json').write_text(json.dumps({'eligibility': 'prospective', 'probability': 0.61}))

    def save(self, **kwargs):
        args = dict(sport='lol', target_date='2026-09-13', mode='daily-summary', root=self.root, agent='codex')
        args.update(kwargs)
        return archive.save(self.source, **args)

    def index(self):
        return json.loads((self.root/'reports/index.json').read_text())['reports']

    def test_bytes_timestamps_and_originals_are_preserved(self):
        (self.source/'sources').mkdir()
        attachment = self.source/'sources/賽程.json'
        attachment.write_bytes(b'{"complete": true}\n')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode) for p in self.source.rglob('*') if p.is_file()}
        result = self.save(model='actual-model')
        target = Path(result['archive_dir'])
        self.assertEqual(result['category'], 'predictions')
        self.assertEqual(result['file_count'], 3)
        self.assertEqual(Path(result['report_paths'][0]).read_bytes(), self.report)
        for path, original in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode), original)
            copy = target/'files'/path.relative_to(self.source)
            self.assertEqual(copy.read_bytes(), original[0])
            self.assertEqual(copy.stat().st_mtime_ns, original[1])
            self.assertFalse(copy.stat().st_mode & 0o222)
        receipt = archive.verify(target)
        self.assertEqual(receipt['identity']['model'], 'actual-model')
        self.assertFalse(receipt['eligibility_verified_by_archive'])
        self.assertEqual(len(self.index()), 1)

    def test_retries_reuse_and_updates_keep_older_versions(self):
        first = self.save()
        again = self.save()
        self.assertFalse(first['reused'])
        self.assertTrue(again['reused'])
        self.assertEqual(first['archive_dir'], again['archive_dir'])
        (self.source/'report.md').write_text('# Updated\n')
        newer = self.save(supersedes=first['content_id'])
        self.assertNotEqual(first['archive_dir'], newer['archive_dir'])
        self.assertEqual(Path(first['report_paths'][0]).read_bytes(), self.report)
        self.assertEqual(archive.verify(newer['archive_dir'])['identity']['supersedes'], first['content_id'])
        self.assertEqual(len(self.index()), 2)
        self.assertEqual(list((self.root/'reports').glob('.staging-*')), [])

    def test_mode_routing_and_failure_precedence(self):
        expected = {'quick': 'predictions', 'full': 'predictions', 'daily-summary': 'predictions',
                    'postmortem': 'reviews', 'live': 'live', 'historical-replay': 'replays',
                    'test': 'examples', 'diagnostic': 'diagnostics'}
        for mode, category in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(self.save(mode=mode)['category'], category)
        self.assertEqual(self.save(mode='postmortem', status='incomplete')['category'], 'diagnostics')
        self.assertEqual(self.save(status='validation-failed')['category'], 'diagnostics')
        self.assertEqual(self.save(mode='test', status='validation-failed')['category'], 'examples')

    def test_declared_timing_routes_replays_and_mixed_without_rewriting(self):
        forecast = self.source/'forecast.json'
        forecast.write_text(json.dumps({'eligibility': 'historical_replay'}))
        self.assertEqual(self.save()['category'], 'replays')
        forecast.write_text(json.dumps({'forecasts': [{'eligibility': 'prospective'}, {'eligibility': 'reconstructed_after_start'}]}))
        result = self.save()
        self.assertEqual(result['category'], 'mixed')
        self.assertEqual((Path(result['archive_dir'])/'files/forecast.json').read_bytes(), forecast.read_bytes())
        self.assertEqual(self.save(mode='live')['category'], 'live')
        self.assertEqual(self.save(mode='postmortem')['category'], 'reviews')

    def test_old_sources_and_embedded_baselines_do_not_change_current_category(self):
        (self.source/'sources').mkdir()
        (self.source/'sources/forecast.json').write_text('{"eligibility": "historical_replay"}')
        (self.source/'forecast.json').write_text(json.dumps({'eligibility': 'prospective', 'generation_input': {'eligibility': 'historical_replay'}}))
        self.assertEqual(self.save()['category'], 'predictions')

    def test_jsonl_and_text_only_reports_are_supported(self):
        (self.source/'forecast.json').unlink()
        (self.source/'report.md').rename(self.source/'每日報告.md')
        text_only = self.save(agent='gemini')
        self.assertEqual(text_only['category'], 'predictions')
        self.assertEqual(Path(text_only['report_paths'][0]).name, '每日報告.md')
        (self.source/'forecasts.jsonl').write_text('{"eligibility": "reconstructed_after_start"}\n')
        self.assertEqual(self.save(agent='gemini')['category'], 'replays')

    def test_parallel_agents_and_retries_share_a_complete_index(self):
        agents = ['codex', 'gemini'] * 3
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda agent: self.save(agent=agent), agents))
        self.assertEqual(len({r['archive_dir'] for r in results}), 2)
        self.assertEqual(sum(not r['reused'] for r in results), 2)
        self.assertEqual({r['agent'] for r in self.index()}, {'codex', 'gemini'})
        for result in results:
            archive.verify(result['archive_dir'])
        self.assertFalse((self.root/'reports/.catalog.lock').exists())

    def test_environment_files_caches_and_symlinks_are_excluded(self):
        (self.source/'.env').write_text('SAMPLE=fixture')
        (self.source/'credentials.json').write_text('{}')
        (self.source/'__pycache__').mkdir()
        (self.source/'__pycache__/fixture.pyc').write_bytes(b'fixture')
        (self.source/'linked.md').symlink_to(self.source/'report.md')
        (self.source/'linked-dir').symlink_to(self.source/'__pycache__', target_is_directory=True)
        result = self.save()
        self.assertEqual(result['excluded'], ['.env', '__pycache__/', 'credentials.json', 'linked-dir/', 'linked.md'])
        self.assertEqual(result['file_count'], 2)
        self.assertTrue((self.source/'.env').exists())
        archive.verify(result['archive_dir'])

    def test_invalid_metadata_and_overlapping_trees_do_not_write(self):
        cases = [{'sport': '../lol'}, {'target_date': '2026-02-30'}, {'target_date': '../2026-09-13'},
                 {'mode': 'unknown'}, {'status': 'unknown'}, {'agent': 'guessed'},
                 {'root': self.source/'nested'}, {'root': self.base}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.save(**case)
        self.assertFalse(self.root.exists())
        self.assertFalse((self.source/'nested').exists())
        self.assertFalse((self.base/'reports').exists())

    def test_template_or_repository_directory_is_rejected_as_source(self):
        (self.source/'SKILL.md').write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'dedicated'):
            self.save()
        self.assertFalse(self.root.exists())

    def test_tampered_archive_is_detected_and_never_overwritten(self):
        result = self.save()
        copy = Path(result['report_paths'][0])
        copy.chmod(0o600)
        copy.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'files differ'):
            archive.verify(result['archive_dir'])
        with self.assertRaisesRegex(ValueError, 'files differ'):
            self.save()
        self.assertEqual(copy.read_bytes(), b'tampered')
        self.assertEqual((self.source/'report.md').read_bytes(), self.report)

    def test_source_changes_abort_before_committing(self):
        actual_scan = archive.scan
        calls = 0

        def changing_scan(source):
            nonlocal calls
            if source == self.source:
                calls += 1
                if calls == 2:
                    (source/'report.md').write_text('concurrent update')
            return actual_scan(source)

        with patch.object(archive, 'scan', side_effect=changing_scan), self.assertRaisesRegex(ValueError, 'source changed'):
            self.save()
        self.assertEqual(list(self.root.rglob('archive.json')), [])
        self.assertEqual(list((self.root/'reports').glob('.staging-*')), [])

    def test_cli_is_independent_of_cwd_and_honors_configured_root(self):
        cli = Path(archive.__file__).resolve()
        env = dict(os.environ, PREDICTION_ARCHIVE_ROOT=str(self.root))
        command = [sys.executable, str(cli), 'save', '--source', str(self.source), '--sport', 'nba',
                   '--date', '2026-09-12', '--mode', 'full', '--agent', 'gemini']
        result = subprocess.run(command, cwd=self.base, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        saved = json.loads(result.stdout)
        self.assertTrue(Path(saved['archive_dir']).is_relative_to(self.root))
        check = subprocess.run([sys.executable, str(cli), 'verify', saved['archive_dir']], cwd=self.base, text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout+check.stderr)
        self.assertTrue(json.loads(check.stdout)['passed'])
        with patch.dict(os.environ, env):
            self.assertEqual(archive.archive_root(self.base/'override'), self.base/'override')

    def test_index_rebuild_preserves_legacy_archive_and_root_index(self):
        self.root.mkdir()
        root_index = self.root/'INDEX.md'
        root_index.write_text('legacy root index\n')
        legacy = self.root/'2026-09-13/manifest.json'
        legacy.parent.mkdir()
        legacy.write_bytes(b'legacy-original')
        self.save()
        (self.root/'reports/INDEX.md').unlink()
        cli = Path(archive.__file__).resolve()
        result = subprocess.run([sys.executable, str(cli), 'index', '--root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(len(self.index()), 1)
        self.assertTrue((self.root/'reports/INDEX.md').exists())
        self.assertEqual(root_index.read_text(), 'legacy root index\n')
        self.assertEqual(legacy.read_bytes(), b'legacy-original')


if __name__ == '__main__':
    unittest.main()
