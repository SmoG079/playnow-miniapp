import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
export default defineConfig(({ mode }) => {
  if (mode !== 'prototype') throw new Error('Prototype only: production release is blocked until API migration and acceptance are complete.')
  return { plugins: [uni()], server: { host: '127.0.0.1', port: 5188 }, optimizeDeps: { exclude: ['@wot-ui/ui'] } }
})
