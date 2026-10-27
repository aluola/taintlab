"""Check current DOCX/PDF structure and hashes; visual inspection remains separate."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile
from docx import Document
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'docs/v2/qa'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    validation=json.loads((QA/'document_validation.json').read_text('utf8'))
    source=ROOT/'docs/project_report.md';docx=ROOT/'dist/project_report.docx';pdf=ROOT/'dist/project_report.pdf'
    text=source.read_text('utf8');document=Document(docx);pages=PdfReader(pdf).pages
    contents=[p.extract_text() or '' for p in pages];normalized=[re.sub(r'\s+','',v) for v in contents]
    with zipfile.ZipFile(docx) as z:
        package_ok=z.testzip() is None
        page_fields=any('PAGE' in z.read(n).decode('utf8') for n in z.namelist() if re.fullmatch(r'word/footer\d+\.xml',n))
    headings=[line[3:] for line in text.splitlines() if line.startswith('## ')]
    colors=[str(r.font.color.rgb or p.style.font.color.rgb) for p in document.paragraphs if p.style.name in {'Title','Heading 1','Heading 2'} for r in p.runs if r.text.strip()]
    rendered=sorted(int(re.fullmatch(r'page-(\d+)\.png',p.name)[1]) for p in (QA/'render').glob('page-*.png'))
    media=json.loads((ROOT/'demo/video_validation.json').read_text('utf8'));play=json.loads((ROOT/'demo/playback_validation.json').read_text('utf8'))
    images=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text)
    checks={'current_version':validation.get('project_version')=='2.0.0','docx_zip_crc':package_ok,'docx_hash':sha(docx)==validation['docx_sha256'],'pdf_hash':sha(pdf)==validation['pdf_sha256'],'markdown_hash':sha(source)==validation['source_markdown_sha256'],'page_count':len(pages)==validation['pages'],'all_pages_text_and_chinese':all(v.strip() and re.search(r'[\u4e00-\u9fff]',v) for v in contents),'no_replacement_character':all('\ufffd' not in v for v in contents),'page_field':page_fields,'black_headings':bool(colors) and set(colors)=={'000000'},'toc_headings_and_pages':set(headings)==set(validation['toc_pages']) and all(re.sub(r'\s+','',h) in normalized[n-1] for h,n in validation['toc_pages'].items()),'rendered_pages_exact':rendered==list(range(1,len(pages)+1)),'all_markdown_images_embedded':len(images)==len(document.inline_shapes) and all((ROOT/p).is_file() for p in images),'current_video_and_playback':media.get('project_version')==play.get('project_version')=='2.0.0' and media.get('valid') and play.get('all_passed') and media['video_sha256']==play['video_sha256']==sha(ROOT/'demo/demo.mp4')}
    result={'project_version':'2.0.0','checked_at':datetime.now(timezone.utc).isoformat(),'pages':len(pages),'figures':len(images),'checks':checks,'all_passed':all(checks.values()),'scope':'Actual container/XML/PDF/text/font/page/hash checks. Separate per-page visual review is required; no claim of new model runs.'}
    content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    for path in (QA/'structure_validation.json',ROOT/'docs/qa/structure_validation.json'):path.write_text(content,'utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['all_passed']:raise SystemExit(1)
if __name__=='__main__':main()
