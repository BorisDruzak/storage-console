import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { DomainFilters, DomainLoader } from '../domains/models';
import type { Section } from '../navigation';
import { DomainFilter, useDomainFilters } from './DomainFilter';
import { DomainState } from './DomainState';
import { ReadState } from './ReadState';

export function DomainPanel<T>({section,load,filters:extra,children}: {
  section:Section;load:DomainLoader<T>;filters?:DomainFilters;
  children:(items:T[],current:boolean)=>ReactNode;
}) {
  const base=useDomainFilters();
  const filters={source_id:base.source_id,...extra};
  const query=useQuery({queryKey:[section,filters],queryFn:({signal})=>load(filters,signal),retry:false});
  const data=query.data;
  const items=data?.availability==='available'?data.items:[];
  const retainedValues:Record<string,string>=extra?.category?{category:extra.category}:{};
  return <><DomainFilter key={section} section={section} retainedValues={retainedValues} />
    <ReadState query={query}><DomainState data={data}>
      {children(items,data?.availability==='available'&&data.quality==='CURRENT')}
    </DomainState></ReadState>
  </>;
}
