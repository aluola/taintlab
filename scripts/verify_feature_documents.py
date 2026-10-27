"""Verify source links and rendered artifacts; never manufacture visual review."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SPECS={
 'core':('CORE_FEATURES_GUIDE','core_features_qa',[
     'Agent 攻防靶场','不可信内容标记','污点追踪','权限策略控制','自动化攻击测试','泄露检测与综合评测']),
 'development':('DEVELOPMENT_AND_DELIVERY','development_delivery_qa',[
     '需求分析与技术选型','环境搭建与结构化设计','迭代开发与代码规范','集成测试与优化','打包部署与文档编写','持续维护与迭代']),
}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def has_page_body(text):
    """A header/footer alone must not make an accidental blank page pass."""
    lines=[line.strip() for line in (text or '').splitlines()]
    body=[line for line in lines if line and not line.startswith('TaintLab  |') and not re.fullmatch(r'第\s*\d+\s*页',line)]
    return len(''.join(body))>=10

def inspect_source(source,root,expected):
    text=source.read_text('utf-8-sig')
    if '<!-- AUTO ' in text:raise ValueError('Unfilled evidence placeholder')
    chapters=re.findall(r'^## (.+)$',text,re.M)
    if len(chapters)!=6 or any(title not in chapters[i] for i,title in enumerate(expected)):
        raise ValueError('The six required main chapters are incomplete or out of order')
    assets={};links=[]
    for image,label,target in re.findall(r'(!?)\[([^\]]+)\]\(([^)]+)\)',text):
        if re.match(r'https?://',target):continue
        target=target.split('#')[0]
        if not target:continue
        p=(source.parent/target).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():raise ValueError('Broken/outside relative link: '+target)
        links.append(p.relative_to(root).as_posix())
        if image:assets[p.relative_to(root).as_posix()]=sha(p)
    return {'chapters':chapters,'relative_links':sorted(set(links)),'assets':assets}

def verify(kind,root=ROOT,source_only=False):
    stem,qa_name,expected=SPECS[kind];source=root/'docs'/f'{stem}.md';qa=root/'docs'/qa_name
    result=inspect_source(source,root,expected)
    if source_only:return result
    docx=source.with_suffix('.docx');pdf=source.with_suffix('.pdf')
    with zipfile.ZipFile(docx) as z:
        if z.testzip() is not None:raise ValueError('DOCX CRC failure')
        tree=ET.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        doc_text=''.join(tree.itertext())
        if any(x not in doc_text for x in expected):raise ValueError('DOCX lost chapter text')
        if tree.findall('.//w:pBdr',ns):raise ValueError('Decorative paragraph borders reintroduced')
    from pypdf import PdfReader
    reader=PdfReader(pdf);pages=len(reader.pages)
    if pages<6:raise ValueError('Unexpectedly short six-chapter PDF')
    if any(not has_page_body(p.extract_text()) for p in reader.pages):raise ValueError('Empty/unreadable PDF page (header/footer alone is not content)')
    review_path=qa/'visual_review.json';review=json.loads(review_path.read_text('utf-8'))
    if not review.get('all_passed') or len(review.get('reviewed_pages',[]))!=pages:raise ValueError('Complete actual visual review required')
    page_entries=review['reviewed_pages']
    if {x['page'] for x in page_entries}!=set(range(1,pages+1)):raise ValueError('Visual review has missing/repeated pages')
    for item in page_entries:
        image=qa/'render'/f"page-{item['page']}.png"
        if item['sha256']!=sha(image) or not item['passed']:raise ValueError('Stale visual page review')
    if review.get('docx_sha256')!=sha(docx) or review.get('pdf_sha256')!=sha(pdf):raise ValueError('Stale document review')
    result.update({'release_version':'2.0.1','runtime_version':'2.0.0','created_at_utc':datetime.now(timezone.utc).isoformat(),
                   'all_passed':True,'visual_review':'passed','pages':pages,'review_sha256':sha(review_path),
                   'artifact_sha256':{p.relative_to(root).as_posix():sha(p) for p in (source,docx,pdf)},
                   'scope':'Source links, actual DOCX/XML and PDF parsing plus separate page-image visual review bound by SHA. No formal experiment run.'})
    qa.mkdir(parents=True,exist_ok=True);(qa/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--document',choices=['core','development','all'],default='all');p.add_argument('--source-only',action='store_true');a=p.parse_args()
    for kind in (SPECS if a.document=='all' else [a.document]):
        r=verify(kind,source_only=a.source_only);print(json.dumps({'document':kind,'chapters':len(r['chapters']),'assets':len(r['assets']),'pages':r.get('pages'),'source_only':a.source_only},ensure_ascii=False))

if __name__=='__main__':main()
