"use client";
import { ChatContext, ChatContextProvider } from "@/contexts";
import { InteractionProvider } from "@/components/interaction";
import SideBar from "@/components/layout/side-bar";
import TopHeader from "@/components/layout/top-header";
import CommandPalette from "@/components/layout/command-palette";
import {
  STORAGE_LANG_KEY,
  STORAGE_USERINFO_KEY,
  STORAGE_USERINFO_VALID_TIME_KEY,
} from "@/utils/constants/index";
import { App, ConfigProvider, MappingAlgorithm, Spin, theme } from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import Head from "next/head";
import React, { useContext, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { usePathname, useSearchParams } from "next/navigation";
import "./i18n";
import "../styles/globals.css";
import { Suspense } from 'react'
import { authService } from "@/services/auth";

// Prevent SSR flash
const EmptyLayout = ({ children }: { children: React.ReactNode }) => <>{children}</>;

// 全局 AntD 主题 —— 与 src/styles/globals.css 设计 token 对齐
const antdTheme = {
  token: {
    colorPrimary: "#4f46e5",
    colorInfo: "#4f46e5",
    colorSuccess: "#22c55e",
    colorWarning: "#f59e0b",
    colorError: "#ef4444",
    colorText: "#14161c",
    colorTextSecondary: "#5d6577",
    colorTextTertiary: "#8a92a6",
    colorBorder: "#e5e8ef",
    colorBorderSecondary: "#eff1f6",
    colorFillSecondary: "#f2f4f8",
    colorBgLayout: "#f7f8fa",
    borderRadius: 8,
    borderRadiusSM: 6,
    borderRadiusLG: 12,
    fontSize: 13,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif',
    boxShadowTertiary: "0 1px 2px rgba(16, 24, 40, 0.04)",
    boxShadowSecondary: "0 4px 16px rgba(16, 24, 40, 0.08)",
    boxShadow: "0 12px 40px rgba(16, 24, 40, 0.12)",
    controlHeight: 34,
  },
  components: {
    Button: { fontWeight: 500, primaryShadow: "none" },
    Card: { boxShadowTertiary: "0 1px 2px rgba(16, 24, 40, 0.04)" },
    Menu: { itemBorderRadius: 8 },
    Input: { activeShadow: "0 0 0 3px rgba(79, 70, 229, 0.08)" },
  },
};

const antdDarkTheme: MappingAlgorithm = (seedToken, mapToken) => {
  return {
    ...theme.darkAlgorithm(seedToken, mapToken),
    colorBgBase: "#232734",
    colorBorder: "#828282",
    colorBgContainer: "#232734",
  };
};

function CssWrapper({ children }: { children: React.ReactElement }) {
  const { mode } = useContext(ChatContext);
  const { i18n } = useTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mode) {
      document.body?.classList?.add(mode);
      if (mode === "light") {
        document.body?.classList?.remove("dark");
      } else {
        document.body?.classList?.remove("light");
      }
    }
  }, [mode]);

  useEffect(() => {
    if (mounted) {
      i18n.changeLanguage?.(
        window.localStorage.getItem(STORAGE_LANG_KEY) || "zh"
      );
    }
  }, [i18n, mounted]);

  if (!mounted) return <>{children}</>;

  return <div className="h-screen overflow-hidden">{children}</div>;
}

function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const { mode } = useContext(ChatContext);
  const { i18n } = useTranslation();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const authCheckInProgress = useRef(false);

  const isPublicRoute = pathname?.startsWith("/login") || pathname?.startsWith("/auth/callback");

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || isPublicRoute || authCheckInProgress.current) return;

    const checkAuth = async () => {
      authCheckInProgress.current = true;
      try {
        const me = await authService.getMe();
        const user = {
          user_channel: me.user_channel,
          user_no: me.user_no,
          nick_name: me.nick_name,
          avatar_url: me.avatar_url || me.user?.avatar || '',
          email: me.email || me.user?.email || '',
          role: me.role || 'normal',
        };
        localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(user));
        localStorage.setItem(STORAGE_USERINFO_VALID_TIME_KEY, Date.now().toString());
        window.dispatchEvent(new Event('userinfochanged'));
        setAuthChecked(true);
      } catch {
        localStorage.removeItem(STORAGE_USERINFO_KEY);
        localStorage.removeItem(STORAGE_USERINFO_VALID_TIME_KEY);
        const currentPath = window.location.pathname;
        if (!currentPath.startsWith("/login") && !currentPath.startsWith("/auth/callback")) {
          const next = encodeURIComponent(currentPath + window.location.search);
          window.location.href = `/login?next=${next}`;
        }
      } finally {
        authCheckInProgress.current = false;
      }
    };
    checkAuth();
  }, [mounted, isPublicRoute]);

  // 公开页面：直接渲染（无侧边栏）
  if (isPublicRoute) {
    return (
      <ConfigProvider
        locale={i18n.language === "en" ? enUS : zhCN}
        theme={{ ...antdTheme, algorithm: undefined }}
      >
        <App>{children}</App>
      </ConfigProvider>
    );
  }

  if (!authChecked) {
    return (
      <ConfigProvider
        locale={i18n.language === "en" ? enUS : zhCN}
        theme={{ ...antdTheme, algorithm: undefined }}
      >
        <App className="w-screen h-screen flex items-center justify-center">
          <Spin />
        </App>
      </ConfigProvider>
    );
  }

  const renderContent = () => {
    return (
      <div className="flex w-screen h-screen overflow-hidden">
        <Head>
          <meta
            name="viewport"
            content="initial-scale=1.0, width=device-width, maximum-scale=1"
          />
        </Head>
        <div className="transition-[width] duration-300 ease-in-out h-full flex flex-col">
          <SideBar />
        </div>
        <div className="flex flex-col flex-1 overflow-hidden">
          {children}
        </div>
        <CommandPalette />
      </div>
    );
  };

  return (
    <ConfigProvider
      locale={i18n.language === "en" ? enUS : zhCN}
      theme={{
        ...antdTheme,
        algorithm: mode === "dark" ? theme.darkAlgorithm : undefined,
      }}
    >
      <App>{renderContent()}</App>
    </ConfigProvider>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning data-theme="light" className="light">
      <body suppressHydrationWarning={true} className="bg-surface-page dark:bg-[#111]">
        <Suspense fallback={
          <App className="w-screen h-screen flex items-center justify-center">
            <Spin />
          </App>
          }>
          <ChatContextProvider>
            <InteractionProvider autoConnect={false}>
              <CssWrapper>
                <LayoutWrapper>{children}</LayoutWrapper>
              </CssWrapper>
            </InteractionProvider>
          </ChatContextProvider>
        </Suspense>
      </body>
    </html>
  );
}
