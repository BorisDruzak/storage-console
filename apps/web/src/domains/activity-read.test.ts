import { afterEach, expect, test, vi } from 'vitest';
import { ReadResponse } from '../../test-fixtures/http';
import { api } from '../api/client';
import { evidenceDeadline } from '../api/evidence';
import { domainReaders } from './models';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const source = '6a83a99d-247d-4e58-8c49-089c703ab42d';
const response = {
  items: [{id:source,source_id:source,object_id:null,volume_identity:'synthetic-volume',
    file_id:'00000000000000000000000000000001',parent_file_id:null,
    occurred_at:'2026-10-08T04:00:00Z',event_type:'RENAME',
    old_relative_path:null,new_relative_path:'pilot\\После.txt',reason_mask:'0x2000',
    source_event_id:'ntfs-usn:synthetic',provenance:'NTFS_USN',path_quality:'UNAVAILABLE',
    actor:null,client:null,confidence:null}],
  total:1,limit:50,offset:0,evaluated_at:'2026-10-08T04:01:00Z',quality:'UNAVAILABLE',
  continuity:'GAP',window_start_at:'2026-10-07T04:01:00Z',window_end_at:'2026-10-08T04:01:00Z',
};

test('Activity reads actual typed API, filters and unknown provenance without attribution', async () => {
  const fetcher=vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify(response)));
  vi.stubGlobal('fetch',fetcher);
  const result=await domainReaders.activity({source_id:source,event_type:'RENAME'},new AbortController().signal);
  expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/activity?limit=50&offset=0&source_id=${source}&event_type=RENAME`);
  expect(result.availability).toBe('available');
  if(result.availability!=='available') throw Error('missing activity');
  expect(result.quality).toBe('STALE');
  expect(result.items[0]).toMatchObject({actor:null,client:null,confidence:null,
    old_path:null,new_path:'pilot\\После.txt',provenance:'NTFS_USN',path_quality:'UNAVAILABLE'});
  expect(evidenceDeadline(result)).not.toBeNull();
});

test('mapped Activity retains original absolute evidence deadline', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify(response))));
  vi.spyOn(performance,'now').mockReturnValue(1234);
  const raw=await api.activity();
  const original=evidenceDeadline(raw);
  vi.spyOn(api,'activity').mockResolvedValue(raw);
  vi.mocked(performance.now).mockReturnValue(2500);
  const mapped=await domainReaders.activity({},new AbortController().signal);
  expect(evidenceDeadline(mapped)).toBe(original);
});

test('Activity refuses unbounded pagination and fabricated actor in a successful response', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new ReadResponse(JSON.stringify({
    ...response,items:[{...response.items[0],actor:'fabricated-user'}],
  }))));
  await expect(api.activity({offset:10001})).rejects.toMatchObject({code:'INVALID_REQUEST'});
  await expect(api.activity()).rejects.toMatchObject({code:'INVALID_RESPONSE'});
});
