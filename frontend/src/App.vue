<script setup lang="ts">
import { onLaunch, onShow, onHide } from "@dcloudio/uni-app";
import {watch} from "vue";
import {useInbox} from "./stores/inbox";
import { useSession } from "./stores/session";
import { isTimelinePreview } from "./utils/share";
let visible=false;
onLaunch(() => {
 if(isTimelinePreview())return;
 const session=useSession();
 watch(()=>[session.loggedIn,session.user?.id],()=>{const inbox=useInbox();inbox.reset();if(visible)inbox.start();});
 session.fetchUser().catch(()=>{});
});
onShow(()=>{if(isTimelinePreview())return;visible=true;useInbox().start();});
onHide(()=>{visible=false;useInbox().stop();});
</script>
<style lang="scss">
@use "./styles/theme.scss";
</style>
