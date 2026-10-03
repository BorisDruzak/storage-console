import { useSyncExternalStore } from 'react';

export const preferencesKey='storage-console.preferences.v1';
export interface Preferences {locale:'ru-RU' | 'en-US';timeZone:string}
const defaults:Preferences={locale:'ru-RU',timeZone:'UTC'};
let cachedRaw:string | null | undefined;
let cached:Preferences=defaults;
let temporary:Preferences | null=null;
export function validTimeZone(value:string):boolean {
  if (!value || value.length>128) return false;
  try { new Intl.DateTimeFormat('en-US',{timeZone:value});return true; } catch {return false;}
}
export function getPreferences():Preferences {
  if (temporary) return temporary;
  let raw:string | null;
  try {raw=localStorage.getItem(preferencesKey);} catch {return cached;}
  if (raw===cachedRaw) return cached;
  cachedRaw=raw;cached=defaults;
  if (raw && raw.length<=4096) {
    try {
      const data:unknown=JSON.parse(raw);
      if (data && typeof data==='object' && !Array.isArray(data)) {
        const value=data as Record<string,unknown>;
        cached={locale:value.locale==='en-US'?'en-US':'ru-RU',timeZone:typeof value.timeZone==='string'&&validTimeZone(value.timeZone)?value.timeZone:'UTC'};
      }
    } catch { /* Corrupt preferences recover to safe defaults. */ }
  }
  return cached;
}
export function savePreferences(value:Preferences):boolean {
  if (!validTimeZone(value.timeZone) || !['ru-RU','en-US'].includes(value.locale)) throw new Error('INVALID_PREFERENCES');
  let persisted=true;
  try {localStorage.setItem(preferencesKey,JSON.stringify(value));temporary=null;} catch {temporary={...value};persisted=false;}
  window.dispatchEvent(new Event('preferenceschange'));
  return persisted;
}
function subscribe(callback:()=>void) {
  const storage=(event:StorageEvent)=>{if (event.key===preferencesKey || event.key===null) {temporary=null;callback();}};
  window.addEventListener('storage',storage);window.addEventListener('preferenceschange',callback);
  return ()=>{window.removeEventListener('storage',storage);window.removeEventListener('preferenceschange',callback);};
}
export function usePreferences(){return useSyncExternalStore(subscribe,getPreferences);}
