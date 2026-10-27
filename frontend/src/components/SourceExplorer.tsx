import { useEffect, useRef, useState } from 'react';
import type { AgentEvent, SourceNode } from '../types';
import { sensitivity, TOOLS } from '../format';
import { sourceFocus } from '../provenanceView';
import { Icon } from './Icon';

function DependencyGraph({ nodes, selected }: { nodes: SourceNode[]; selected: string }) {
  const positions = new Map<string, { x: number; y: number }>(), depth = new Map<string, number>();
  const ids = new Set(nodes.map(node => node.node_id));
  for (let pass = 0; pass < Math.min(nodes.length, 25); pass++) for (const node of nodes) {
    if (depth.has(node.node_id)) continue;
    const parents = node.parent_ids.filter(id => ids.has(id));
    if (parents.every(id => depth.has(id))) depth.set(node.node_id, parents.length ? Math.max(...parents.map(id => depth.get(id)!)) + 1 : 0);
  }
  const rows: Record<number, number> = {};
  for (const node of nodes) { const column = depth.get(node.node_id) ?? 0; positions.set(node.node_id, { x: 16 + column * 205, y: 18 + (rows[column] ?? 0) * 94 }); rows[column] = (rows[column] ?? 0) + 1; }
  const width = Math.max(400, 200 + Math.max(0, ...depth.values()) * 205), height = Math.max(120, Math.max(0, ...Object.values(rows)) * 94 + 20);
  const scroll = useRef<HTMLDivElement>(null), selectedX = positions.get(selected)?.x ?? 0;
  const locate = () => { if (scroll.current) scroll.current.scrollLeft = Math.max(0, selectedX - scroll.current.clientWidth / 2 + 87); };
  useEffect(() => { if (scroll.current) scroll.current.scrollLeft = Math.max(0, selectedX - scroll.current.clientWidth / 2 + 87); }, [selected, selectedX, width]);
  return <><div className="graph-navigation"><button type="button" className="text-button" onClick={() => { if (scroll.current) scroll.current.scrollLeft = 0; }}>查看上游来源</button><button type="button" className="text-button" onClick={locate}>定位所选动作</button></div><div className="graph-scroll" ref={scroll}><svg width={width} height={height} role="img" aria-label="程序记录的来源依赖图"><defs><marker id="dependency-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8fa89a" /></marker></defs>{nodes.flatMap(node => node.parent_ids.map(parent => { const from = positions.get(parent), to = positions.get(node.node_id); if (!from || !to) return null; return <path key={`${parent}-${node.node_id}`} d={`M${from.x + 174},${from.y + 32} C${from.x + 194},${from.y + 32} ${to.x - 20},${to.y + 32} ${to.x},${to.y + 32}`} fill="none" stroke="#a4b6b4" strokeWidth="1.4" strokeDasharray={node.dependency_kind === 'deterministic_data' ? undefined : '4 4'} markerEnd="url(#dependency-arrow)" />; }))}{nodes.map(node => { const at = positions.get(node.node_id)!; return <g key={node.node_id} transform={`translate(${at.x},${at.y})`}><rect width="174" height="66" rx="9" fill={node.node_id === selected ? '#e6f2ec' : node.sensitivity === 'secret' ? '#fff6e7' : '#f6faf9'} stroke={node.node_id === selected ? '#419071' : node.sensitivity === 'secret' ? '#dfbb78' : '#c8ded9'} strokeWidth={node.node_id === selected ? 2 : 1} /><text x="11" y="22" fontSize="11.5" fill="#273a37">{(node.display_name ?? node.source_id).slice(0, 19)}</text><text x="11" y="41" fontSize="10" fill="#73817d">{sensitivity(node.sensitivity)} · {node.source_type}</text><text x="11" y="56" fontSize="8.5" fill="#96a79d">{node.node_id.slice(-12)}</text><title>{node.node_id} · {node.dependency_kind ?? '未分类依赖'}</title></g>; })}</svg></div></>;
}
export function SourceExplorer({ nodes, events, initialNodeId }: { nodes: SourceNode[]; events: AgentEvent[]; initialNodeId?: string }) {
  const [chosen, setChosen] = useState(initialNodeId ?? '');
  const [showAll, setShowAll] = useState(false);
  const eventNodes = events.filter(event => event.node_id && nodes.some(node => node.node_id === event.node_id));
  const selected = nodes.some(node => node.node_id === chosen) ? chosen : eventNodes.at(-1)?.node_id ?? nodes.at(-1)?.node_id ?? '';
  const event = [...eventNodes].reverse().find(item => item.node_id === selected), node = nodes.find(item => item.node_id === selected);
  const view = sourceFocus(nodes, selected), shown = showAll ? nodes : view.focused;
  const sourceNames = view.related.filter(item => item.dependency_kind === 'source').map(item => item.display_name ?? item.source_id);
  return <><div className="source-controls"><label>聚焦动作<select aria-label="聚焦来源动作" value={selected} onChange={e => { setChosen(e.target.value); setShowAll(false); }}>{eventNodes.map((item, index) => <option value={item.node_id} key={`${item.node_id}-${index}`}>#{item.step} {TOOLS[item.tool ?? ''] ?? item.tool} · {item.decision}</option>)}{!eventNodes.length && <option value={selected}>最近登记的来源</option>}</select></label><button type="button" className="button ghost small" onClick={() => setShowAll(!showAll)}>{showAll ? '回到聚焦视图' : `展开全部 ${nodes.length} 个节点`}</button></div>
    {node && <p className="source-explanation">{event ? `动作 #${event.step}「${TOOLS[event.tool ?? ''] ?? event.tool}」` : '所选节点'}继承了{sourceNames.length ? ` ${sourceNames.slice(0, 5).join('、')}${sourceNames.length > 5 ? ' 等' : ''}` : '已登记父节点'}的标签；当前为{sensitivity(node.sensitivity)}。{node.dependency_kind === 'potential_context' ? '这里记录模型可见上下文的潜在影响，不能证明某段正文实际导致了该动作。' : '确定性派生保留输入标签；图中虚线仍只表示潜在或未分类依赖。'}</p>}
    <div className="section-heading"><h3>来源依赖图</h3><span>{showAll ? `全部 ${nodes.length}` : `显示 ${shown.length} / 相关 ${view.related.length}`} 个节点</span></div>
    {shown.length ? <DependencyGraph nodes={shown} selected={selected} /> : <p className="muted">尚无来源节点。</p>}
    <p className="graph-note">实线：确定性数据派生；虚线：潜在或未分类依赖。默认最多显示 14 个相关节点，折叠仅影响视图，不删除来源与标签。横向滚动查看后续节点。</p>
    {shown.map(source => <details key={source.node_id} className="source-card"><summary><Icon name="file" size={15} /><span>{source.display_name ?? source.source_id}</span><span className={`tag sensitivity-${source.sensitivity}`}>{sensitivity(source.sensitivity)}</span></summary><dl><dt>指令可信度</dt><dd>{source.integrity === 'trusted_control' ? '可信控制' : '不可信内容'}</dd><dt>来源类型</dt><dd>{source.source_type}</dd><dt>节点</dt><dd>{source.node_id}</dd><dt>标签依据</dt><dd>{source.label_basis || '由程序维护'}</dd><dt>变换</dt><dd>{source.transformation}</dd><dt>父节点</dt><dd>{source.parent_ids.join('、') || '无'}</dd><dt>内容哈希</dt><dd>{source.content_hash || '未提供'}</dd></dl>{source.preview && <pre>{source.preview}</pre>}</details>)}
  </>;
}
