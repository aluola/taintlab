"""Anonymous GitHub publication download verification; no GitHub auth is read.

Run after a release exists. Creates a NEW directory, downloads source/archive
and release assets, verifies SHA256SUMS and safely extracts the source ZIP.
It does not install packages, start processes or mutate any remote resource.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

REPO = 'aluola/taintlab'
TAG = 'v2.0.0'

def request(url):
    # No CookieJar, Authorization, netrc, gh or credential helper.
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'TaintLab-anonymous-release-verifier/1.0', 'Accept': '*/*'}), timeout=120)

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with request(url) as response, path.open('wb') as stream:
        status = response.status
        while block := response.read(1024 * 1024): stream.write(block)
    if status != 200: raise ValueError(f'Unexpected download status {status}')
    return {'url': url, 'http_status': status, 'filename': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)}

def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 15000 or sum(e.file_size for e in entries) > 512 * 1024 * 1024: raise ValueError('Source archive exceeds budget')
        for item in entries:
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or '\\' in item.filename or item.filename.startswith('/'):
                raise ValueError('Unsafe source archive path')
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(item))
    roots = [p for p in destination.iterdir() if p.is_dir()]
    if len(roots) != 1: raise ValueError('Unexpected source root')
    return roots[0]

def verify(destination):
    destination.mkdir(parents=True, exist_ok=False)
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'repository': REPO, 'tag': TAG,
              'authentication': 'Anonymous HTTP, no cookies or authorization headers; no gh token read', 'all_passed': False,
              'installation_or_model_execution': 'not performed by this downloader; separate Windows acceptance required'}
    try:
        with request(f'https://api.github.com/repos/{REPO}') as response: repository = json.load(response)
        if repository['private']: raise ValueError('Repository is private')
        with request(f'https://api.github.com/repos/{REPO}/releases/tags/{TAG}') as response: release = json.load(response)
        if release['draft'] or release['tag_name'] != TAG: raise ValueError('Expected published release')
        report['public_repository'] = True
        report['release'] = {'url': release['html_url'], 'id': release['id'], 'draft': release['draft'], 'published_at': release['published_at']}
        assets = release['assets']
        for asset in assets:
            if Path(asset['name']).name != asset['name'] or '\\' in asset['name']: raise ValueError('Unsafe asset name')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            report['assets'] = list(pool.map(lambda a: download(a['browser_download_url'], destination / 'assets' / a['name']), assets))
        for asset, result in zip(assets, report['assets']):
            if asset['size'] != result['bytes']: raise ValueError('Release asset length mismatch')
            if asset.get('digest') and asset['digest'] != 'sha256:' + result['sha256']: raise ValueError('GitHub asset digest mismatch')
        sums = destination / 'assets/SHA256SUMS'
        if not sums.exists(): raise ValueError('Release has no SHA256SUMS')
        checked = []
        for line in sums.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})\s+\*?([^/\\]+)', line)
            if not match: raise ValueError('Invalid checksum line')
            path = destination / 'assets' / match[2]
            if not path.is_file() or sha(path) != match[1]: raise ValueError('Checksum mismatch for ' + match[2])
            checked.append(match[2])
        report['checksum_verified_assets'] = checked
        source = destination / 'source.zip'
        report['source_archive'] = download(f'https://github.com/{REPO}/archive/refs/tags/{TAG}.zip', source)
        root = extract(source, destination / 'source')
        manifest = json.loads((root / 'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
        for name, item in manifest['files'].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or sha(path) != item['sha256']:
                raise ValueError('Source snapshot differs: ' + name)
        report['source_manifest_verified'] = len(manifest['files'])
        report['source_root'] = str(root)
        record_counts = {name: len(list((root / f'results/{name}/records').glob('*.json'))) for name in ('main','ablation','v2/baseline','v2/external')}
        if record_counts != {'main':972,'ablation':324,'v2/baseline':1296,'v2/external':1080}: raise ValueError('Formal records missing')
        report['formal_record_counts'] = record_counts
        must = ['README.md','启动项目.cmd','关闭项目.cmd','frontend/dist/index.html','docs/USER_MANUAL.md','docs/USER_MANUAL.pdf','docs/USER_MANUAL.docx','docs/assets/user-manual/raw/01_home.png','demo/demo.mp4','dist/project_report.pdf','dist/project_report.docx']
        checks=[]
        for name in must:
            url = f'https://raw.githubusercontent.com/{REPO}/{TAG}/' + urllib.parse.quote(name, safe='/')
            with request(url) as response:
                raw = response.read(); status = response.status
            equal = hashlib.sha256(raw).hexdigest() == sha(root / name)
            if status != 200 or not equal: raise ValueError('Raw file mismatch: ' + name)
            checks.append({'path':name,'status':status,'bytes':len(raw),'sha256_equal_to_source':equal})
        report['raw_public_files'] = checks
        report['all_passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    (destination / 'anonymous_download.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('all_passed','source_root','source_manifest_verified','formal_record_counts','error')},ensure_ascii=False,indent=2))
    return report['all_passed']

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--destination',type=Path,required=True);args=parser.parse_args()
    raise SystemExit(0 if verify(args.destination.resolve()) else 1)
