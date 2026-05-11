export function TopNavMobile({ title = "工作台" }: { title?: string }) {
  return (
    <header className="sticky top-0 z-[200] flex items-center justify-between h-[var(--nav-h-mobile)] px-4 bg-paper border-b border-rule">
      <button className="w-10 h-10 grid place-items-center text-ink-2">☰</button>
      <div className="flex items-center gap-2 font-wenkai text-h3">
        <img src="/chick-happy.svg" alt="小纸笺" className="h-7 w-7 rounded-xs shadow-xs" />
        <span>{title}</span>
      </div>
      <span
        className="h-8 px-3 rounded-pill bg-success border border-success inline-flex items-center text-micro font-semibold text-white shadow-xs"
      >
        内测
      </span>
    </header>
  );
}

const tabs = [
  { label: "工作台", active: true },
  { label: "周计划" },
  { label: "记录" },
  { label: "模板" },
  { label: "我的" },
];

export function TabBar() {
  return (
    <nav
      className="fixed left-0 right-0 bottom-0 flex z-[200] border-t border-rule backdrop-blur"
      style={{
        height: "calc(var(--tabbar-h-mobile) + env(safe-area-inset-bottom))",
        paddingBottom: "env(safe-area-inset-bottom)",
        background: "color-mix(in oklch, var(--color-paper), var(--color-white) 40%)",
      }}
    >
      {tabs.map((t) => (
        <a
          key={t.label}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-micro ${
            t.active ? "text-brand" : "text-ink-3"
          }`}
        >
          <span className={`w-[22px] h-[22px] rounded-full ${t.active ? "bg-brand" : "bg-ink-4"}`} />
          {t.label}
        </a>
      ))}
    </nav>
  );
}
