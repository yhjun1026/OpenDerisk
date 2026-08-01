'use client';

import { AppContext } from '@/contexts';
import { InfoCircleOutlined } from '@ant-design/icons';
import { Tag } from 'antd';
import { useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  typeKey: string;
}

/**
 * Minimal read-only fallback for resource types without a dedicated picker.
 * Lists currently-bound entries of the type from `all_resources` (the merge the
 * backend returns on load). Cannot edit in-UI; a picker can be added later.
 */
export default function ReadOnlyAssetSection({ typeKey }: Props) {
  const { t } = useTranslation();
  const { appInfo } = useContext(AppContext);

  const boundEntries = useMemo(() => {
    // Prefer the backend-merged all_resources; fall back to scanning the
    // denormalized fields in case the info response omits all_resources.
    const all: any[] = appInfo?.all_resources ?? [
      ...(appInfo?.resource_tool ?? []),
      ...(appInfo?.resource_knowledge ?? []),
      ...(appInfo?.resources ?? []),
      ...(appInfo?.resource_agent ?? []),
      ...(appInfo?.resource_memory ?? []),
    ];
    return all.filter(r => r?.type === typeKey);
  }, [appInfo, typeKey]);

  return (
    <section className="rounded-xl border border-gray-100 overflow-hidden flex flex-col">
      <div className="px-5 py-2.5 border-b border-gray-100/60 bg-gray-50/50 flex items-center gap-2">
        <span className="text-[13px] font-semibold text-gray-700">{typeKey}</span>
        <Tag className="m-0 text-[10px] border-0 bg-gray-100 text-gray-400 rounded px-1.5 leading-5">
          {t('assets_read_only')}
        </Tag>
      </div>
      <div className="px-5 py-3">
        <div className="flex items-start gap-2 text-[12px] text-gray-400 mb-2">
          <InfoCircleOutlined className="text-[12px] mt-0.5 flex-shrink-0" />
          <span>{t('assets_section_no_picker')}</span>
        </div>
        {boundEntries.length > 0 ? (
          <div className="space-y-1.5">
            {boundEntries.map((r, idx) => (
              <div
                key={`${typeKey}-${idx}`}
                className="flex items-center gap-2 p-2 rounded-lg border border-gray-100/80 bg-gray-50/20"
              >
                <Tag className="m-0 text-[10px] border-0 bg-gray-100 text-gray-500 rounded px-1.5 leading-5">
                  {r?.type}
                </Tag>
                <span className="text-[12px] text-gray-600 truncate">
                  {r?.name || r?.value || '--'}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-gray-300 py-2">{t('builder_no_items')}</div>
        )}
      </div>
    </section>
  );
}
