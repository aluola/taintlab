import { describe, it, expect } from 'vitest';
import { mergeRun, percent, STATUS } from './format';
import { fixtureRun, fixtureSession } from './testFixtures';
describe('out of order events and session isolation', () => {
  it('ignores another session, duplicate sequences and stale SSE events', () => {
    const session = fixtureSession({ last_sequence: 8 });
    expect(mergeRun(session, fixtureRun({ session_id: 'other-session' }), 9)).toBe(session);
    expect(mergeRun(session, fixtureRun(), 8)).toBe(session);
    expect(mergeRun(session, fixtureRun(), 5)).toBe(session);
  });
  it('does not let a late HTTP start receipt overwrite an already completed run', () => {
    const completed = fixtureRun({ events: [{ step: 1, decision: 'allow', tool: 'final' }] });
    const session = fixtureSession({ runs: [completed], last_sequence: 7 });
    expect(mergeRun(session, fixtureRun({ status: 'running', final: null }))).toBe(session);
    expect(mergeRun(session, fixtureRun({ status: 'completed', events: [] }))).toBe(session);
  });
  it('accepts confirmed pending progress and keeps one run entry', () => {
    const session = fixtureSession({ runs: [fixtureRun({ status: 'pending' })], last_sequence: 5 });
    const updated = mergeRun(session, fixtureRun({ status: 'running' }), 6);
    expect(updated.runs).toHaveLength(1); expect(updated.runs[0].status).toBe('running'); expect(updated.last_sequence).toBe(6);
  });
  it('never formats absent metrics as a measured zero or completed as task success', () => {
    expect(percent(undefined)).toBe('—'); expect(percent(NaN)).toBe('—'); expect(percent(0)).toBe('0.00%');
    expect(STATUS.completed).toBe('运行结束');
  });
});
