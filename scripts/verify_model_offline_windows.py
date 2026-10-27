"""Explicit actual-model-offline UI acceptance, preserving the existing UI.

This stops only the fully identified project model and always attempts restoration.
Run only after formal experiments and interactive work have finished:
    .venv/Scripts/python.exe scripts/verify_model_offline_windows.py --execute
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from project_lifecycle import Project, ROOT, project_mutex
from verify_launcher_windows import protected_hash, service_ids, verify_frozen_campaigns


def active_runs(database):
    if not database.is_file():
        return 0
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        return sum(json.loads(row[0]).get('record', {}).get('status') in {'running', 'stopping'}
                   for row in connection.execute('SELECT data FROM runs'))
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error('Pass --execute only when no interactive or formal model work is active.')
    if os.name != 'nt':
        parser.error('This actual lifecycle validation is Windows-only.')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    campaigns = verify_frozen_campaigns(ROOT)
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for the isolated browser check.')
    if active_runs(ROOT / 'results/v2/web_private/sessions.sqlite'):
        raise RuntimeError('Interactive runs are active; no model process was stopped.')
    directory = ROOT / 'results/v2/browser'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / 'model-offline-lifecycle.json'
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'all_passed': False,
              'campaigns': campaigns, 'protected_before': protected_hash(ROOT),
              'scope': 'Stop fully identified project model only, inspect real isolated browser UI, restore model while retaining UI process. No mock inference or system network changes.'}
    project = Project()
    with project_mutex(project.root, float(project.settings['operation_lock_timeout_seconds'])):
        initial = project.inspect()
        report['initial'] = initial
        if not all(item['healthy'] and not item['conflicts'] for item in initial.values()):
            raise RuntimeError('Both project services must be healthy and fully identified before verification.')
        initial_ui = service_ids(initial)['ui']
        try:
            for identity in initial['model']['owned'] + initial['model'].get('launchers', []):
                project.stop_identity('model', identity, 'explicit_model_offline_UI_acceptance')
            offline = project.inspect()
            report['offline'] = offline
            assert not offline['model']['owned'] and not offline['model']['listeners'] and not offline['model']['healthy']
            assert offline['ui']['healthy'] and service_ids(offline)['ui'] == initial_ui
            result = subprocess.run([node, str(ROOT / 'scripts/verify_model_offline_ui.cjs'), 'offline'], cwd=ROOT, timeout=90)
            report['offline_browser_exit_code'] = result.returncode
            assert result.returncode == 0, 'Actual offline browser verification failed.'
        except Exception as error:
            report['error'] = {'type': type(error).__name__, 'message': str(error)}
        finally:
            # Restore even if a screenshot or assertion failed. start() reuses the
            # surviving UI and verifies the model identity, listener and health.
            try:
                restored = project.start(open_browser=False)
                report['restored'] = restored
                report['same_UI_identity'] = service_ids(restored)['ui'] == initial_ui
                result = subprocess.run([node, str(ROOT / 'scripts/verify_model_offline_ui.cjs'), 'restored'], cwd=ROOT, timeout=90)
                report['restored_browser_exit_code'] = result.returncode
            except Exception as error:
                report['restoration_error'] = {'type': type(error).__name__, 'message': str(error)}
            report['protected_after'] = protected_hash(ROOT)
            report['protected_unchanged'] = report['protected_before'] == report['protected_after']
            report['all_passed'] = (not report.get('error') and not report.get('restoration_error')
                                    and report.get('offline_browser_exit_code') == 0 and report.get('restored_browser_exit_code') == 0
                                    and report.get('same_UI_identity') and report['protected_unchanged'])
            report['events'] = project.events
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'all_passed': report['all_passed'], 'evidence': str(output)}, ensure_ascii=False), flush=True)
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
