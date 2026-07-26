import styled from 'styled-components';

export const VisTodoListWrap = styled.div`
  width: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  background-color: #fff;
  border: 1px solid #e8e8e8;
  overflow: hidden;
  margin: 4px 0;

  .todolist-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-bottom: 1px solid #f0f0f0;

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
    }

    .header-expand {
      font-size: 12px;
      color: #bfbfbf;
      cursor: pointer;
      transform: rotate(180deg);
      
      &:hover {
        color: #8c8c8c;
      }
    }
  }

  .todolist-items {
    display: flex;
    flex-direction: column;
    padding: 8px 0;

    .todo-item {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 8px 12px;
      cursor: default;
      transition: background-color 0.15s ease;
      border-left: 3px solid transparent;

      &.working {
        background-color: #f5f3ff;
        border-left-color: #4f46e5;
      }

      &.failed {
        background-color: #fef2f2;
        border-left-color: #ef4444;
      }

      &:hover {
        background-color: #fafafa;
      }

      .todo-checkbox {
        flex-shrink: 0;
        width: 18px;
        height: 18px;
        border: 1.5px solid #d9d9d9;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 1px;
        transition: all 0.2s ease;

        &.checked {
          background-color: #52c41a;
          border-color: #52c41a;

          .checkmark {
            color: #fff;
            font-size: 12px;
            font-weight: bold;
          }
        }

        &.working {
          border-color: #4f46e5;

          .spinner {
            width: 10px;
            height: 10px;
            border: 1.5px solid #4f46e5;
            border-top-color: transparent;
            border-radius: 50%;
            display: inline-block;
            animation: todo-spin 0.8s linear infinite;
          }
        }

        &.failed {
          background-color: #ef4444;
          border-color: #ef4444;

          .checkmark {
            color: #fff;
            font-size: 12px;
            font-weight: bold;
          }
        }
      }

      .todo-title {
        flex: 1;
        font-size: 14px;
        color: #262626;
        line-height: 20px;
        word-break: break-word;

        &.completed {
          color: #8c8c8c;
          text-decoration: line-through;
        }

        &.failed {
          color: #ef4444;
          text-decoration: line-through;
        }
      }
    }

    .todolist-empty {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px 12px;
      color: #bfbfbf;
      font-size: 13px;
    }
  }

  @keyframes todo-spin {
    to {
      transform: rotate(360deg);
    }
  }
`;
