export interface DrawSeat { group_no:number; position:number; team_id:number|null }
export function swapSeats(seats:DrawSeat[],a:number,b:number):DrawSeat[] {
  return seats.map((s,i)=>({...s,team_id:i===a?seats[b].team_id:i===b?seats[a].team_id:s.team_id}));
}
export function seatError(original:DrawSeat[],proposed:DrawSeat[],knockout:boolean):string|undefined {
  const ids=(rows:DrawSeat[])=>rows.map(s=>s.team_id).sort((a,b)=>(a??0)-(b??0)).join(',');
  if(ids(original)!==ids(proposed))return '参赛单位不能重复或遗漏';
  for(const group of new Set(original.map(s=>s.group_no))) {
    const count=(rows:DrawSeat[])=>rows.filter(s=>s.group_no===group&&s.team_id!=null).length;
    if(count(original)!==count(proposed))return '跨组交换须保持各组参赛数量';
  }
  if(knockout&&proposed.some(s=>s.position%2===0&&s.team_id==null&&proposed.find(o=>o.group_no===s.group_no&&o.position===s.position+1)?.team_id==null))return '首轮对阵不能双方均轮空';
}
