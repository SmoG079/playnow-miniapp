import type {Tournament} from '../services/tournaments';
/** A server explanation takes precedence; the count fallback supports older APIs. */
export function drawBlockReason(t: Tournament | null): string {
  if (!t?.config || t.draw_stage === 'knockout') return '';
  if (t.draw_block_reason != null) return t.draw_block_reason;
  const eligible=t.registrations.filter(r=>r.status==='confirmed'&&r.admission==='active'&&r.approval==='approved'&&['none','paid','verified'].includes(r.payment||''));
  const perTeam=t.config.discipline==='singles'?1:2;
  const required=2*perTeam*t.config.group_count;
  if(eligible.length<required)return `至少需要 ${required} 名符合抽签条件的选手，当前 ${eligible.length} 名，请补充参赛者`;
  return '';
}
