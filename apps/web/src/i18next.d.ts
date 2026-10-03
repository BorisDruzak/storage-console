import 'i18next';
import ru from '../../../packages/i18n/ru-RU.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof ru };
  }
}
