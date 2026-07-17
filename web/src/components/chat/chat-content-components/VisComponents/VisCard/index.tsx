import React, { FC } from 'react';
import { VisCardStyles } from './style';

/**
 * VisCard — VIS 组件渲染的固定容器。
 *
 * 给每个 vis 代码块(manus-left-panel 等)的渲染产物套一层 VisCardStyles,
 * 统一收敛 react-markdown 原生元素的 margin/防溢出,保证各 vis 组件间距一致。
 * 仅做容器包裹,不重新解析 markdown——调用方传入的是已渲染好的 React 节点。
 */
const VisCard: FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => {
  return (
    <VisCardStyles className={className ? `VisWrapClass ${className}` : 'VisWrapClass'}>
      {children}
    </VisCardStyles>
  );
};

export default VisCard;