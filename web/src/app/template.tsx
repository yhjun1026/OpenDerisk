'use client';

/**
 * 路由切换转场:每次导航重新挂载并播放轻微浮起淡入。
 * 保持极短(0.3s)避免拖慢操作节奏。
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <div
      className='flex flex-col h-full w-full min-h-0 animate-rise'
      style={{ animationDuration: '0.3s', animationTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' }}
    >
      {children}
    </div>
  );
}
