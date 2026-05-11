import { workbenchData } from "@/lib/workbench-data";

export function QuickActions() {
  const handleClick = (id: string) => {
    if (id === "recent") {
      document.getElementById("recent-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (id === "knowledge") {
      window.dispatchEvent(new CustomEvent("sidenav:open", { detail: "knowledge" }));
      return;
    }
    if (id === "theme") {
      window.dispatchEvent(new CustomEvent("sidenav:open", { detail: "weekly" }));
    }
  };

  return (
    <section className="pb-9">
      <div className="flex gap-2 overflow-x-auto md:overflow-visible -mx-4 px-4 md:mx-0 md:px-0"
           style={{ scrollSnapType: "x mandatory" }}>
        {workbenchData.quick.map((q) => (
          <button
            key={q.id}
            type="button"
            onClick={() => handleClick(q.id)}
            className="shrink-0 md:shrink h-10 px-5 rounded-pill bg-paper-hi border border-rule text-body-sm text-ink hover:bg-paper-sunk whitespace-nowrap"
            style={{ scrollSnapAlign: "start" }}
          >
            {q.label}
          </button>
        ))}
      </div>
    </section>
  );
}
