import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

interface Props {
  breadcrumb?: string[];
  children?: ReactNode;
}

export function AppShell({ breadcrumb, children }: Props) {
  return (
    <div className="flex h-screen w-full bg-background" data-component="AppShell">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar breadcrumb={breadcrumb} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
