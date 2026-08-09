import security from 'eslint-plugin-security';
import tsParser from '@typescript-eslint/parser';

// Static security scan for LLM-generated TypeScript, run by TypeScriptRunner
// after every pulse (ace_enterprise-85u) — the TS analog of Bandit for Python.
// eslint-plugin-security's recommended rules all default to "warn"; the
// subset with a direct Bandit-HIGH analog (subprocess exec, eval, unsafe
// dynamic code loading, ReDoS, weak crypto) is escalated to "error" so it
// gates the TDD cycle the same way Bandit's HIGH findings do. Everything
// else stays "warn" — informational, non-blocking.
export default [
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tsParser,
    },
  },
  security.configs.recommended,
  {
    rules: {
      'security/detect-child-process': 'error',
      'security/detect-eval-with-expression': 'error',
      'security/detect-non-literal-require': 'error',
      'security/detect-unsafe-regex': 'error',
      'security/detect-pseudoRandomBytes': 'error',
    },
  },
];
