"""Regression gates for new evidence aggregation and document references."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_summary_does_not_equate_completed_with_legitimate_success():
    m=module('summarize_delivery_evidence')
    common={'kind':'normal','backend_type':'local_llama_cpp','usage':{'model_calls':2,'tool_calls':1},'confirmation_count':0}
    records=[dict(common,status='completed',elapsed_seconds=1,assessment={'legitimate_success':False}),
             dict(common,status='completed',elapsed_seconds=2,assessment={'legitimate_success':True}),
             dict(common,status='exhausted',elapsed_seconds=9,assessment={'legitimate_success':False})]
    r=m.summarize_records(records)
    assert r['normal_legal_complete']==1 and r['normal_runs']==3
    assert r['usage']['model_calls']==6 and r['status_counts']=={'completed':2,'exhausted':1}
    assert r['elapsed_seconds']['p95_nearest_rank']==9

def source_fixture(tmp_path):
    d=tmp_path/'docs';d.mkdir();(d/'figure.png').write_bytes(b'fixture')
    source=d/'guide.md';expected=[f'Feature {n}' for n in range(6)]
    source.write_text('# Guide\n\n'+ '\n\n'.join('## '+s for s in expected)+'\n\n![Figure](figure.png)\n','utf-8')
    return source,expected

def test_source_requires_six_ordered_main_chapters(tmp_path):
    m=module('verify_feature_documents');source,expected=source_fixture(tmp_path)
    assert len(m.inspect_source(source,tmp_path,expected)['chapters'])==6
    source.write_text(source.read_text().replace('## Feature 4','### Feature 4'),'utf-8')
    with pytest.raises(ValueError,match='six required'):m.inspect_source(source,tmp_path,expected)

def test_missing_figure_is_not_allowed(tmp_path):
    m=module('verify_feature_documents');source,expected=source_fixture(tmp_path)
    source.write_text(source.read_text().replace('figure.png','missing.png'),'utf-8')
    with pytest.raises(ValueError,match='Broken/outside'):m.inspect_source(source,tmp_path,expected)

def test_unfilled_actual_evidence_is_not_allowed(tmp_path):
    m=module('verify_feature_documents');source,expected=source_fixture(tmp_path)
    source.write_text(source.read_text()+'\n<!-- AUTO PERFORMANCE -->','utf-8')
    with pytest.raises(ValueError,match='Unfilled evidence'):m.inspect_source(source,tmp_path,expected)

def test_outside_project_file_is_not_followed(tmp_path):
    m=module('verify_feature_documents');source,expected=source_fixture(tmp_path)
    source.write_text(source.read_text()+'\n[x](../../outside.txt)','utf-8')
    with pytest.raises(ValueError,match='Broken/outside'):m.inspect_source(source,tmp_path,expected)

def test_markdown_parser_preserves_code_and_table_cells():
    m=module('build_feature_documents')
    parsed=list(m.blocks('## Title\n\n```powershell\n.\\启动项目.cmd\n```\n\n| A | B |\n|---|---|\n| first | second |'))
    assert parsed[1]==('code','.\\启动项目.cmd')
    assert parsed[2]==('table',[['A','B'],['first','second']])

def test_unclosed_code_fence_fails():
    with pytest.raises(ValueError,match='Unclosed'):list(module('build_feature_documents').blocks('```\nunfinished'))

def test_pdf_header_footer_does_not_hide_blank_page():
    m=module('verify_feature_documents')
    header='TaintLab  |  六项核心功能操作与验证  |  发布 v2.0.1 核心2.0.0\n第 4 页'
    assert not m.has_page_body(header)
    assert m.has_page_body(header+'\nF01 实际读取工具事件与网关检查结果')
