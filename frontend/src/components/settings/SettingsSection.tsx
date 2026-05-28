import type { ReactNode } from "react";

type Props = {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export default function SettingsSection({ title, description, action, children }: Props) {
  return (
    <section className="ledger-fade-in">
      <header className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-[1.2rem] text-ink-50 tracking-tight2">{title}</h2>
          {description && <p className="mt-1 text-[13px] text-ink-300">{description}</p>}
        </div>
        {action}
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}
