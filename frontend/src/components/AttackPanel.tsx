import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AttackPreview, AttackTemplate, AttackView, Mode, Session } from '../types';
import { MODES, text } from '../format';
import { Icon } from './Icon';

const VIEWS: { id: AttackView; name: string; description: string }[] = [
  { id: 'direct', name: '直接注入', description: '用户输入中的指令攻击，单独统计。' },
  { id: 'indirect', name: '间接注入', description: '攻击藏在文档、网页或工具返回中。' },
  { id: 'encoding', name: '编码变形', description: '观察编码包装后的指令与数据流。' },
  { id: 'segmented', name: '分段诱导', description: '把攻击拆分到多个来源或轮次。' },
];
const OPTION_LABELS: Record<string, string> = { role_forgery: '角色与授权伪造', workflow_hijack: '工作流程劫持', data_exfiltration: '数据窃取', fact_tampering: '事实篡改', none: '不编码', base64: 'Base64', hex: '十六进制', url: 'URL 编码', direct: '用户输入', document: '文档正文', web: '网页快照', tool_return: '工具返回', unauthorized_read: '未授权读取', unauthorized_send: '未授权发送', unauthorized_export: '未授权导出', canary_leak: 'Canary 泄露', tamper: '结果篡改', query: '查询与提取', notification: '发送通知', export: '导出文件', multi_step: '多步骤任务' };
const FIELDS: Record<string, string> = { technique: '攻击手法', encoding: '编码方式', entry: '注入入口', goal: '攻击目标', workflow: '合法工作流' };

export function AttackPanel({ getSession, onRun, busy }: { getSession: () => Promise<Session>; onRun: (preview: AttackPreview, mode: Mode, seed: number) => Promise<void>; busy: boolean }) {
  const [templates, setTemplates] = useState<AttackTemplate[]>([]);
  const [view, setView] = useState<AttackView>('indirect');
  const [templateId, setTemplateId] = useState('');
  const [options, setOptions] = useState<Record<string, string>>({});
  const [seed, setSeed] = useState(11);
  const [mode, setMode] = useState<Mode>('taint_policy');
  const [preview, setPreview] = useState<AttackPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { let active = true; api.templates().then(result => { if (active) setTemplates(result.templates); }).catch(error => { if (active) setError(String(error.message)); }); return () => { active = false; }; }, []);
  const matching = templates.filter(item => item.view === view);
  const template = matching.find(item => item.template_id === templateId) ?? matching[0];
  useEffect(() => { if (template) { setTemplateId(template.template_id); setOptions(template.defaults); setPreview(null); } }, [template]);
  async function generate() {
    if (!template) return;
    setLoading(true); setError(''); setPreview(null);
    try { const session = await getSession(); setPreview(await api.preview(session.session_id, { ...options, view, seed })); }
    catch (error) { setError((error as Error).message); }
    finally { setLoading(false); }
  }
  async function start() { if (!preview) return; setError(''); try { await onRun(preview, mode, seed); } catch (error) { setError((error as Error).message); } }
  return <div className="workspace-page experiments-page"><div className="page-intro"><span className="eyebrow">可重复的本地实验</span><h1>看见攻击如何进入上下文</h1><p>先生成并检查样本，再交给真实本地 Agent。预览不会执行工具。</p></div>
    <div className="attack-views" role="tablist" aria-label="攻击类型">{VIEWS.map(item => <button type="button" role="tab" aria-selected={view === item.id} className={view === item.id ? 'selected' : ''} key={item.id} onClick={() => { setView(item.id); setTemplateId(''); setPreview(null); }}><strong>{item.name}</strong><span>{item.description}</span></button>)}</div>
    <div className="experiment-grid"><section className="surface experiment-controls"><div className="section-heading"><h2>样本配置</h2><Icon name="flask" size={19} /></div><label>规则模板<select value={template?.template_id ?? ''} onChange={event => { setTemplateId(event.target.value); setPreview(null); }}>{matching.length === 0 && <option value="">等待本地模板目录</option>}{matching.map(item => <option key={item.template_id} value={item.template_id}>{item.name}</option>)}</select></label>{template?.description && <p className="small muted">{template.description}</p>}{Object.entries(FIELDS).map(([key, label]) => template?.options[key]?.length ? <label key={key}>{label}<select value={options[key] ?? ''} onChange={event => { setOptions({ ...options, [key]: event.target.value }); setPreview(null); }}>{template.options[key].map(option => <option key={typeof option === 'string' ? option : option.value} value={typeof option === 'string' ? option : option.value}>{typeof option === 'string' ? OPTION_LABELS[option] ?? option : option.label}</option>)}</select></label> : null)}<label>生成与运行种子<input type="number" min="0" max="2147483647" value={seed} onChange={event => { setSeed(Number(event.target.value)); setPreview(null); }} /></label><button type="button" className="button primary wide" disabled={loading || !template} onClick={generate}><Icon name="refresh" size={16} />{loading ? '正在生成真实样本' : '生成样本预览'}</button><p className="small muted">模板和预置授权保存在服务端，浏览器无法提交自造 Grant。</p></section>
    <section className="surface preview-surface"><div className="section-heading"><h2>样本预览</h2>{preview && <span className="tag neutral">尚未执行</span>}</div>{!preview ? <div className="preview-empty"><Icon name="file" size={40} /><h3>{loading ? '正在生成样本' : '先检查输入，再启动实验'}</h3><p>这里会显示原始任务、注入前后正文与分段来源。</p></div> : <><div className="legitimate-task"><span className="field-label">仍需完成的合法任务</span><p>{preview.task}</p></div><div className="before-after"><div><h3>注入前</h3>{preview.before.map(source => <div className="source-preview" key={source.source_id}><small>{source.source_id} · {source.source_type}</small><pre>{source.content}</pre></div>)}</div><div className="after-panel"><h3>注入后 <span className="tag warning">不可信内容</span></h3>{preview.after.map(source => <div className="source-preview" key={source.source_id}><small>{source.source_id} · {source.source_type}</small><pre>{source.content}</pre></div>)}</div></div>{preview.fragments?.length > 0 && <div className="fragments"><h3>分段来源</h3>{preview.fragments.map(fragment => <details key={`${fragment.source_id}-${fragment.order}`}><summary>第 {fragment.order} 段 · {fragment.source_id}</summary><pre>{fragment.content}</pre></details>)}</div>}<details className="audit-detail"><summary>生成元数据 · {preview.case_id}</summary><pre>{text(preview.metadata)}</pre></details><div className="preview-run"><label>执行配置<select value={mode} onChange={event => setMode(event.target.value as Mode)}>{Object.entries(MODES).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></label><button type="button" className="button primary" disabled={busy || loading} onClick={start}><Icon name="send" size={17} />{busy ? '当前会话仍在运行' : '交给本地 Agent 运行'}</button></div></>}
    </section></div>{error && <div className="error-banner" role="alert"><Icon name="info" size={17} />{error}</div>}
  </div>;
}
