import { localTime, utcInput } from '../services/tournaments';
export function notificationTime(value?:string,full=false):string {
  if(!value || !Number.isFinite(Date.parse(utcInput(value))))return '';
  const local=localTime(value);
  return full?local:local.slice(5);
}
