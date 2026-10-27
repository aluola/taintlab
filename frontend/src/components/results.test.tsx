import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { ResultsPanel } from './ResultsPanel';
import { api } from '../api';
import type { Campaign } from '../types';
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const campaign = (id: string, historical: boolean, patch: Partial<Campaign> = {}): Campaign => ({ id, label: id, version: historical ? '1.0.0' : '2.0.0', historical, planned_runs: 100, completed_runs: 0, complete: false, summary: {}, manifest: {}, ...patch });
describe('result versions and absent measurements', () => {
  it('selects current baseline first even when historical results arrive first', async () => {
    vi.spyOn(api, 'results').mockResolvedValue({ campaigns: [campaign('historical_main', true), campaign('v2_external', false), campaign('v2_baseline', false, { completed_runs: 13 })] });
    vi.spyOn(api, 'replays').mockResolvedValue({ records: [] }); render(<ResultsPanel onReplay={vi.fn()} />);
    await waitFor(() => expect((screen.getByLabelText('结果版本') as HTMLSelectElement).value).toBe('v2_baseline'));
    expect(screen.getByText('尚未完成')).toBeDefined(); expect(screen.queryAllByText('0.00%')).toHaveLength(0);
  });
  it('does not replace unavailable rates with measured zeros', async () => {
    vi.spyOn(api, 'results').mockResolvedValue({ campaigns: [campaign('v2_baseline', false, { completed_runs: 1, summary: { modes: { taint_policy: { runs: 1, normal_runs: 1, attack_runs: 0 } } } })] });
    vi.spyOn(api, 'replays').mockResolvedValue({ records: [] }); render(<ResultsPanel onReplay={vi.fn()} />);
    await screen.findAllByText('次数未提供'); expect(screen.queryAllByText('0.00%')).toHaveLength(0); expect(screen.getAllByText('无样本').length).toBeGreaterThan(0);
  });
});
