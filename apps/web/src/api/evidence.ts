import { useEffect,useReducer } from 'react';

const deadlines=new WeakMap<object,number>();
export function recordEvidence(data:object,requestStartedAt:number,lifetimeMs:number){
  deadlines.set(data,requestStartedAt+lifetimeMs);
}
export function evidenceDeadline(data:unknown):number | null {
  return data!==null&&typeof data==='object'?deadlines.get(data) ?? null:null;
}
export function useExpiredEvidence(data:unknown):boolean {
  const deadline=evidenceDeadline(data);
  const [,refresh]=useReducer((value:number)=>value+1,0);
  useEffect(()=>{
    const remaining=deadline===null?null:deadline-performance.now();
    const timer=remaining!==null&&remaining>0?window.setTimeout(refresh,remaining+1):null;
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    return ()=>{if(timer!==null) window.clearTimeout(timer);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};
  },[deadline]);
  return deadline!==null&&performance.now()>=deadline;
}
