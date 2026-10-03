import type { ActivityEvent } from './models';

export interface ActivityGroup extends ActivityEvent { count: number; first_at: string; last_at: string }
export function groupActivity(events: readonly ActivityEvent[]): ActivityGroup[] {
  const groups = new Map<string, ActivityGroup>();
  const seen = new Set<string>();
  for (const item of events) {
    // Deduplicate delivery, not observations from different sources.
    const identity = JSON.stringify([item.source_id,item.id]);
    if (seen.has(identity)) continue;
    seen.add(identity);
    const key = JSON.stringify([item.source_id,item.object_id,item.event_type,item.actor,item.client,
      item.old_path,item.new_path,item.confidence,Math.floor(Date.parse(item.occurred_at)/60000)]);
    const existing = groups.get(key);
    if (!existing) groups.set(key,{...item,count:1,first_at:item.occurred_at,last_at:item.occurred_at});
    else {
      existing.count += 1;
      if (Date.parse(item.occurred_at)<Date.parse(existing.first_at)) existing.first_at=item.occurred_at;
      if (Date.parse(item.occurred_at)>Date.parse(existing.last_at)) existing.last_at=item.occurred_at;
    }
  }
  return [...groups.values()].sort((a,b)=>Date.parse(b.last_at)-Date.parse(a.last_at) || a.id.localeCompare(b.id));
}
