"""The read-only release verifier must target the requested immutable release."""
import importlib.util
import io
import json
from pathlib import Path

import pytest


def verifier():
    path = Path(__file__).resolve().parents[1] / 'scripts/verify_public_download.py'
    spec = importlib.util.spec_from_file_location('release_download', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bad_tag_rejected_before_directory_or_network(tmp_path, monkeypatch):
    m = verifier()
    monkeypatch.setattr(m, 'request', lambda _: pytest.fail('Must not reach network'))
    destination = tmp_path / 'new'
    with pytest.raises(ValueError, match='release tag'):
        m.verify(destination, '../../main')
    assert not destination.exists()


@pytest.mark.parametrize('tag', ['v2.0.0', 'v2.0.1'])
def test_requested_tag_is_preserved_in_request_and_failure_receipt(tmp_path, monkeypatch, tag):
    m = verifier()
    calls = []

    def request(url):
        calls.append(url)
        if len(calls) == 1:
            return io.BytesIO(json.dumps({'private': False}).encode())
        raise OSError('Synthetic no-network failure')

    monkeypatch.setattr(m, 'request', request)
    destination = tmp_path / 'new'
    assert not m.verify(destination, tag)
    report = json.loads((destination / 'anonymous_download.json').read_text('utf-8'))
    assert calls[1].endswith('/releases/tags/' + tag)
    assert report['tag'] == tag and not report['all_passed']
    assert 'Synthetic no-network failure' in report['error']
