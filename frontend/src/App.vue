<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'
onLaunch(() => {
  if (import.meta.env.VITE_APP_MODE !== 'prototype') throw new Error('Prototype data cannot be used outside prototype mode.')
})
</script>
<style lang="scss">
@use './styles/theme.scss';
</style>
