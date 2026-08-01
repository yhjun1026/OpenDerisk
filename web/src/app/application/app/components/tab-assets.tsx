'use client';

import { apiInterceptors, getResourceType } from '@/client/api';
import { AppContext } from '@/contexts';
import { RightOutlined } from '@ant-design/icons';
import { Spin } from 'antd';
import { useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { findPicker, isDenylisted } from './asset-pickers';
import ReadOnlyAssetSection from './read-only-asset-section';

/**
 * Unified Assets tab. Replaces the former per-type database / ecp / knowledge
 * tabs with a single, catalog-driven surface:
 *  - fetches the resource-type catalog (GET /api/v1/resource-type/list),
 *  - renders a dedicated picker for each type that has one (DB / ECP / Knowledge),
 *  - renders a read-only fallback for any other non-denylisted type, so new
 *    backend resource types appear here without frontend changes.
 *
 * Sections with bound assets sort first; empty picker sections collapse to a
 * header row (click to expand); empty read-only fallbacks are not rendered.
 *
 * Storage is untouched: each picker reads/writes the same fields as before
 * (resource_tool for datasource/ecp, resource_knowledge for knowledge_pack).
 */
export default function TabAssets() {
  const { t } = useTranslation();
  const { appInfo } = useContext(AppContext);
  const [catalogTypes, setCatalogTypes] = useState<string[] | null>(null);
  // Empty picker sections the user manually expanded (sections with bound
  // assets are always expanded).
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [, res] = await apiInterceptors(getResourceType());
      if (!cancelled) {
        setCatalogTypes(Array.isArray(res) ? res : []);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Bound-entry count per resource type, from the backend-merged all_resources
  // (same source and fallback as ReadOnlyAssetSection).
  const boundCounts = useMemo(() => {
    const all: any[] = appInfo?.all_resources ?? [
      ...(appInfo?.resource_tool ?? []),
      ...(appInfo?.resource_knowledge ?? []),
      ...(appInfo?.resources ?? []),
      ...(appInfo?.resource_agent ?? []),
      ...(appInfo?.resource_memory ?? []),
    ];
    const counts = new Map<string, number>();
    for (const r of all) {
      if (r?.type) counts.set(r.type, (counts.get(r.type) ?? 0) + 1);
    }
    return counts;
  }, [appInfo]);

  // Catalog-driven section list: denylisted types are excluded; the rest get a
  // picker if one is registered, otherwise a read-only fallback. Sections with
  // bound assets sort first (stable within each group); empty read-only
  // fallbacks carry no information and are dropped.
  const sections = useMemo(() => {
    if (catalogTypes === null) return null;
    return catalogTypes
      .filter(key => !isDenylisted(key))
      .map(key => {
        const picker = findPicker(key);
        const count = (picker ? picker.keys : [key]).reduce(
          (sum, k) => sum + (boundCounts.get(k) ?? 0),
          0,
        );
        return { key, picker, count };
      })
      .filter(s => s.picker || s.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [catalogTypes, boundCounts]);

  const toggleExpand = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (sections === null) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto custom-scrollbar">
      <div className="p-5 space-y-4">
        {sections.length === 0 ? (
          <div className="text-center py-12 text-gray-300 text-xs">
            {t('builder_no_items')}
          </div>
        ) : (
          sections.map(({ key, picker, count }) => {
            if (picker) {
              const Picker = picker.Component;
              const sectionKey = picker.keys[0];
              const expanded = count > 0 || expandedKeys.has(sectionKey);
              const collapsible = count === 0;
              return (
                <section
                  key={sectionKey}
                  className="rounded-xl border border-gray-100 overflow-hidden flex flex-col max-h-[440px] bg-white/60"
                >
                  <div
                    className={`px-5 py-2.5 bg-gray-50/50 flex items-center gap-2 ${
                      expanded ? 'border-b border-gray-100/60' : ''
                    } ${collapsible ? 'cursor-pointer hover:bg-gray-100/50' : ''}`}
                    onClick={collapsible ? () => toggleExpand(sectionKey) : undefined}
                  >
                    <span className="text-[13px] font-semibold text-gray-700 flex-1">
                      {t(picker.labelKey as any)}
                    </span>
                    {collapsible && (
                      <RightOutlined
                        className={`text-[10px] text-gray-300 transition-transform ${expanded ? 'rotate-90' : ''}`}
                      />
                    )}
                  </div>
                  {expanded && (
                    <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                      <Picker />
                    </div>
                  )}
                </section>
              );
            }
            return <ReadOnlyAssetSection key={key} typeKey={key} />;
          })
        )}
      </div>
    </div>
  );
}
