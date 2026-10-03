import type { HealthState } from '../api/client';

// View-model boundary for later domain read providers, not published HTTP endpoints.
// Production readers below explicitly report unavailable until those providers exist.
export type DomainRead<T> = { availability: 'unavailable' } | {
  availability: 'available'; quality: 'CURRENT' | 'STALE'; evaluated_at: string; items: T[];
};
export interface DomainFilters { source_id?: string; event_type?: EventType }
export type DomainLoader<T> = (filters: DomainFilters, signal: AbortSignal) => Promise<DomainRead<T>>;
export const eventTypes = ['CREATE', 'WRITE', 'RENAME', 'DELETE', 'METADATA_CHANGE', 'SECURITY_CHANGE'] as const;
export type EventType = typeof eventTypes[number];
export interface ActivityEvent {
  id: string; source_id: string; object_id: string; occurred_at: string; event_type: EventType;
  actor: string | null; client: string | null; old_path: string | null; new_path: string | null;
  confidence: number | null;
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
const unavailable = async (): Promise<{availability:'unavailable'}> => ({availability:'unavailable'});
export const domainReaders: { activity: DomainLoader<ActivityEvent>; recovery: DomainLoader<RecoveryWorkload> } = {
  activity: unavailable, recovery: unavailable,
};
