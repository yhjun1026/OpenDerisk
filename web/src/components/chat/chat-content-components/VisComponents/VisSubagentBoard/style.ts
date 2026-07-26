import styled from 'styled-components';

export const VisSubagentBoardWrap = styled.div`
  width: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  background-color: #fff;
  border: 1px solid #e8e8e8;
  overflow: hidden;
  margin: 4px 0;

  .board-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-bottom: 1px solid #f0f0f0;
    cursor: pointer;

    .header-left {
      display: flex;
      align-items: center;
      gap: 8px;

      .header-icon {
        font-size: 14px;
        color: #8c8c8c;
      }

      .header-title {
        font-size: 14px;
        font-weight: 500;
        color: #262626;
      }

      .header-progress {
        font-size: 13px;
        color: #8c8c8c;
      }

      .header-auth-badge {
        font-size: 12px;
        color: #f59e0b;
        background: #fffbeb;
        padding: 1px 6px;
        border-radius: 4px;
        border: 1px solid #fde68a;
      }
    }

    .header-expand {
      font-size: 12px;
      color: #bfbfbf;

      &:hover {
        color: #8c8c8c;
      }
    }
  }

  .board-items {
    display: flex;
    flex-direction: column;
    padding: 8px 0;

    .subagent-item {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 8px 12px;
      cursor: pointer;
      transition: background-color 0.15s ease;
      border-left: 3px solid transparent;

      &.running {
        background-color: #f5f3ff;
        border-left-color: #4f46e5;
      }

      &.failed {
        background-color: #fef2f2;
        border-left-color: #ef4444;
      }

      &.done {
        background-color: #f0fdf4;
        border-left-color: #52c41a;
      }

      &.awaiting_authorization {
        background-color: #fffbeb;
        border-left-color: #f59e0b;
      }

      &:hover {
        background-color: #fafafa;
      }

      .status-icon {
        flex-shrink: 0;
        width: 18px;
        height: 18px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 1px;

        .spinner {
          width: 12px;
          height: 12px;
          border: 1.5px solid #4f46e5;
          border-top-color: transparent;
          border-radius: 50%;
          display: inline-block;
          animation: subagent-spin 0.8s linear infinite;
        }

        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .dot.pending {
          background: #d9d9d9;
        }

        .dot.done {
          background: #52c41a;
        }

        .dot.failed {
          background: #ef4444;
        }

        .dot.awaiting {
          background: #f59e0b;
        }
      }

      .item-content {
        flex: 1;
        min-width: 0;

        .item-title {
          font-size: 14px;
          color: #262626;
          line-height: 20px;
          font-weight: 500;

          &.done {
            color: #8c8c8c;
          }

          &.failed {
            color: #ef4444;
            text-decoration: line-through;
          }
        }

        .item-task {
          font-size: 12px;
          color: #8c8c8c;
          line-height: 16px;
          margin-top: 2px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .item-auth {
          font-size: 12px;
          color: #f59e0b;
          margin-top: 2px;
        }
      }

      .item-status-badge {
        flex-shrink: 0;
        font-size: 11px;
        padding: 1px 6px;
        border-radius: 4px;
        margin-top: 1px;

        &.running {
          color: #4f46e5;
          background: #eef2ff;
        }

        &.done {
          color: #52c41a;
          background: #f0fdf4;
        }

        &.failed {
          color: #ef4444;
          background: #fef2f2;
        }

        &.pending {
          color: #8c8c8c;
          background: #f5f5f5;
        }

        &.awaiting_authorization {
          color: #f59e0b;
          background: #fffbeb;
        }
      }
    }

    .board-empty {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px 12px;
      color: #bfbfbf;
      font-size: 13px;
    }
  }

  @keyframes subagent-spin {
    to {
      transform: rotate(360deg);
    }
  }
`;
