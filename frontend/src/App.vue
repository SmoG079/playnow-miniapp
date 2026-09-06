<script setup lang="ts">
import { onLaunch } from "@dcloudio/uni-app";
import { useSession } from "./stores/session";
onLaunch(() => {
  useSession()
    .fetchUser()
    .catch(() => {});
});
</script>
<style lang="scss">
@use "./styles/theme.scss";
</style>
