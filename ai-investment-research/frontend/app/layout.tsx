import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 投資研究",
  description: "個人使用的 AI 投資研究網站（台股、美股、國際總經）",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
