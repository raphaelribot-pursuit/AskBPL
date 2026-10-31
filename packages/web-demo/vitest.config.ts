import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      // Process the theme stylesheets so src/test/brand.test.tsx can read them with ?raw (vitest skips CSS by default).
      css: { include: [/src\/theme\/.*\.css/] },
    },
  }),
)
