import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { savePreferences,usePreferences,validTimeZone,type Preferences } from '../preferences';

const languages=[{value:'ru-RU',label:'russian'},{value:'en-US',label:'english'}] as const;
export function SettingsPage(){
  const {t}=useTranslation();const preferences=usePreferences();
  const [locale,setLocale]=useState<Preferences['locale']>(preferences.locale);
  const [timeZone,setTimeZone]=useState(preferences.timeZone);
  const [message,setMessage]=useState<'saved' | 'temporary' | 'invalid' | null>(null);
  useEffect(()=>{setLocale(preferences.locale);setTimeZone(preferences.timeZone);},[preferences]);
  return <section className="settings"><p>{t('settings.scope')}</p>
    <form onSubmit={event=>{
      event.preventDefault();
      if (!validTimeZone(timeZone.trim())) {setMessage('invalid');return;}
      setMessage(savePreferences({locale,timeZone:timeZone.trim()})?'saved':'temporary');
    }}>
      <div className="field"><label htmlFor="display-locale">{t('common.locale')}</label><select id="display-locale" value={locale} onChange={event=>setLocale(event.target.value as Preferences['locale'])}>
        {languages.map(language=><option key={language.value} value={language.value}>{t(`settings.${language.label}`)}</option>)}
      </select></div>
      <label>{t('common.timeZone')}<input value={timeZone} onChange={event=>{setTimeZone(event.target.value);setMessage(null);}} aria-invalid={message==='invalid'} aria-describedby="timezone-help" /></label>
      <button type="submit">{t('settings.save')}</button>
    </form>
    <p id="timezone-help">{t('settings.timezoneHelp')}</p>
    {message?<p role={message==='invalid'?'alert':'status'}>{t(`settings.${message}`)}</p>:null}
  </section>;
}
