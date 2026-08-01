'use client';

import type { ComponentType } from 'react';
import TabDatabase from './tab-database';
import TabEcp from './tab-ecp';
import TabKnowledge from './tab-knowledge';

export interface AssetPickerEntry {
  /** Catalog type keys (and storage discriminators) this picker handles. */
  keys: string[];
  /** i18n key for the section heading. */
  labelKey: string;
  /** Self-contained picker: reads AppContext, writes its own storage slice. */
  Component: ComponentType;
}

/**
 * Known data-flavored resource pickers. Rendered by the Assets tab when the
 * corresponding type appears in the resource-type catalog
 * (GET /api/v1/resource-type/list), which DB / ECP / knowledge all do.
 *
 * Storage mapping (unchanged from the former per-type tabs):
 *  - DB        -> appInfo.resource_tool, type "datasource"
 *  - ECP       -> appInfo.resource_tool, type "ecp"
 *  - Knowledge -> appInfo.resource_knowledge, type "knowledge_pack"
 */
export const ASSET_PICKERS: AssetPickerEntry[] = [
  { keys: ['datasource', 'database'], labelKey: 'assets_section_database', Component: TabDatabase },
  { keys: ['ecp'], labelKey: 'assets_section_ecp', Component: TabEcp },
  { keys: ['knowledge_pack', 'knowledge'], labelKey: 'assets_section_knowledge', Component: TabKnowledge },
];

/**
 * Resource types that have their own tab or are tool/skill-flavored -> never
 * shown in the Assets tab. Future data-flavored types are NOT listed here, so
 * they show up automatically (via the read-only fallback) without frontend
 * changes.
 */
export const ASSET_DENYLIST = new Set<string>([
  'tool',
  'tool(local_v2)',
  'skill',
  'skill(derisk)',
  'agent_skill',
  'reasoning_engine',
  'memory',
  'agent',
  'app',
  'workflow',
  'pack',
  'open_rca_scene',
  'internet',
  'text_file',
  'excel_file',
  'image_file',
  'common_file',
  'plugin',
  'awel_flow',
  'report',
  'document',
  'code_wiki',
  'monitor',
  'yuque',
]);

export function findPicker(key: string): AssetPickerEntry | undefined {
  return ASSET_PICKERS.find(p => p.keys.includes(key));
}

export function isDenylisted(key: string): boolean {
  return ASSET_DENYLIST.has(key);
}
