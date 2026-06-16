"use client";

import { createContext, useContext, useMemo } from "react";

type Ctx = {
  jumpToSnap: (id: string) => void;
};

export const CompetitorScrollContext = createContext<Ctx>({
  jumpToSnap: (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  },
});

export function CompetitorScrollProvider({
  jumpToSnap,
  children,
}: {
  jumpToSnap: (id: string) => void;
  children: React.ReactNode;
}) {
  const value = useMemo(() => ({ jumpToSnap }), [jumpToSnap]);
  return <CompetitorScrollContext.Provider value={value}>{children}</CompetitorScrollContext.Provider>;
}

export function useCompetitorScroll() {
  return useContext(CompetitorScrollContext);
}
