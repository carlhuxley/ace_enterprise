import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['**/*.{test,spec}.ts', '**/test_*.ts'],
    reporters: ['verbose', 'json'],
    outputFile: '/tmp/vitest-results.json',
    testTimeout: 10000,
    passWithNoTests: false,
  },
})
