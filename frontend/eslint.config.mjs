import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

// Flat config (Next 16 removed `next lint`; rules carried over from .eslintrc.json).
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'warn',
      'react/no-unescaped-entities': 'off',
      // New in react-hooks v7 (Next 16); flags pre-existing effects — perf advice,
      // not a correctness bug. Warn until those components are refactored.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  {
    files: ['jest.setup.js', 'tailwind.config.ts'],
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
  globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts', 'coverage/**']),
])
