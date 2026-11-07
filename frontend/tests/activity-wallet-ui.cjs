// Isolated H5 UI verification: intercept every API and block external traffic.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='http://127.0.0.1:5188',api='https://www.tennisplaynow.site/api/v1';
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});
  const errors=[],writes=[];let joined=false;
  const user={id:'member',role:'user',nickname:'球友',phone:'13800000000'};
  const wallet={available_cents:21272,debt_cents:0,paid_cents:10000,pending_cents:20000,gross_cents:21400,refund_cents:0,fee_cents:128,locked_cents:0,platform_fee_cents:0,fee_rate:'.006',fee_verified:false,enabled:false,disabled_reason:'提现暂未开放，费用和转账额度核实后开放',minimum_cents:10,maximum_cents:20000,daily_limit_cents:20000,activities:[{activity_id:701,kind:'post',title:'周末网球活动',date:'2030-01-01',count:14,gross_cents:21400,fee_cents:128,refund_cents:0,locked_cents:0,available_cents:21272}],transfers:[{id:1,amount_cents:20000,state:'SUCCESS'}]};
  await context.route('**/*',async route=>{
   const req=route.request(),url=req.url();
   if(url.startsWith(api)){
    const headers={'access-control-allow-origin':base,'access-control-allow-headers':'authorization,content-type','access-control-allow-methods':'GET,POST,DELETE,OPTIONS'};
    if(req.method()==='OPTIONS')return route.fulfill({status:204,headers});
    const path=url.slice(api.length).split('?')[0];let body={};
    if(req.method()!=='GET'){
     writes.push(path);
     if(path==='/clubs/1/community')joined=req.method()==='POST';
     else throw new Error('Unexpected write '+path);
    }else if(path==='/users/me')body=user;
    else if(path==='/activity-wallet')body=wallet;
    else if(path==='/clubs/1')body={id:1,name:'上海网球社群',description:'没有自有球场，也能一起组织网球活动。',city:'上海市',contact_phone:'13800000000',images:[],venues:[]};
    else if(path==='/clubs/1/community')body={count:joined?1:0,joined,owner:false,members:[]};
    else if(path==='/clubs')body={items:[{id:1,name:'上海网球社群',description:'一起打球',city:'上海市',images:[]}],total:1};
    else if(path.endsWith('/unread-count'))body={total:0,system:0,private:0,by_conversation:{}};
    else body={items:[]};
    return route.fulfill({headers,contentType:'application/json',body:JSON.stringify(body)});
   }
   if(url.startsWith(base+'/')||url.startsWith('data:')||url.startsWith('blob:'))return route.continue();
   return route.abort();
  });
  await context.addInitScript(()=>{localStorage.setItem('access_token','isolated');localStorage.setItem('session_context','account-v2:web:https://www.tennisplaynow.site:8443/api/v1');localStorage.setItem('discovery_city_v1',JSON.stringify({type:'object',data:{city:'上海市',region:['上海市','上海市','浦东新区']}}));});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#/pages/profile/activity-wallet',{waitUntil:'networkidle'});
  await page.getByText('当前账户可提现',{exact:true}).waitFor();
  assert.match(await page.locator('body').innerText(),/212\.72/);
  assert.match(await page.locator('body').innerText(),/微信支付手续费（预估）/);
  assert.match(await page.locator('body').innerText(),/平台服务费 ¥0\.00/);
  const button=page.locator('.wd-button').filter({hasText:'提取当前列表活动收入'});
  assert.match(await button.getAttribute('class'),/disabled/);
  await page.screenshot({path:'/tmp/playnow-wallet-ui/wallet.png',fullPage:true});
  await page.goto(base+'/#/pages/common/club-detail?id=1',{waitUntil:'networkidle'});
  await page.getByText('加入俱乐部',{exact:true}).click();
  await page.getByText('退出俱乐部',{exact:true}).waitFor();
  assert.deepEqual(writes,['/clubs/1/community']);
  await page.getByText('退出俱乐部',{exact:true}).click();
  await page.getByText('加入俱乐部',{exact:true}).waitFor();
  await page.screenshot({path:'/tmp/playnow-wallet-ui/community.png',fullPage:true});
  for(const route of ['select','confirm','venue-detail']){
   await page.goto(base+'/#/pages/booking/'+route+'?id=1',{waitUntil:'networkidle'});
   await page.getByText('订场服务暂未开放',{exact:true}).waitFor();
  }
  assert.deepEqual(writes,['/clubs/1/community','/clubs/1/community']);
  assert.deepEqual(errors,[]);
  console.log('PASS: wallet fees and disabled transfer gate, no-court club membership, old booking routes paused; all API traffic intercepted.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
