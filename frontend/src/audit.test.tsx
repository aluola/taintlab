import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { countLabel, measuredCount, numberLabel } from './metrics';
import { sourceFocus } from './provenanceView';
import { GrantSummary } from './components/GrantSummary';
import { SourceExplorer } from './components/SourceExplorer';
import { fixtureRun } from './testFixtures';
import type { SourceNode } from './types';
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function chain(): SourceNode[] { return Array.from({ length: 20 }, (_, i) => ({ node_id: `n${i}`, source_id: `source${i}`, source_type: 'model_output', parent_ids: i ? [`n${i-1}`] : [], integrity: 'untrusted_content', sensitivity: 'internal', transformation: 'model_generation', dependency_kind: i ? 'potential_context' : 'source' })); }
describe('metrics use the actual declared denominator', () => {
  it('recovers exact counts from unrounded summary rates', () => { expect(measuredCount(12 / 216, 216)).toBe(12); expect(countLabel(72 / 108, 108)).toBe('72 / 108'); expect(countLabel(0, 216)).toBe('0 / 216'); });
  it('never invents counts from missing, rounded or invalid statistics', () => { expect(measuredCount(.0556, 216)).toBeNull(); expect(measuredCount(undefined, 216)).toBeNull(); expect(measuredCount(0, 0)).toBeNull(); expect(measuredCount(1.1, 216)).toBeNull(); expect(countLabel(undefined, 0)).toBe('无样本'); expect(numberLabel(undefined)).toBe('—'); });
});
describe('source focus is only a visual projection', () => {
  it('preserves ancestors and can expose the full graph without losing nodes', () => { const nodes = chain(), copy = JSON.stringify(nodes), focus = sourceFocus(nodes, 'n19'); expect(focus.focused).toHaveLength(14); expect(focus.focused.at(-1)?.node_id).toBe('n19'); expect(focus.related).toHaveLength(20); expect(focus.all).toHaveLength(20); expect(JSON.stringify(nodes)).toBe(copy); });
  it('does not include unrelated branches in a selected action view', () => { const nodes = chain(); nodes.push({ ...nodes[0], node_id: 'unrelated', source_id: 'unrelated' }); const focus = sourceFocus(nodes, 'n4'); expect(focus.related.map(node => node.node_id)).toEqual(['n0','n1','n2','n3','n4']); });
  it('lets the user expand all actual source nodes and labels potential influence', () => { render(<SourceExplorer nodes={chain()} events={[{ step: 3, decision: 'allow', tool: 'final', node_id: 'n19' }]} />); expect(document.querySelectorAll('.source-card')).toHaveLength(14); expect(screen.getByText(/不能证明某段正文实际导致/)).toBeDefined(); fireEvent.click(screen.getByRole('button', { name: '展开全部 20 个节点' })); expect(document.querySelectorAll('.source-card')).toHaveLength(20); });
});
describe('readable grant remains sourced from the real run', () => {
  it('shows actual scope, quota, sensitivity and binding without raw JSON as the only view', () => { render(<GrantSummary run={fixtureRun({ grant: { run_id: 'bound-run', tools: ['read_document','export_file'], readable_docs: ['selected-doc'], recipients: {}, export_paths: { '/exports/report.md': 'internal' }, max_tool_calls: 6, used_calls: 2, remaining_calls: 4, reply_sensitivity: 'internal', query_sensitivity: 'public', confirm_tools: ['export_file'], policy_version: 'gateway-2.0', expires_at: Date.now() / 1000 + 300 } })} />); expect(screen.getByText('selected-doc')).toBeDefined(); expect(screen.getByText('2 / 4')).toBeDefined(); expect(screen.getByText('.md')).toBeDefined(); expect(screen.getByText('bound-run')).toBeDefined(); expect(screen.getByText('gateway-2.0')).toBeDefined(); expect(document.querySelector('details')?.open).toBe(false); });
});
