"use client";

import { useParams } from "next/navigation";
import { CompetitorReportShell } from "../../components/CompetitorReportShell";

/** 深链指定期次：/competitor/e/2025-annual */
export default function CompetitorEditionPage() {
  const params = useParams();
  const raw = params?.editionId;
  const editionId = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : null;
  return <CompetitorReportShell editionId={editionId} />;
}
