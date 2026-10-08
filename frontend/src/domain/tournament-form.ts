import { validateConfig, type TournamentConfig } from "../services/tournaments";
export interface TournamentFieldIssue { field:string; panel:string; message:string }
const blank = (v:unknown) => v == null || String(v).trim() === "";
export function tournamentFieldIssues(form:any, config:TournamentConfig, linked:any, previewOnly=false): TournamentFieldIssue[] {
  const issues:TournamentFieldIssue[]=[];
  const add=(field:string,panel:string,message:string)=>issues.push({field,panel,message});
  if (!previewOnly && !form.auto_title && blank(form.title)) add("title","basic","请填写赛事名称");
  for (const [field,label] of [["start_date","开始日期"],["start","开始时间"],["end_date","结束日期"],["end","结束时间"]])
    if (blank(form[field])) add(field,"basic",`请选择${label}`);
  const start=new Date(`${form.start_date}T${form.start}:00+08:00`),end=new Date(`${form.end_date}T${form.end}:00+08:00`);
  if (![form.start_date,form.start,form.end_date,form.end].some(blank) && (!Number.isFinite(+start)||!Number.isFinite(+end)||end<=start)) add("end_date","basic","结束日期与时间必须晚于开始时间");
  if (!previewOnly && (!form.city || (!linked?.venue_id && (!form.address?.trim() || form.latitude == null || form.longitude == null)))) add("address","basic","请在地图中选择比赛地点或关联已预订场地");
  const requirements:[string,unknown,string,string,number,number,boolean][]=[
    ["max_participants",form.max_participants,"人数上限","settings",2,128,true],
    ["group_count",config.group_count,"分组数量","settings",1,16,true],
    ["match_minutes",config.match_minutes,"每场预计分钟","settings",5,300,true],
  ];
  if (!previewOnly) requirements.push(["entry_fee",form.entry_fee,"报名费","settings",0,99999999,false],["registration_hours",form.registration_hours,"报名截止时长","advanced",0,Infinity,false],["cancellation_hours",form.cancellation_hours,"取消截止时长","advanced",0,Infinity,false]);
  if (config.format==="groups_knockout") requirements.push(["qualifiers_per_group",config.qualifiers_per_group,"每组晋级队数","rules",1,8,true]);
  if (!blank(config.max_parallel)) requirements.push(["max_parallel",config.max_parallel,"每轮最多同时场次","rules",1,16,true]);
  for(const [field,value,label,panel,min,max,integer] of requirements) {
    if(blank(value)) add(field,panel,`请填写${label}`);
    else if(!Number.isFinite(Number(value))||Number(value)<min||Number(value)>max||(integer&&!Number.isInteger(Number(value)))) add(field,panel,`${label}须为${min}–${max===Infinity?'不限':max}的${integer?'整数':'有效数字'}`);
  }
  const courts=String(form.courts||'').split('\n').map(x=>x.trim()).filter(Boolean);
  if(!courts.length) add("courts","settings","请填写至少一个排场名称");
  else if(courts.length>16||courts.some(x=>x.length>64)||new Set(courts).size!==courts.length) add("courts","settings","排场名称不能重复，最多16个，每个最多64字");
  if(!issues.length) {
    const message=validateConfig({...config,group_count:Number(config.group_count),qualifiers_per_group:Number(config.qualifiers_per_group),courts},Number(form.max_participants));
    if(message) add(config.format==='groups_knockout'?'qualifiers_per_group':'group_count',config.format==='groups_knockout'?'rules':'settings',message);
  }
  return issues;
}
