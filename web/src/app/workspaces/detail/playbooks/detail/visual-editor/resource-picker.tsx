'use client';

import { SearchOutlined, ReloadOutlined, CheckCircleFilled } from '@ant-design/icons';
import { Input, Spin, Tag, Tooltip, Empty } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ResourceItem } from './types';

interface ResourcePickerProps {
  title?: string;
  items: ResourceItem[];
  selectedRefs: string[];
  loading: boolean;
  onRefresh: () => void;
  onToggle: (ref: string) => void;
  getRef: (item: ResourceItem) => string;
  getLabel: (item: ResourceItem) => string;
  getDescription: (item: ResourceItem) => string;
  getTag?: (item: ResourceItem) => { label: string; color: string } | null;
  icon: React.ReactNode;
  activeColor?: string;
  emptyText?: string;
}

export default function ResourcePicker({
  title,
  items,
  selectedRefs,
  loading,
  onRefresh,
  onToggle,
  getRef,
  getLabel,
  getDescription,
  getTag,
  icon,
  activeColor = 'blue',
  emptyText,
}: ResourcePickerProps) {
  const { t } = useTranslation();
  const [searchValue, setSearchValue] = useState('');

  const filteredItems = useMemo(() => {
    if (!searchValue) return items;
    const lower = searchValue.toLowerCase();
    return items.filter(
      (item) =>
        (getLabel(item) || '').toLowerCase().includes(lower) ||
        (getRef(item) || '').toLowerCase().includes(lower) ||
        (getDescription(item) || '').toLowerCase().includes(lower),
    );
  }, [items, searchValue, getLabel, getRef, getDescription]);

  const activeColorMap: Record<string, { bg: string; border: string; iconBg: string; iconColor: string }> = {
    blue: { bg: 'bg-blue-50/30', border: 'border-blue-200/80', iconBg: 'bg-blue-100', iconColor: 'text-blue-500' },
    green: { bg: 'bg-green-50/30', border: 'border-green-200/80', iconBg: 'bg-green-100', iconColor: 'text-green-500' },
    purple: { bg: 'bg-purple-50/30', border: 'border-purple-200/80', iconBg: 'bg-purple-100', iconColor: 'text-purple-500' },
    orange: { bg: 'bg-orange-50/30', border: 'border-orange-200/80', iconBg: 'bg-orange-100', iconColor: 'text-orange-500' },
    sky: { bg: 'bg-sky-50/30', border: 'border-sky-200/80', iconBg: 'bg-sky-100', iconColor: 'text-sky-500' },
    red: { bg: 'bg-red-50/30', border: 'border-red-200/80', iconBg: 'bg-red-100', iconColor: 'text-red-500' },
  };

  const active = activeColorMap[activeColor] || activeColorMap.blue;

  return (
    <div className="flex flex-col">
      {title && <div className="text-sm font-medium text-gray-700 mb-2">{title}</div>}
      <div className="flex items-center gap-2 mb-3">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder={t('builder_search_placeholder') || 'Search...'}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          allowClear
          className="rounded-lg h-9 flex-1"
        />
        <Tooltip title={t('workspaces.reload') || 'Refresh'}>
          <button
            onClick={onRefresh}
            className="w-9 h-9 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all flex-shrink-0"
          >
            <ReloadOutlined className={`text-sm ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
      </div>

      <Spin spinning={loading}>
        {filteredItems.length > 0 ? (
          <div className="grid grid-cols-1 gap-2">
            {filteredItems.map((item, idx) => {
              const ref = getRef(item);
              const isEnabled = selectedRefs.includes(ref);
              const label = getLabel(item);
              const description = getDescription(item);
              const tag = getTag ? getTag(item) : null;
              return (
                <div
                  key={`${ref}-${idx}`}
                  className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                    isEnabled
                      ? `${active.bg} ${active.border} shadow-sm`
                      : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                  }`}
                  onClick={() => onToggle(ref)}
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isEnabled ? active.iconBg : 'bg-gray-100'
                      }`}
                    >
                      <span className={`text-sm ${isEnabled ? active.iconColor : 'text-gray-400'}`}>
                        {icon}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium text-gray-700 truncate">{label}</span>
                        {tag && (
                          <Tag
                            className="mr-0 text-[10px] rounded-md border-0 font-medium px-1.5"
                            color={tag.color}
                          >
                            {tag.label}
                          </Tag>
                        )}
                      </div>
                      <div className="text-[11px] text-gray-400 truncate mt-0.5">
                        {description || '--'}
                      </div>
                    </div>
                  </div>
                  {isEnabled && (
                    <CheckCircleFilled className="text-blue-500 text-base ml-2 flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          !loading && (
            <div className="flex justify-center py-12">
              <Empty description={emptyText || t('builder_no_items') || 'No items found'} />
            </div>
          )
        )}
      </Spin>
    </div>
  );
}
