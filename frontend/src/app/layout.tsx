import "./globals.css";
import type { Metadata } from "next";

import { AppProviders } from "@/components/AppProviders";

export const metadata: Metadata = {
  title: "成电吃什么 Agent",
  description: "电子科技大学校园餐饮推荐 MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}

