import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

interface Props {
  children: ReactNode;
  breadcrumb?: string;
}

export function AppShell({ children, breadcrumb }: Props) {
  return (
    <div className="flex h-screen w-full bg-[color:var(--background)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar breadcrumb={breadcrumb} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
