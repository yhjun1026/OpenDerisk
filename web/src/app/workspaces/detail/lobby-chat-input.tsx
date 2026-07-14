'use client';

import React, { useState } from 'react';
import { Input, Button } from 'antd';

interface LobbyChatInputProps {
  placeholder?: string;
  onSend: (text: string) => void;
}

export function LobbyChatInput({ placeholder = '发起新任务...', onSend }: LobbyChatInputProps) {
  const [value, setValue] = useState('');

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue('');
  };

  return (
    <div className="lobby-chat-input">
      <Input
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onPressEnter={handleSend}
        suffix={
          <Button
            type="primary"
            size="small"
            disabled={!value.trim()}
            onClick={handleSend}
          >
            发送
          </Button>
        }
      />
    </div>
  );
}

export default LobbyChatInput;