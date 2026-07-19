/** @type {import("jest").Config }**/
module.exports = {
  testEnvironment: "node",
  preset: "ts-jest",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testMatch: [
    "<rootDir>/src/**/__tests__/**/*.test.ts",
    "<rootDir>/src/**/__tests__/**/*.test.tsx",
  ],
  // Project tsconfig uses jsx: "preserve"; override to react-jsx so ts-jest can
  // transpile .tsx React tests into executable JS under Node/jsdom.
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { tsconfig: { jsx: "react-jsx" } }],
    // unified/remark 生态是纯 ESM,用第二个 ts-jest 实例转译这些 node_modules .js
    "^.+/node_modules/(unified|remark-.*|mdast-.*|micromark.*|unist-.*|vfile.*|bail|trough|devlop|zwitch|html-void-elements|stringify-entities|character-entities.*|ccount|comma-separated-tokens|space-separated-tokens|hast-.*|property-information|web-namespaces|decode-named-character-reference|longest-streak|markdown-table|trim-lines|escape-string-regexp|is-plain-obj|extend|html-url-attributes|url-join)/.+\\.js$":
      ["ts-jest", { tsconfig: { allowJs: true, jsx: "react-jsx" } }],
  },
  // unified/remark 生态是纯 ESM,允许 ts-jest 转译这些依赖
  transformIgnorePatterns: [
    "/node_modules/(?!(unified|remark-.*|mdast-.*|micromark.*|unist-.*|vfile.*|bail|trough|devlop|zwitch|html-void-elements|stringify-entities|character-entities.*|ccount|comma-separated-tokens|space-separated-tokens|hast-.*|property-information|web-namespaces|decode-named-character-reference|longest-streak|markdown-table|trim-lines|escape-string-regexp|is-plain-obj|extend|html-url-attributes|url-join)/)",
  ],
  // Registers @testing-library/jest-dom matchers (toBeInTheDocument, …) for
  // React component tests that run under the jsdom environment.
  setupFilesAfterEnv: ["<rootDir>/src/test-setup.ts"],
};