import type { SourceNode } from './types';
export function sourceFocus(nodes: SourceNode[], selected: string, limit = 14) {
  const byId = new Map(nodes.map(node => [node.node_id, node]));
  const queue = byId.has(selected) ? [selected] : nodes.length ? [nodes[nodes.length - 1].node_id] : [];
  const visited = new Set<string>();
  for (let index = 0; index < queue.length; index++) {
    const id = queue[index]; if (visited.has(id) || !byId.has(id)) continue;
    visited.add(id); queue.push(...byId.get(id)!.parent_ids);
  }
  const shown = new Set([...visited].slice(0, limit));
  return { focused: nodes.filter(node => shown.has(node.node_id)), related: nodes.filter(node => visited.has(node.node_id)), all: nodes };
}
