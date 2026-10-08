import { api, type HealthState } from '../api/client';
import { evidenceDeadline, recordEvidence } from '../api/evidence';

// View-model boundary for later domain read providers, not published HTTP endpoints.
// Production readers below explicitly report unavailable until those providers exist.
export type DomainRead<T> = { availability: 'unavailable' } | {
  availability: 'available'; quality: 'CURRENT' | 'STALE'; evaluated_at: string; items: T[];
  activity?: {continuity:'CONTINUOUS_SINCE_BASELINE'|'GAP'|'UNKNOWN';total:number;limit:number;offset:number};
};
export interface DomainFilters { source_id?: string; event_type?: EventType; category?: HygieneCategory; offset?:number }
export type DomainLoader<T> = (filters: DomainFilters, signal: AbortSignal) => Promise<DomainRead<T>>;
export const eventTypes = ['CREATE', 'WRITE', 'RENAME', 'DELETE', 'METADATA_CHANGE', 'SECURITY_CHANGE'] as const;
export type EventType = typeof eventTypes[number];
export interface ActivityEvent {
  id: string; source_id: string; object_id: string; occurred_at: string; event_type: EventType;
  actor: string | null; client: string | null; old_path: string | null; new_path: string | null;
  confidence: number | null;
  provenance?: 'NTFS_USN'|'UNKNOWN'; path_quality?:'COMPLETE'|'UNAVAILABLE'; file_id?:string|null;
}
export const recoverySteps = ['local', 'offhost', 'backup', 'rpo', 'verify', 'retention', 'restore', 'rto', 'consistency'] as const;
export type RecoveryStep = typeof recoverySteps[number];
export interface RecoveryEvidence {
  state: HealthState; observed_at: string | null; seconds?: number | null;
  consistency?: 'CRASH_CONSISTENT' | 'GUEST_AGENT' | 'VSS_QUIESCED' | 'UNKNOWN';
}
export interface RecoveryWorkload {
  id: string; name: string; platform_state: HealthState;
  protection: 'PROTECTED' | 'UNPROTECTED' | 'UNKNOWN';
  steps: Partial<Record<RecoveryStep, RecoveryEvidence>>;
}
export interface AccessRecord {
  id:string; path:string; expected:string[] | null; actual:string[] | null; owner:string | null;
  group_chain:string[] | null; drift:'MATCH' | 'DRIFT' | 'UNKNOWN';
  exceptions:{reason:string;expires_at:string | null}[];
}
export const hygieneCategories=['LONG_PATH','AGE','FILE_TYPE','TEMP_LOCK','LARGE','ZERO_BYTE','DUPLICATE','RARE_EXTENSION'] as const;
export type HygieneCategory=typeof hygieneCategories[number];
export interface HygieneRecord {
  id:string; path:string; category:HygieneCategory; value:number | null;
  unit:'BYTES' | 'DAYS' | 'CHARS' | 'COUNT';
  classification:'ACTIVE' | 'RECENT' | 'STALE' | 'CANDIDATE' | 'HASH_PENDING' | 'CONFIRMED' | 'DIFFERENT_CONTENT' | 'EXCLUDED' | 'UNKNOWN';
}
export const diagnosticPhases=['PRE_TRIGGER','TRIGGER','POST_TRIGGER'] as const;
export interface DiagnosticRecord {
  id:string; phase:typeof diagnosticPhases[number]; occurred_at:string;
  trigger:'SLOW_OPERATION' | 'ACCESS_DENIED' | 'MANUAL' | 'UNKNOWN';
  metric:'LATENCY' | 'THROUGHPUT' | 'ERRORS'; value:number | null;
}
export interface DiscoveryRecord {
  id:string; series_name:string; schema_family:string | null; path:string;
  digitization_candidate:boolean | null;
  workflow_state:'OBSERVED' | 'CANDIDATE' | 'REVIEWED' | 'APPROVED' | 'REJECTED' | 'UNKNOWN';
  confidence:number | null;
}
export interface PolicyRecord {
  id:string; name:string;
  domain:'TELEMETRY' | 'CAPACITY' | 'FILESYSTEM' | 'SMB_DFS' | 'ACCESS' | 'VSS' | 'RECOVERY' | 'NETWORK' | 'PVE_ZFS' | 'HYGIENE'; scope:string | null;
  threshold_seconds:number | null; threshold_bytes:number | null; exception_count:number; updated_at:string | null;
}
export interface AuditRecord {
  id:string; occurred_at:string; actor:string | null; target:string | null;
  action:'INGEST_BATCH_PROCESSED' | 'INGEST_POSTPROCESSED' | 'COLLECTOR_REGISTERED' | 'POLICY_CHANGED' | 'OTHER';
  outcome:'SUCCESS' | 'FAILURE' | 'UNKNOWN';
}
const unavailable = async (): Promise<{availability:'unavailable'}> => ({availability:'unavailable'});
const activity:DomainLoader<ActivityEvent> = async (filters,signal) => {
  const response=await api.activity({source_id:filters.source_id,event_type:filters.event_type,
    offset:filters.offset},signal);
  const result:DomainRead<ActivityEvent>={availability:'available',
    quality:response.quality==='COMPLETE'?'CURRENT':'STALE',evaluated_at:response.evaluated_at,
    activity:{continuity:response.continuity,total:response.total,limit:response.limit,offset:response.offset},
    items:response.items.map(item=>({id:item.id,source_id:item.source_id,
      object_id:item.object_id ?? JSON.stringify([item.volume_identity,item.file_id ?? item.id]),
      occurred_at:item.occurred_at,event_type:item.event_type,actor:item.actor ?? null,
      client:item.client ?? null,old_path:item.old_relative_path,new_path:item.new_relative_path,
      confidence:item.confidence ?? null,
      provenance:item.provenance,path_quality:item.path_quality,file_id:item.file_id})),
  };
  const deadline=evidenceDeadline(response);
  if(deadline!==null) recordEvidence(result,deadline,0);
  return result;
};
export const domainReaders: {
  activity:DomainLoader<ActivityEvent>; recovery:DomainLoader<RecoveryWorkload>;
  access:DomainLoader<AccessRecord>; hygiene:DomainLoader<HygieneRecord>;
  diagnostics:DomainLoader<DiagnosticRecord>; discovery:DomainLoader<DiscoveryRecord>;
  policies:DomainLoader<PolicyRecord>; audit:DomainLoader<AuditRecord>;
} = {
  activity, recovery:unavailable, access:unavailable, hygiene:unavailable,
  diagnostics:unavailable, discovery:unavailable, policies:unavailable, audit:unavailable,
};
