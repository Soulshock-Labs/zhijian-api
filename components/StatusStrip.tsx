import { workbenchData } from "@/lib/workbench-data";

export function StatusStrip() {
  const { status } = workbenchData;
  const items = [
    { label: "知识库", value: status.kb },
    { label: "会员",   value: status.member },
    { label: "连续",   value: status.streak },
  ];
  return (
    <section className="pt-5 mt-5 border-t border-dashed border-rule-soft">
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-8 text-meta">
        {items.map((it) => (
          <div key={it.label} className="text-ink-2">
            <span className="font-mono text-ink-3 mr-2">{it.label}</span>
            {it.value}
          </div>
        ))}
      </div>
    </section>
  );
}
