"""Apply human-readable annotation corrections after actual visual inspection."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'docs/assets/core-features'
x=json.loads((A/'figure_index.json').read_text('utf8'));items={f['id']:f for f in x['figures']};changes={}
for name in ['f01_read','f01_query']:
    f=items[name];c=f['crop'];marks=f['annotations'][:1]
    marks.append({'number':2,'label':'最终答复的关键事实','rect':[c['x']+72,c['y']+555,c['x']+928,c['y']+590],'style':'number_rectangle_arrow'})
    changes[name]={'annotations':marks}
for name in ['f05_direct_run','f05_indirect_run','f05_encoding_run','f05_segmented_run']:
    changes[name]={'annotations':items[name]['annotations'][:1],'annotation_review_note':'Final status is below the viewport behind the composer. Removed misleading offscreen mark; use saved safe record for final assessment. Visible first tool event retained.'}
changes['f03_flow_denied']={'annotations':[items['f03_flow_denied']['annotations'][0]],'annotation_review_note':'Visible flow-denial event; final success/failure is independently recorded. Offscreen terminal-status mark removed.'}
changes['f02_upload_registered']={'annotations':items['f02_upload_registered']['annotations'][:1],'annotation_review_note':'Newly uploaded document now scrolled into view with actual doc_id. Upload notice outside this crop is retained in full raw PNG; no arrow points to clipped notice.'}
for kind in ['direct','indirect','encoding','segmented']:
    name='f05_'+kind+'_preview'
    marks=[{**m,**({'number_placement':'before_target_in_column_gap'} if m['number']>1 else {})} for m in items[name]['annotations']]
    changes[name]={'annotations':marks,'annotation_review_note':'Right-column markers moved into the clear column gap so no horizontal annotation arrow crosses left-column parameter labels or values.'}
(A/'annotation_overrides.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n','utf8')
