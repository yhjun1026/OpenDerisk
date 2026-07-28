import styled from 'styled-components';

/**
 * VisContentCardWrap — agent 叙述文本(step_thought / 阶段回复)。
 * 纯排版、无气泡材质:叙述与步骤条(chip)交错时,
 * 逐段 shrink-to-fit 的灰底会造成长短不一的参差色块。
 */
export const VisContentCardWrap = styled.div`
  width: 100%;
  min-width: 100px;
  white-space: normal;
  padding: 2px 0;
  background: transparent;
`;
