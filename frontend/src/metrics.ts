// summarize() stores unrounded Boolean rates and their denominators. Recover
// counts only when they are an exact integer within floating-point tolerance.
export function measuredCount(rate?: number, denominator?: number): number | null {
  if (typeof rate !== 'number' || !Number.isFinite(rate) || rate < 0 || rate > 1 || typeof denominator !== 'number' || !Number.isInteger(denominator) || denominator <= 0) return null;
  const count = rate * denominator, integer = Math.round(count);
  return Math.abs(integer - count) < 1e-7 ? integer : null;
}
export function countLabel(rate?: number, denominator?: number) {
  const count = measuredCount(rate, denominator);
  return count === null ? denominator === 0 ? '无样本' : '次数未提供' : `${count.toLocaleString()} / ${denominator!.toLocaleString()}`;
}
export const numberLabel = (value?: number, digits = 0) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
