"use client";

import { BulkPanel } from "./BulkPanel";
import { DocDetailPanel, type DocDetailPanelDoc } from "./DocDetailPanel";
import { InspectorEmptyState } from "./InspectorEmptyState";

export function InspectorPanel(props: {
  bulkSelection: { doc_ids: string[]; source_folder_id?: string | null };
  activeDoc: DocDetailPanelDoc | null;
  onBulkMove: () => void;
  onBulkCopy: () => void;
  onBulkDelete: () => void;
  onClearBulkSelection: () => void;
  onDocMove: () => void;
  onDocCopy: () => void;
  onDocDelete: () => void;
}) {
  if (props.bulkSelection.doc_ids.length > 0) {
    return (
      <BulkPanel
        count={props.bulkSelection.doc_ids.length}
        source_folder_id={props.bulkSelection.source_folder_id}
        onMove={props.onBulkMove}
        onCopy={props.onBulkCopy}
        onDelete={props.onBulkDelete}
        onClear={props.onClearBulkSelection}
      />
    );
  }

  if (props.activeDoc) {
    return (
      <DocDetailPanel
        doc={props.activeDoc}
        onMove={props.onDocMove}
        onCopy={props.onDocCopy}
        onDelete={props.onDocDelete}
      />
    );
  }

  return <InspectorEmptyState />;
}

