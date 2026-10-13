import { utcInput } from '../services/tournaments';
import type { ActivityCardData, ActivityKind } from './activity-card';
export function registrationCutoff(item:ActivityCardData,kind:ActivityKind):number {
  const value=kind==='tournament'
    ? (item.registration_deadline || item.start_time)
    : item.preferred_date && item.preferred_start ? `${item.preferred_date}T${item.preferred_start.slice(0,5)}:00+08:00` : undefined;
  return value ? Date.parse(kind==='tournament'?utcInput(value):value) : NaN;
}
export function registrationClosed(item:ActivityCardData,kind:ActivityKind,now=Date.now()):boolean {
  if(item.registration_closed || ['closed','cancelled','finished','ongoing'].includes(item.status||''))return true;
  const cutoff=registrationCutoff(item,kind);
  return Number.isFinite(cutoff)&&cutoff<=now;
}
export function activityPhase(item:ActivityCardData,kind:ActivityKind,now=Date.now()):string {
  if(kind==='post') return registrationClosed(item,kind,now)?'ended':'open';
  if(['finished','cancelled'].includes(item.status||'') || item.end_time && Date.parse(utcInput(item.end_time))<=now)return 'ended';
  if(item.start_time && Date.parse(utcInput(item.start_time))<=now)return 'ongoing';
  return registrationClosed(item,kind,now)?'registration_closed':'open';
}
export function visibleInDiscovery(item:ActivityCardData,kind:ActivityKind,now=Date.now()):boolean {
  return Number.isFinite(registrationCutoff(item,kind)) && activityPhase(item,kind,now)!=='ended'
    && (kind==='post'?['open','full'].includes(item.status||''):['open','ongoing'].includes(item.status||''));
}
