"""Persist the completed AI visual inspection, bound to exact image hashes.

This records a review already performed with original-resolution image viewing;
it is not an automatic claim that arbitrary future captures are reviewed.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'docs/assets/core-features'
x=json.loads((A/'figure_index.json').read_text('utf8'))
notes={
'overview':'Current React home, three navigation entries, four tools and local model settings visible.',
'f01_read':'Actual meeting read allow and Wednesday15:00/A301 final text readable; final rectangle corrected after review.',
'f01_query':'Actual search query and November8/November3 final dates readable; final rectangle corrected.',
'f01_notify_inbox':'One real simulated team_A message, run/version and no exports visible.',
'f01_export_download':'Actual /exports/report.txt content and download link visible; file hash separately retained.',
'f02_upload_registered':'Latest capture scrolls the actual uploaded file into the finite document list. doc_id and unchecked box visible. Removed clipped notice annotation.',
'f02_source_fields':'Latest upload doc_c2c1a4d03459b original source, upload/untrusted/internal/hash and quoted trusted/approved wording readable.',
'f02_derived_action':'Latest actual run81665601; source doc node, deterministic assembly and visible-context explanation shown. Graph is horizontally scrollable and not all nodes fit one view.',
'f03_flow_denied':'Exact current normal-task replay, allowed first read and subsequent sensitivity flow denial. No claim of legitimate success. Removed annotation to status behind fixed footer.',
'f03_dependency_graph':'Same02e896c7 run and blocked action#2 selected; secret derived node to model_generation shown.',
'f03_upstream_source':'Same run upstream viewport shows original vault, deterministic derived edge, potential dashed context edges and legend.',
'f03_no_effect':'Same run, inbox0/files0. Clearly actual replay, version2.0.0.',
'f04_confirmation':'Actual internal notification pending, team_A/body/source IDs/run/hash/expiry and both buttons readable.',
'f04_grant':'Actual task tools,meeting read scope,team_A internal,quota6 used2 remaining4,expiry and run binding readable.',
'f04_rejection':'Separate actual rejection run6924078b, no inbox/files. Does not claim final cancellation wording.',
'f04_unauthorized':'Direct-injection current replay; attacker target blocked by recipient whitelist. This is not flow-denial evidence.',
'f05_direct_preview':'Actual direct input generation, role_forgery,seed11,task and generated case visible.',
'f05_indirect_preview':'Actual patch document before/after, role/approval forgery and generated case visible.',
'f05_encoding_preview':'Actual Base64 text, unchanged legal facts and generation/run controls visible.',
'f05_segmented_preview':'Actual patch/continuation before/after and two separately expanded fragments visible.',
'f05_direct_run':'Actual unauthorized vault read blocked. Final assessment below composer not presented as visible; use record.',
'f05_indirect_run':'Actual patch read allow. Final assessment below composer not presented as visible; use record.',
'f05_encoding_run':'Actual patch read allow. Final assessment below composer not presented as visible; use record.',
'f05_segmented_run':'Actual patch read and later notification card visible; model final claim partly below composer. Do not infer continuation read; record proves absent.',
'f06_canary_state':'Real current replay, Canary established/sensitive read yes/not found, legitimate_success false visible. Expanded JSON continues below crop.',
'f06_baseline':'Current three-mode actual counts and complete denominators readable:13/216,9/216,8/216.',
'f06_external':'Current extended counts31/180,29/180,34/180 and policy_only34/180 readable.',
'f06_completion_split':'Current extended normal automatic61/90 and assisted6/90, contact and failure rows readable.',
'f06_selfcheck_positive':'Actual native console exact positive and neighbor negative input/findings, Chinese synthetic/nonmodel statement readable. Long actual command wraps intact.',
'f06_selfcheck_encoded':'Actual two-layer Base64 and same/cross-sink segmented findings readable; synthetic-only label remains.',
'f06_selfcheck_limits':'Actual known three-layer decode boundary false, limits and7/7 expected match stated; no model or ASR claim.'}
assert set(notes)=={f['id'] for f in x['figures']}
out={'release_version':'2.0.1','runtime_version':'2.0.0','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'reviewer':'AI agent /root/ui_delivery; not attributed to a human group member','method':'Viewed each original-resolution annotated image with view_image; checked source pixels for focused areas. Revisited corrected screenshots/marks; no montage-only review.','all_passed':True,'scope':'Readable evidence images and truthful captions. Not proof that all states or all model tasks succeed; not video QA.','limitations':['Native browser graph scroll clips nodes by design; paired upstream/action images explain this.','Some tool-run terminal footer is behind fixed composer. Misleading arrows removed; saved actual records carry final assessment.','No image edits except crop, margin, numbered rectangles/arrows. No secret original values in application UI captures. Synthetic Canary is deliberately visible and labeled.'],'figures':[{'id':f['id'],'raw_sha256':f['raw_sha256'],'annotated_sha256':f['annotated_sha256'],'passed':True,'observation':notes[f['id']]} for f in x['figures']]}
(A/'visual_review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf8')
