import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "小纸笺 · 工作台",
  description: "幼师的智能工作台",
  icons: {
    icon: [
      { url: "/favicon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/favicon.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon.ico", sizes: "any" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
