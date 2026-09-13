#!/usr/bin/env python3
"""Model-independent, local-only report filing. Never runs or changes source files."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

SPORTS = ('cs', 'dota2', 'lol', 'mlb', 'nba', 'soccer', 'valorant')
MODES = ('quick', 'full', 'daily-summary', 'postmortem', 'live', 'historical-replay', 'test', 'diagnostic')
CATEGORIES = {
    'predictions': '賽前預測／文字分析', 'reviews': '賽後檢討', 'live': '賽中分析',
    'replays': '歷史重播／開賽後重建', 'mixed': '混合時點，逐場核驗',
    'examples': '測試／示例', 'diagnostics': '診斷／未完成產物',
}
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'locks'}
REPORT_NAMES = ('report.md', 'prediction.md', 'postmortem.md', 'analysis.md', 'chat-summary.md', 'youtube-script.md')
ARTIFACT_NAMES = {'forecast.json', 'forecasts.json', 'forecasts.jsonl', 'forecast-snapshot.json',
                  'prediction.json', 'evaluation-v2.json'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive_root(value=None):
    return Path(value or os.environ.get('PREDICTION_ARCHIVE_ROOT') or Path.home()/'prediction-archive').expanduser().resolve()


def prepare_reports(base):
    reports = base/'reports'
    if reports.resolve() != reports:
        raise ValueError('reports directory cannot be a symlink')
    reports.mkdir(parents=True, exist_ok=True)
    return reports


def classification(mode, status, eligibilities):
    if mode not in MODES or status not in ('complete', 'incomplete', 'validation-failed'):
        raise ValueError('unsupported mode or status')
    if mode == 'test':
        return 'examples'
    if status != 'complete' or mode == 'diagnostic':
        return 'diagnostics'
    if mode == 'postmortem':
        return 'reviews'
    if mode == 'live':
        return 'live'
    if mode == 'historical-replay':
        return 'replays'
    past = {'historical_replay', 'reconstructed_after_start'} & set(eligibilities)
    prospective = {'prospective', 'prospective_pre_match'} & set(eligibilities)
    return ('mixed' if prospective else 'replays') if past else 'predictions'


def declared_eligibilities(payload):
    """Inspect forecast envelopes only, not training data or embedded old baselines."""
    if isinstance(payload, list):
        return {v for row in payload for v in declared_eligibilities(row)}
    if not isinstance(payload, dict):
        return set()
    result = {str(payload[k]) for k in ('eligibility', 'evaluation_status') if payload.get(k)}
    for key in ('forecasts', 'predictions', 'forecast', 'prediction', 'records'):
        if isinstance(payload.get(key), (dict, list)):
            result.update(declared_eligibilities(payload[key]))
    return result


def scan(source):
    files, excluded, eligibilities = [], [], set()
    for base, dirs, names in os.walk(source, followlinks=False):
        for name in sorted(dirs):
            path = Path(base)/name
            if name in SKIP_DIRS or path.is_symlink():
                excluded.append(str(path.relative_to(source))+'/')
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base)/d).is_symlink())
        for name in sorted(names):
            path = Path(base)/name
            rel = path.relative_to(source).as_posix()
            if (path.is_symlink() or not path.is_file() or name.startswith('.env')
                    or name in {'.DS_Store', '.git'} or path.suffix in {'.pyc', '.pyo'}
                    or any(k in name.lower() for k in ('credential', 'secret', 'private-key'))):
                excluded.append(rel)
                continue
            data = path.read_bytes()
            files.append({'path': rel, 'bytes': len(data), 'sha256': digest(data)})
            if (name in ARTIFACT_NAMES or (name.startswith('f-') and path.suffix == '.json')) and not (
                {'sources', 'originals', 'history', 'diagnostics'} & set(path.relative_to(source).parts[:-1])
            ):
                try:
                    payload = ([json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]
                               if path.suffix == '.jsonl' else json.loads(data))
                    eligibilities.update(declared_eligibilities(payload))
                except (ValueError, UnicodeError):
                    # Keep raw failures. Source validation belongs to the forecasting workflow.
                    pass
    return sorted(files, key=lambda f: f['path']), sorted(excluded), sorted(eligibilities)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def catalog_lock(root, timeout=15):
    """Portable short-lived lock shared by Gemini/Codex processes."""
    lock = root/'.catalog.lock'
    deadline = time.monotonic()+timeout
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError(f'archive index busy; preserve source and retry later: {lock}')
            time.sleep(.05)
    try:
        (lock/'owner.json').write_bytes(encode({'pid': os.getpid()}))
        yield
    finally:
        (lock/'owner.json').unlink(missing_ok=True)
        lock.rmdir()


def verify(directory):
    directory = Path(directory).resolve()
    receipt = json.loads((directory/'archive.json').read_text(encoding='utf-8'))
    if receipt.get('archive_schema_version') != 1 or not (directory/'files').is_dir() or (directory/'files').is_symlink():
        raise ValueError('invalid archive structure')
    identity = receipt['identity']
    if digest(encode(identity)) != receipt['content_id']:
        raise ValueError('archive receipt identity differs')
    expected = identity['files']
    actual, excluded, _ = scan(directory/'files')
    if expected != actual or excluded:
        raise ValueError('archive files differ from receipt')
    return receipt


def build_index(root):
    """Called with catalog lock held. Only owns reports/INDEX.md and index.json."""
    rows = []
    for path in sorted(root.glob('*/*/*/*/archive.json')):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('archive_schema_version') != 1:
            continue
        identity = receipt['identity']
        rows.append({k: identity[k] for k in ('sport', 'category', 'date', 'mode', 'agent', 'model', 'status')} | {
            'archive': path.parent.relative_to(root).as_posix(), 'content_id': receipt['content_id'],
            'archived_at': receipt['archived_at'], 'entrypoints': receipt['entrypoints'],
            'file_count': len(identity['files']), 'declared_eligibilities': identity['declared_eligibilities'],
        })
    rows.sort(key=lambda r: (r['date'], r['archived_at'], r['archive']), reverse=True)
    lines = ['# 自動分類報告索引', '', '原始模板及數字不改寫；分類是保存用途，不是正式評分資格。舊批次封存在上層日期目錄。', '',
             '| 台灣日期 | 運動 | 類型 | 執行 agent | 報告／資料 |', '| --- | --- | --- | --- | --- |']
    for row in rows:
        folder = row['archive']
        target = folder+'/'+(row['entrypoints'][0] if row['entrypoints'] else 'archive.json')
        lines.append(f"| {row['date']} | {row['sport']} | {CATEGORIES[row['category']]} | {row['agent']} | [開啟](<{target}>) |")
    if not rows:
        lines += ['', '尚無依此規則歸檔的新報告。下一次完成報告後，執行 save 即可自動建立目錄及索引。']
    atomic_write(root/'index.json', encode({'archive_schema_version': 1, 'reports': rows})+b'\n')
    atomic_write(root/'INDEX.md', ('\n'.join(lines)+'\n').encode())
    return rows


def save(source, *, sport, target_date, mode, root=None, agent='unknown', model=None,
         status='complete', supersedes=None):
    source = Path(source).expanduser().resolve()
    base = archive_root(root)
    if sport not in SPORTS:
        raise ValueError('unsupported sport; use the active skill mapping')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', target_date):
        raise ValueError('date must be YYYY-MM-DD in Asia/Taipei')
    date.fromisoformat(target_date)
    if agent not in ('codex', 'gemini', 'other', 'unknown'):
        raise ValueError('unsupported agent label')
    if not source.is_dir() or (source/'.git').exists() or (source/'SKILL.md').exists():
        raise ValueError('source must be a dedicated report/run directory')
    if source == base or source in base.parents or base in source.parents:
        raise ValueError('source and archive root must be separate trees')
    # Validate mode/status before any directory creation.
    classification(mode, status, [])
    files, excluded, eligibilities = scan(source)
    if not files:
        raise ValueError('no report artifacts to archive')
    category = classification(mode, status, eligibilities)
    identity = {'source_dir': str(source), 'sport': sport, 'category': category, 'date': target_date,
                'mode': mode, 'status': status, 'agent': agent, 'model': model,
                'supersedes': supersedes, 'files': files, 'excluded': excluded,
                'declared_eligibilities': eligibilities}
    content_id = digest(encode(identity))
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', source.name).strip('-')[:64] or 'report'
    reports = prepare_reports(base)
    target = reports/sport/category/target_date/(slug+'-'+content_id[:20])
    stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=reports))
    try:
        for item in files:
            src = source/item['path']
            dst = stage/'files'/item['path']
            dst.parent.mkdir(parents=True, exist_ok=True)
            data = src.read_bytes()
            if digest(data) != item['sha256']:
                raise ValueError('source changed before copy: '+item['path'])
            with dst.open('xb') as stream:
                stream.write(data)
            shutil.copystat(src, dst)
            dst.chmod(0o400)
        now_files, now_excluded, _ = scan(source)
        if now_files != files or now_excluded != excluded:
            raise ValueError('source changed while archiving; retry after writing finishes')
        entries = sorted(('files/'+f['path'] for f in files if Path(f['path']).suffix.lower() in {'.md', '.html', '.pdf'}),
                         key=lambda p: (REPORT_NAMES.index(Path(p).name) if Path(p).name in REPORT_NAMES else len(REPORT_NAMES), len(p), p))
        receipt = {'archive_schema_version': 1, 'content_id': content_id, 'identity': identity,
                   'archived_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                   'entrypoints': entries, 'eligibility_verified_by_archive': False}
        (stage/'archive.json').write_bytes(encode(receipt)+b'\n')
        (stage/'archive.json').chmod(0o400)
        verify(stage)
        reused = False
        with catalog_lock(reports):
            if target.resolve() != target:
                raise ValueError('archive category path cannot be a symlink')
            if target.exists():
                old = verify(target)
                if old['content_id'] != content_id:
                    raise ValueError('archive path collision; existing version preserved')
                reused = True
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stage.rename(target)
            build_index(reports)
        return {'archive_dir': str(target), 'category': category, 'content_id': content_id,
                'file_count': len(files), 'excluded': excluded, 'reused': reused,
                'report_paths': [str(target/p) for p in entries], 'index': str(reports/'INDEX.md')}
    finally:
        if stage.exists():
            # Windows also treats read-only copies as protected from deletion.
            for path in stage.rglob('*'):
                if path.is_file():
                    path.chmod(0o600)
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('save', help='classify, copy, verify and index a finished report/run')
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--sport', required=True, choices=SPORTS)
    p.add_argument('--date', required=True, dest='target_date')
    p.add_argument('--mode', required=True, choices=MODES)
    p.add_argument('--agent', choices=('codex', 'gemini', 'other', 'unknown'), default='unknown')
    p.add_argument('--model', default=None)
    p.add_argument('--status', choices=('complete', 'incomplete', 'validation-failed'), default='complete')
    p.add_argument('--supersedes', help='prior archive content ID; does not alter that version')
    p.add_argument('--root', type=Path)
    p = sub.add_parser('verify', help='verify a saved bundle without modifying it')
    p.add_argument('directory', type=Path)
    p = sub.add_parser('index', help='rebuild the local report index, including after interrupted writes')
    p.add_argument('--root', type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    try:
        if command == 'save':
            result = save(**args)
        elif command == 'verify':
            receipt = verify(args['directory'])
            result = {'passed': True, 'content_id': receipt['content_id'], 'files': len(receipt['identity']['files'])}
        else:
            root = prepare_reports(archive_root(args['root']))
            with catalog_lock(root):
                rows = build_index(root)
            result = {'index': str(root/'INDEX.md'), 'reports': len(rows)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc), 'source_preserved': True}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
