import { type ReactNode } from "react";
import { TopNav } from "./TopNav";
import { SideNav } from "./SideNav";
import { TopNavMobile, TabBar } from "./TopNavMobile";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      {/* Desktop */}
      <div id="top" className="hidden md:flex flex-col min-h-screen">
        <TopNav />
        <div className="flex flex-1" style={{ height: "calc(100vh - 56px)" }}>
          <SideNav />
          <main className="flex-1 overflow-y-auto px-12 py-9 pb-20">{children}</main>
        </div>
      </div>

      {/* Mobile */}
      <div id="top-mobile" className="md:hidden min-h-screen pb-[var(--tabbar-h-mobile)]">
        <TopNavMobile />
        <main className="px-4 py-5">{children}</main>
        <TabBar />
      </div>
    </>
  );
}
