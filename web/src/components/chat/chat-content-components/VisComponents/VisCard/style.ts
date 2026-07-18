import styled from 'styled-components';

/**
 * VisCardStyles — VIS 渲染的固定容器。
 *
 * 背景:本项目 globals.css 未引入 tailwind preflight,react-markdown 产出的原生
 * p / pre / heading / ul 走浏览器默认 margin,导致 vis 代码块(如 manus-left-panel)之间出现
 * 大段空白。参考项目 nex-main 用一份 VisCardStyles 包裹每个 vis 代码块并做全面 reset。
 *
 * 这里只保留"治间距/防溢出"的必要规则——Tailwind 工具类(如 space-y、gap 系列)仍由全局
 * Tailwind 引擎按扫描结果生成并作用到容器内,无需在此重复声明,避免冲突。
 */
export const VisCardStyles = styled.div`
  /* stylelint-disable */
  /* 全局防溢出:VIS 渲染出的块级后代最大宽度不超过容器,超宽内容走各自已有的内部滚动,
     而非被上方 overflow 切除右侧。box-sizing:border-box 保证 padding/border 不撑破 100%。 */
  max-width: 100%;
  overflow-x: hidden;
  word-break: break-word;

  &,
  & > *,
  & div,
  & section,
  & article,
  & header,
  & footer,
  & ul,
  & ol,
  & li,
  & table {
    max-width: 100%;
    box-sizing: border-box;
  }

  /* react-markdown 把每个自定义代码块(manus-left-panel 等)外层套一个 <pre>。
     让其内联、去 padding/background,避免块级 <pre> 默认间距撑出空白 —— 对齐参考项目
     :where(pre){display:inline;padding-left:0} 的效果。
     注意:markdown 包裹层的 <pre> 是不带 class 的原生节点;组件内部自己渲染的 <pre>
     (如 SqlQueryRenderer/TerminalRenderer 的代码块)都带有 Tailwind class。
     用 :not([class]) 把 reset 限定在前者,避免把组件内的代码块 <pre> 打成 inline
     (inline pre 的 background/padding 会按行片段绘制,造成行与行互相遮挡)。 */
  :where(pre):not([class]) {
    display: inline;
    padding-left: 0;
    margin: 0;
    background: transparent;
    font-size: 1em;
  }

  pre:has(.approval-summary) {
    display: block;
    margin: 0;
  }

  /* 块级元素默认 margin 归零(浏览器默认 <p> 1em、<h*> 较大 margin 是空白主因)。 */
  :where(blockquote),
  :where(dl),
  :where(dd),
  :where(h1),
  :where(h2),
  :where(h3),
  :where(h4),
  :where(h5),
  :where(h6),
  :where(hr),
  :where(figure),
  :where(p),
  :where(pre) {
    margin: 0;
  }

  :where(ol),
  :where(ul),
  :where(menu) {
    margin: 0;
    padding: 0;
  }

  :where(h1),
  :where(h2),
  :where(h3),
  :where(h4),
  :where(h5),
  :where(h6) {
    font-size: inherit;
    font-weight: inherit;
  }

  :where(a) {
    color: inherit;
    text-decoration: inherit;
  }

  :where(img),
  :where(video) {
    max-width: 100%;
    height: auto;
  }
`;