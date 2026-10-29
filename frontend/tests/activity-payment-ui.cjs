// Isolated request interception: never sends API requests to production.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='http://127.0.0.1:5188';
const api='https://www.tennisplaynow.site:8443/api/v1';
const output='/tmp/playnow-activity-payment-ui';fs.mkdirSync(output,{recursive:true});
(async()=>{
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
const context=await browser.newContext({viewport:{width:390,height:844}});
let registered=false,method='offline',manager=false;const writes=[],errors=[],reads=[];
const user={id:'guest',nickname:'测试球友',role:'club_admin',managed_club_ids:[1],phone:'13800000000',ntrp_level:3};
const post=()=>({id:701,user_id:'host',user_nickname:'测试组织者',title:'线下收费约球',city:'上海市',address:'测试网球场',location_name:'测试网球场',preferred_date:'2030-01-01',preferred_start:'09:00',preferred_end:'11:00',min_players:2,max_players:4,price:36,payment_method:method,status:'open',approval_required:false,registration_count:registered?1:0,registrations:registered?[{id:1,user_id:'guest',user_nickname:user.nickname,status:'approved',payment:'offline'}]:[],images:[]});
const tournament=()=>({id:702,title:'线下收费比赛',club_id:null,organizer_user_id:'host',organizer_nickname:'测试组织者',city:'上海市',address:'测试网球场',location_name:'测试网球场',start_time:'2030-01-01T01:00:00',end_time:'2030-01-01T05:00:00',entry_fee:36,payment_method:method,status:'open',prepay_enabled:false,can_register:!registered,can_manage:manager,can_review:false,registration_deadline:'2030-01-01T00:00:00',cancellation_deadline:'2029-12-31T23:00:00',current_participants:registered?1:0,max_participants:4,config:{format:'knockout',discipline:'singles',group_count:1,pairing:null,courts:['1号场','2号场'],match_minutes:60,gap_minutes:0},prizes:[],images:[],registrations:[],participants:[],entry_teams:[],teams:manager?[{id:1,name:'甲队',group_no:1},{id:2,name:'乙队',group_no:1}]:[],matches:manager?[{id:3,key:'3',group_no:1,round_no:1,position:1,team_a_id:1,team_b_id:2,status:'pending',kind:'knockout'}]:[],rankings:[],draw_version:0,published_version:0,my_registration:registered?{id:2,user_id:'guest',status:'confirmed',admission:'active',approval:'approved',payment:'offline'}:null});
await context.route('**/*',async route=>{
 const req=route.request(),url=req.url();
 if(url.startsWith(api+'/')){
  const headers={'access-control-allow-origin':base,'access-control-allow-headers':'authorization,content-type','access-control-allow-methods':'GET,POST,PUT,OPTIONS'};
  if(req.method()==='OPTIONS')return route.fulfill({status:204,headers});
  const endpoint=url.slice(api.length).split('?')[0];if(req.method()==='GET')reads.push(url);let body={};
  if(req.method()==='POST'){writes.push(endpoint);if(endpoint.endsWith('/register')){registered=true;body={msg:'ok',payment:'offline',admission:'active'};}else throw Error('Unexpected write '+endpoint);}
  else if(endpoint==='/users/me')body=user;
  else if(endpoint==='/posts/701')body=post();
  else if(endpoint==='/tournaments/702')body=tournament();
  else if(endpoint.startsWith('/clubs'))body={items:[]};
  else if(endpoint.endsWith('/comments'))body={items:[]};
  else if(endpoint.endsWith('/unread-count'))body={total:0,system:0,private:0,by_conversation:{}};
  else if(endpoint==='/discovery/cities')body=['上海市'];
  else body={items:[]};
  return route.fulfill({headers,contentType:'application/json',body:JSON.stringify(body)});
 }
 if(url.startsWith(base+'/')||url.startsWith('data:')||url.startsWith('blob:'))return route.continue();
 return route.abort();
});
await context.addInitScript(({api})=>{localStorage.setItem('discovery_city_v1',JSON.stringify({type:'object',data:{city:'上海市',region:['上海市','上海市','浦东新区']}}));localStorage.setItem('access_token','isolated-fixture');localStorage.setItem('session_context','account-v2:web:'+api);},{api});
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
for(const target of ['post','tournament']){
 registered=false;method='offline';
 await page.goto(base+'/#/pages/common/'+target+'-detail?id='+(target==='post'?701:702),{waitUntil:'networkidle'});
 const button=page.locator('.fixed-action .wd-button').filter({hasText:target==='post'?'报名参加':'报名 ¥36'});
 await button.click();
 await page.locator('uni-modal').waitFor();
 await page.locator('uni-toast').waitFor({state:'hidden'});
 assert.match(await page.locator('uni-modal').innerText(),/报名费 ¥36.00\/人/);
 assert.match(await page.locator('uni-modal').innerText(),/报名时无需线上支付/);
 await page.waitForTimeout(350);
 await page.screenshot({path:output+'/'+target+'-offline-confirm.png'});
 await page.locator('.uni-modal__btn_primary').click();
 await page.waitForTimeout(400);
 assert(writes.includes('/'+(target==='post'?'posts/701':'tournaments/702')+'/register'));
 assert(!writes.some(x=>/\/pay$/.test(x)));
 assert.match(await page.locator('body').innerText(),target==='post'?/已报名 · 取消/:/线下付款/);
}
// Online paid tournament stays unavailable while online payments are disabled.
registered=false;method='online';await page.reload({waitUntil:'networkidle'});
assert.match(await page.locator('.fixed-action').innerText(),/预付尚未开放/);
// Publishing forms expose both channels when a fee is entered.
for(const target of ['post','tournament']){
 await page.goto(base+'/#/pages/publish/'+target+'-create',{waitUntil:'networkidle'});
 // Use the field adjacent to the exact label, independent of input type normalization.
 const label=page.getByText(target==='post'?'人均费用（元）':'报名费（每人） *',{exact:true});
 const input=label.locator('xpath=following::input[1]');
 await input.fill('36');
 const trigger=page.locator('.payment-select .choice-trigger');
 assert((await trigger.boundingBox()).y < (await input.boundingBox()).y);
 await trigger.click();
 await page.locator('.choice-sheet:visible').waitFor();
 const sheet=page.locator('.choice-sheet:visible');
 assert.match(await sheet.locator('.is-selected').innerText(),/线下付款/);
 assert.match(await sheet.innerText(),/报名无需线上支付/);
 await page.waitForTimeout(350);
 await page.screenshot({path:output+'/'+target+'-payment-select.png'});
 await sheet.locator('.choice-option').filter({hasText:'线上付款'}).click();
 await sheet.waitFor({state:'hidden'});
 assert.match(await trigger.innerText(),/线上付款/);
 await trigger.click();
 assert.match(await page.locator('.choice-sheet:visible .is-selected').innerText(),/线上付款/);
 await page.locator('.choice-sheet:visible .choice-close').click();
 assert.match(await trigger.innerText(),/线上付款/);
}
// Shared choices retain competition dependencies and draft selections.
async function choose(title,label) {
 const select=page.locator('.choice-select').filter({has:page.locator('.choice-field-label').filter({hasText:title})});
 await select.locator('.choice-trigger').click();
 await page.locator('.choice-sheet:visible .choice-option').filter({has:page.locator('.choice-label').getByText(label,{exact:true})}).click();
 await page.locator('.choice-sheet:visible').waitFor({state:'hidden'});
}
await choose('赛制','循环赛');
await choose('比赛项目','双打');
await choose('搭档方式','固定搭档');
await page.reload({waitUntil:'networkidle'});
assert.match(await page.locator('.creation-section').filter({hasText:'比赛设置'}).innerText(),/固定搭档/);
await choose('比赛项目','单打');
assert.equal(await page.locator('#required-pairing').count(),0);
await choose('比赛项目','混双');
assert.match(await page.locator('#required-pairing').innerText(),/请选择/);
// Native-picker adapters still send the existing numeric-index events.
await page.goto(base+'/#/pages/home/index',{waitUntil:'networkidle'});
await page.getByText('全部活动',{exact:true}).click();
await page.locator('.choice-sheet:visible .choice-option').filter({hasText:'自由约球'}).click();
await page.waitForTimeout(150);
assert(reads.some(url=>url.includes('activity_type=free')));
await page.getByText('NTRP 等级',{exact:true}).click();
await page.locator('.choice-sheet:visible .choice-option').filter({has:page.getByText('3.5',{exact:true})}).click();
await page.waitForTimeout(150);
assert(reads.some(url=>url.includes('ntrp_levels=3.5')));
// Real multi-selection: close discards edits; confirm commits them.
await page.goto(base+'/#/pages/publish/venue-manage?club_id=1',{waitUntil:'networkidle'});
await page.getByText('新增规则',{exact:true}).click();
const multi=page.locator('.choice-multi-trigger');
assert.match(await multi.innerText(),/星期六、星期日/);
await multi.click();
await page.locator('.choice-sheet:visible .choice-option').filter({hasText:'星期一'}).click();
await page.locator('.choice-sheet:visible .choice-close').click();
assert.doesNotMatch(await multi.innerText(),/星期一/);
await multi.click();
await page.locator('.choice-sheet:visible .choice-option').filter({hasText:'星期一'}).click();
await page.locator('.choice-sheet:visible').getByText('确定（已选 3 项）',{exact:true}).click();
assert.match(await multi.innerText(),/星期一/);
// A child chooser opens above the scheduling popup without closing its parent.
manager=true;registered=false;method='offline';
await page.goto(base+'/#/pages/common/tournament-detail?id=702',{waitUntil:'networkidle'});
await page.getByText('排场',{exact:true}).click();
await page.locator('.edit-popup').waitFor({state:'visible'});
await choose('场地','2号场');
assert.match(await page.locator('.edit-popup:visible').innerText(),/2号场/);
assert.deepEqual(errors,[]);console.log('Isolated UI passed: offline registration, shared payment/config/filter choices, draft restore, multiple-choice cancel/confirm, nested scheduling popup. '+output);
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
