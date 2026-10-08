import { describe,it,expect } from "vitest";
import { tournamentFieldIssues } from "../src/domain/tournament-form";
import { defaultConfig } from "../src/services/tournaments";
const valid=()=>({title:"个人比赛",auto_title:false,start_date:"2026-11-01",start:"09:00",end_date:"2026-11-01",end:"17:00",city:"南京市",address:"地图地点",latitude:0,longitude:0,max_participants:16,entry_fee:"0",courts:"1号场地",registration_hours:"0",cancellation_hours:"1"});
describe("actionable tournament form validation",()=>{
 it("accepts a complete personal tournament without requiring a club",()=>{
  expect(tournamentFieldIssues(valid(),defaultConfig(),null)).toEqual([]);
 });
 it("collects all missing fields including collapsed settings without treating empty numbers as zero",()=>{
  const form={...valid(),title:"",address:"",latitude:null,start_date:"",max_participants:"",entry_fee:"",registration_hours:""};
  const issues=tournamentFieldIssues(form,defaultConfig(),null);
  expect(issues.map(i=>i.field)).toEqual(expect.arrayContaining(["title","address","start_date","max_participants","entry_fee","registration_hours"]));
  expect(issues.find(i=>i.field==="registration_hours")?.panel).toBe("advanced");
 });
 it("validates mapped venue, generated titles and preview separately",()=>{
  const form={...valid(),title:"",auto_title:true,address:"",latitude:null,longitude:null};
  expect(tournamentFieldIssues(form,defaultConfig(),{venue_id:1})).toEqual([]);
  expect(tournamentFieldIssues({...form,auto_title:false},defaultConfig(),null,true)).toEqual([]);
 });
 it("rejects invalid duration, dates, double numbers and missing qualifiers",()=>{
  const cfg={...defaultConfig(),format:"groups_knockout" as const,group_count:2,qualifiers_per_group:"" as any,match_minutes:1};
  const issues=tournamentFieldIssues({...valid(),end:"08:00"},cfg,null);
  expect(issues.map(i=>i.field)).toEqual(expect.arrayContaining(["end_date","match_minutes","qualifiers_per_group"]));
  expect(issues.find(i=>i.field==="qualifiers_per_group")?.panel).toBe("rules");
  expect(tournamentFieldIssues({...valid(),max_participants:7},{...defaultConfig(),discipline:"doubles"},null)[0].message).toContain("偶数");
 });
});
