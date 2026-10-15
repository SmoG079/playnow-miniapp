<script setup lang="ts">
import { getCurrentInstance, nextTick, onBeforeUnmount, ref } from "vue";
import { onHide } from "@dcloudio/uni-app";
import { activityCode, copyActivityLink, type ShareKind } from "../services/activity-sharing";
import { activityShare } from "../utils/share";
const props=defineProps<{kind:ShareKind;id:string|number;title:string;schedule?:string;place?:string|null;people?:string;fee?:number}>();
const visible=ref(false),busy=ref(false),preview=ref(false),image=ref(""),imageTitle=ref("");
const instance=getCurrentInstance();
let alive=true;
onHide(()=>{visible.value=false;preview.value=false;});
onBeforeUnmount(()=>{alive=false;});
async function run(work:()=>Promise<void>) {
  if(busy.value)return;
  busy.value=true;
  uni.showLoading({title:"正在生成",mask:true});
  let failure="";
  try{await work();}catch(error:any){failure=error.message||"生成失败，请重试";}
  finally{uni.hideLoading();busy.value=false;}
  if(failure && alive)uni.showToast({title:failure,icon:"none"});
}
async function copyLink(){await run(async()=>{await copyActivityLink(props.kind,props.id);visible.value=false;uni.showToast({title:"已复制，链接30天内有效",icon:"none"});});}
async function showCode(){await run(async()=>{
  const path=await activityCode(props.kind,props.id);
  if(!alive)return;
  image.value=path;imageTitle.value="活动小程序码";visible.value=false;preview.value=true;
});}
function wrapText(ctx:UniApp.CanvasContext,text:string,x:number,y:number,width:number,lineHeight:number,maxLines:number){
  let line="",row=0;
  for(const char of text){
    if(ctx.measureText(line+char).width>width){ctx.fillText(line,x,y+row*lineHeight);row++;line="";if(row>=maxLines)return;}
    line+=char;
  }
  if(line)ctx.fillText(line,x,y+row*lineHeight);
}
async function poster(){await run(async()=>{
  const code=await activityCode(props.kind,props.id);
  if(!alive)return;
  await nextTick();
  const ctx=uni.createCanvasContext("activity-poster",instance?.proxy);
  ctx.setFillStyle("#f2f7f3");ctx.fillRect(0,0,600,900);
  ctx.setFillStyle("#006633");ctx.fillRect(0,0,600,160);
  ctx.setFillStyle("#fff");ctx.setFontSize(34);ctx.fillText("PlayNow · 一起上场",36,72);
  ctx.setFontSize(20);ctx.fillText(props.kind==="post"?"网球约球":"网球比赛",36,118);
  ctx.setFillStyle("#fff");ctx.fillRect(24,184,552,692);
  ctx.setFillStyle("#203c2b");ctx.setFontSize(30);wrapText(ctx,props.title,48,238,504,42,2);
  ctx.setFontSize(22);ctx.setFillStyle("#576c60");
  wrapText(ctx,props.schedule||"时间见活动详情",48,346,504,32,2);
  wrapText(ctx,props.place||"地点见活动详情",48,432,504,32,2);
  ctx.fillText(props.people||"欢迎球友报名",48,530);
  ctx.setFillStyle("#006633");ctx.setFontSize(28);ctx.fillText(Number(props.fee)>0?`¥${props.fee}/人`:"免费参加",48,590);
  ctx.drawImage(code,48,642,170,170);
  ctx.setFillStyle("#203c2b");ctx.setFontSize(22);ctx.fillText("扫码查看活动",246,706);
  ctx.setFillStyle("#738579");ctx.setFontSize(18);ctx.fillText("长按识别小程序码报名",246,744);
  await new Promise<void>(resolve=>ctx.draw(false,()=>resolve()));
  const path=await new Promise<string>((resolve,reject)=>uni.canvasToTempFilePath({canvasId:"activity-poster",width:600,height:900,destWidth:1200,destHeight:1800,fileType:"png",success:r=>resolve(r.tempFilePath),fail:()=>reject(new Error("海报生成失败，请重试"))},instance?.proxy));
  if(!alive)return;
  image.value=path;imageTitle.value="活动海报";visible.value=false;preview.value=true;
});}
function shareImage(){
  uni.showShareImageMenu({path:image.value,entrancePath:activityShare(props.kind,props.id).path.slice(1),needShowEntrance:true,fail:(error:any)=>{if(!error.errMsg?.includes("cancel"))uni.showToast({title:"暂时无法分享图片，请保存后分享",icon:"none"});}});
}
function saveImage(){uni.saveImageToPhotosAlbum({filePath:image.value,success:()=>uni.showToast({title:"已保存"}),fail:()=>uni.showToast({title:"保存失败，请检查相册权限",icon:"none"})});}
</script>
<template>
  <!-- #ifdef MP-WEIXIN -->
  <view class="activity-share">
    <wd-button variant="text" :disabled="busy" custom-style="width:48px;min-width:48px;height:52px;padding:0;border:0;background:transparent;color:#858585" @click="visible=true"><view class="share-content"><wd-icon name="share-external" size="25px" /><text class="share-label">分享</text></view></wd-button>
  </view>
  <wd-popup v-model="visible" root-portal position="bottom" round safe-area-inset-bottom :z-index="200">
    <view class="share-options">
      <wd-button variant="text" open-type="share" custom-style="width:100%;min-width:0;height:auto;padding:0;background:transparent" @click="visible=false"><view class="share-option"><view class="share-symbol friends"><wd-icon name="message" size="28px" /></view><text>微信好友</text></view></wd-button>
      <view class="share-option" role="button" @click="poster"><view class="share-symbol poster"><wd-icon name="image" size="28px" /></view><text>生成海报</text></view>
      <view class="share-option" role="button" @click="showCode"><view class="share-symbol code"><wd-icon name="qrcode" size="28px" /></view><text>二维码</text></view>
      <view class="share-option" role="button" @click="copyLink"><view class="share-symbol link"><wd-icon name="copy" size="28px" /></view><text>复制链接</text></view>
    </view>
    <view class="share-cancel" role="button" @click="visible=false">取消</view>
  </wd-popup>
  <wd-popup v-model="preview" root-portal position="center" round closable :z-index="210" custom-style="width:88vw;max-width:400px">
    <view class="share-preview"><text class="preview-title">{{ imageTitle }}</text><image :src="image" mode="aspectFit" class="preview-image" :class="{'code-image':imageTitle==='活动小程序码'}" show-menu-by-longpress /><text class="share-hint">长按识别小程序码，查看活动并报名</text><view class="preview-actions"><wd-button size="small" custom-style="min-width:0" variant="plain" @click="saveImage">保存图片</wd-button><wd-button size="small" custom-style="min-width:0" @click="shareImage">分享图片</wd-button></view></view>
  </wd-popup>
  <canvas canvas-id="activity-poster" class="poster-canvas" style="width:600px;height:900px" />
  <!-- #endif -->
</template>
<style scoped>
.activity-share{display:flex;align-items:center;flex:none}.share-content{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}.share-label{font-size:11px;line-height:16px;color:#777}
.share-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:26px 14px 24px;background:#fff}.share-option{display:flex;flex-direction:column;align-items:center;gap:9px;font-size:13px;line-height:20px;color:#666}.share-symbol{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff}.friends{background:#49c96d}.poster{background:#ffa13e}.code{background:#0bc79b}.link{background:#119df4}.share-cancel{text-align:center;border-top:1px solid #f0f0f0;padding:16px;color:#333;background:#fff;font-size:17px;line-height:24px}
.share-preview{padding:24px 20px;display:flex;flex-direction:column;align-items:center;gap:16px}.preview-title{font-size:18px;font-weight:600;color:#203c2b}.preview-image{width:100%;height:54vh}.preview-image.code-image{height:260px}.share-hint{font-size:12px;color:#738579;text-align:center}.preview-actions{display:flex;gap:12px}.poster-canvas{position:fixed;left:-2000px;top:0;pointer-events:none}
</style>
