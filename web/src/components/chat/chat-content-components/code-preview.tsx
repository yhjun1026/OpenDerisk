import { ChatContext } from '@/contexts';
import { CSSProperties, useContext } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { coldarkDark, oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface Props {
  code: string;
  language: string;
  customStyle?: CSSProperties;
  light?: { [key: string]: CSSProperties };
  dark?: { [key: string]: CSSProperties };
}

export function CodePreview({ code, light, dark, language, customStyle }: Props) {
  const { mode } = useContext(ChatContext);

  return (
    <div>
      {/* @ts-ignore */}
      <SyntaxHighlighter
        customStyle={customStyle}
        language={language}
        style={mode === 'dark' ? (dark ?? coldarkDark) : (light ?? oneLight)}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
