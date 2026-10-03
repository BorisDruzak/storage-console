import tseslint from 'typescript-eslint';
import i18next from 'eslint-plugin-i18next';

export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**'] },
  ...tseslint.configs.recommended,
  { files: ['src/**/*.{ts,tsx}'], plugins: { i18next }, rules: {
    'i18next/no-literal-string': ['error', {
      mode: 'jsx-only',
      'jsx-attributes': { exclude: ['className', 'style', 'type', 'key', 'id', 'role', 'aria-current'] },
    }],
  } },
  { files: ['src/*.test.{ts,tsx}'], rules: { 'i18next/no-literal-string': 'off' } },
);
