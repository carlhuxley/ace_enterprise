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
    // Kept in sync with the runtime config TypeScriptRunner writes per pulse
    // (src/agents/typescript_runner.py) -- see the comment there.
    minWorkers: 1,
    maxWorkers: 1,
  },
})
