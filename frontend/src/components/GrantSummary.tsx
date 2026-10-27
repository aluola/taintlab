import type { Run } from '../types';
import { date, sensitivity, text, TOOLS } from '../format';
const list = (value: unknown) => Array.isArray(value) ? value.map(String) : [];
const targets = (value: unknown) => value && typeof value === 'object' && !Array.isArray(value) ? Object.entries(value).map(([target, level]) => `${target}（${sensitivity(String(level))}）`).join('；') || '无' : '未提供';
export function GrantSummary({ run }: { run: Run }) {
  const g = run.grant, paths = g.export_paths && typeof g.export_paths === 'object' ? Object.keys(g.export_paths) : [];
  const formats = [...new Set(paths.map(path => path.match(/\.[a-z0-9]+$/i)?.[0]).filter(Boolean))];
  return <section className="grant-summary"><div className="section-heading"><h3>本次可信授权</h3><span>程序签发 · 只读</span></div>
    {['none', 'input_filter'].includes(run.mode) && <p className="grant-baseline">此基线保留预设授权用于独立评测，但不执行应用权限与信息流策略。</p>}
    <dl><dt>可用工具</dt><dd>{list(g.tools).map(tool => TOOLS[tool] ?? tool).join('、') || '无'}</dd><dt>可读文档</dt><dd>{list(g.readable_docs).join('、') || '无'}</dd><dt>模拟收件人</dt><dd>{targets(g.recipients)}</dd><dt>虚拟导出位置</dt><dd>{targets(g.export_paths)}</dd><dt>导出格式</dt><dd>{formats.join('、') || '无'}<small>由当前授权路径确定</small></dd><dt>工具额度上限</dt><dd>{text(g.max_tool_calls)} 次</dd><dt>网关已用 / 剩余</dt><dd>{text(g.used_calls)} / {text(g.remaining_calls)}</dd><dt>最终回复上限</dt><dd>{sensitivity(String(g.reply_sensitivity ?? '未提供'))}</dd><dt>查询参数上限</dt><dd>{sensitivity(String(g.query_sensitivity ?? '未提供'))}</dd><dt>需确认的工具</dt><dd>{list(g.confirm_tools).map(tool => TOOLS[tool] ?? tool).join('、') || '无'}</dd><dt>策略版本</dt><dd>{text(g.policy_version)}</dd><dt>授权有效期</dt><dd>{typeof g.expires_at === 'number' || typeof g.expires_at === 'string' ? date(g.expires_at) : '未提供'}</dd><dt>运行绑定</dt><dd className="mono">{text(g.run_id ?? run.run_id)}</dd></dl>
    <details className="audit-detail"><summary>完整 TaskGrant JSON</summary><pre>{text(g)}</pre></details>
  </section>;
}
