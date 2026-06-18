"use client";

import { createContext, useContext, useMemo } from "react";

type Ctx = {
  jumpToSnap: (id: string) => void;
  activeSnapId: string;
};

export const CompetitorScrollContext = createContext<Ctx>({
  jumpToSnap: (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  },
  activeSnapId: "sec-01-a",
});

export function CompetitorScrollProvider({
  jumpToSnap,
  activeSnapId,
  children,
}: {
  jumpToSnap: (id: string) => void;
  activeSnapId: string;
  children: React.ReactNode;
}) {
  const value = useMemo(() => ({ jumpToSnap, activeSnapId }), [jumpToSnap, activeSnapId]);
  return <CompetitorScrollContext.Provider value={value}>{children}</CompetitorScrollContext.Provider>;
}

export function useCompetitorScroll() {
  return useContext(CompetitorScrollContext);
}
