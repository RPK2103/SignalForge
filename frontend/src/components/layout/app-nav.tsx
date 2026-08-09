"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Readiness" },
  { href: "/briefing", label: "Executive briefing" },
  { href: "/observability", label: "Observability" },
] as const;

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="border-b border-border/70 bg-white/90"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-1 px-4 py-2">
        {LINKS.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "bg-slate-900 text-white"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-current={active ? "page" : undefined}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
