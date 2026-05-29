"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Layers } from "lucide-react";
import {
  filterFoldersForTreeSearch,
  folderAncestorIds,
  folderChildrenOf,
  folderKbKind,
  folderTreeBadgeCount,
  isKbKindTreeExpanded,
  kbKindRootFolders,
  privateKbRootEntries,
} from "../lib/kb_tree_model";

export type KbTreeFolder = {
  folder_id: string;
  name: string;
  kind?: string | null;
  resource_counts?: Record<string, number>;
  subtree_doc_count?: number;
  parent_folder_id?: string | null;
};

export type KbTreeSelection =
  | { kind: "kb"; kb_kind: string }
  | { kind: "folder"; kb_kind: string; folder_id: string };

type PrivateKbRootEntry =
  | { type: "unfiled"; count: number }
  | { type: "folder"; folder: KbTreeFolder };

type KbBrowseTreeProps = {
  kinds: string[];
  allFolders: KbTreeFolder[];
  kbKindLabelById: Map<string, string>;
  selection: KbTreeSelection;
  activeKbKind: string;
  activeFolderId: string | null;
  privateUnfiledCount: number;
  kbGlobalSearch: string;
  onSelectKb: (kbKind: string) => void;
  onSelectFolder: (kbKind: string, folderId: string) => void;
  loadFolderDetail: (folderId: string) => Promise<void>;
  userHasInteractedRef: { current: boolean };
};

const KB_KIND_PRIVATE = "Private";
/** 知识库类型行下：子项整体缩进 + 左侧引导线，避免与「部门公共库」同级错觉 */
const UNDER_KB_INDENT_CLASS = "ml-6 border-l border-zinc-800/50 pl-2";
const INDENT_PX = 14;

function TreeRow({
  depth,
  active,
  icon,
  label,
  count,
  showChevron,
  expanded,
  onToggleExpand,
  onSelect,
}: {
  depth: number;
  active: boolean;
  icon: ReactNode;
  label: string;
  count?: number;
  /** 为 true 时始终显示 ›（含无子文件夹） */
  showChevron: boolean;
  expanded: boolean;
  onToggleExpand?: () => void;
  onSelect: () => void;
}) {
  return (
    <div className="flex min-w-0 items-center gap-0.5 rounded-md pr-1" style={{ paddingLeft: depth * INDENT_PX }}>
      {showChevron ? (
        <button
          type="button"
          aria-label={expanded ? "收起" : "展开"}
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand?.();
          }}
          className="shrink-0 rounded p-0.5 text-zinc-500 hover:bg-zinc-800/80 hover:text-zinc-300"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
      ) : (
        <span className="inline-block w-[18px] shrink-0" aria-hidden />
      )}
      <button
        type="button"
        onClick={onSelect}
        className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-sm transition-colors ${
          active
            ? "border-l-2 border-[#2563eb] bg-zinc-950/70 text-[#93c5fd] pl-[calc(0.375rem-2px)]"
            : "text-zinc-300 hover:bg-zinc-950/50 hover:text-zinc-100"
        }`}
      >
        {icon}
        <span className="truncate">{label}</span>
        {typeof count === "number" ? (
          <span className="ml-auto shrink-0 rounded bg-zinc-900/80 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500">
            {count}
          </span>
        ) : null}
      </button>
    </div>
  );
}

function FolderBranch({
  allFolders,
  parentId,
  kbKind,
  depth,
  expandedFolders,
  toggleFolder,
  activeFolderId,
  onSelectFolder,
  loadFolderDetail,
  userHasInteractedRef,
}: {
  allFolders: KbTreeFolder[];
  parentId: string | null;
  kbKind: string;
  depth: number;
  expandedFolders: Set<string>;
  toggleFolder: (fid: string) => void;
  activeFolderId: string | null;
  onSelectFolder: (kbKind: string, folderId: string) => void;
  loadFolderDetail: (folderId: string) => Promise<void>;
  userHasInteractedRef: { current: boolean };
}) {
  const nodes = (
    parentId === null ? kbKindRootFolders(allFolders, kbKind) : folderChildrenOf(allFolders, parentId)
  ) as KbTreeFolder[];
  if (!nodes.length) return null;

  return (
    <ul className="m-0 list-none p-0" role="group">
      {nodes.map((f) => {
        const fid = f.folder_id;
        const docN = folderTreeBadgeCount(f, allFolders);
        const kids = folderChildrenOf(allFolders, fid);
        const hasKids = kids.length > 0;
        const expanded = expandedFolders.has(fid);
        const active = activeFolderId === fid;

        return (
          <li key={fid} className="relative">
            {depth > 0 ? (
              <span
                className="pointer-events-none absolute bottom-0 left-0 top-0 w-px bg-zinc-800/90"
                style={{ marginLeft: (depth - 1) * INDENT_PX + 8 }}
                aria-hidden
              />
            ) : null}
            <TreeRow
              depth={depth}
              active={active}
              showChevron
              expanded={expanded}
              onToggleExpand={() => toggleFolder(fid)}
              onSelect={() => {
                userHasInteractedRef.current = true;
                onSelectFolder(kbKind, fid);
                void loadFolderDetail(fid);
              }}
              icon={
                active ? (
                  <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[#2563eb]/80" />
                ) : (
                  <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                )
              }
              label={f.name}
              count={docN}
            />
            {expanded && hasKids ? (
              <FolderBranch
                allFolders={allFolders}
                parentId={fid}
                kbKind={kbKind}
                depth={depth + 1}
                expandedFolders={expandedFolders}
                toggleFolder={toggleFolder}
                activeFolderId={activeFolderId}
                onSelectFolder={onSelectFolder}
                loadFolderDetail={loadFolderDetail}
                userHasInteractedRef={userHasInteractedRef}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function KbBrowseTree(props: KbBrowseTreeProps) {
  const {
    kinds,
    allFolders,
    kbKindLabelById,
    selection,
    activeKbKind,
    activeFolderId,
    privateUnfiledCount,
    kbGlobalSearch,
    onSelectKb,
    onSelectFolder,
    loadFolderDetail,
    userHasInteractedRef,
  } = props;

  const [expandedKinds, setExpandedKinds] = useState<Set<string>>(() => new Set([KB_KIND_PRIVATE]));
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set());

  const scopedFolders = useMemo(
    (): KbTreeFolder[] =>
      filterFoldersForTreeSearch(allFolders, kbGlobalSearch) as KbTreeFolder[],
    [allFolders, kbGlobalSearch],
  );

  const searchQ = kbGlobalSearch.trim().toLowerCase();

  useEffect(() => {
    setExpandedKinds((prev) => {
      const next = new Set(prev);
      for (const kid of kinds) {
        if (isKbKindTreeExpanded(kid, activeKbKind, selection)) next.add(kid);
      }
      return next;
    });
    if (activeFolderId) {
      const ancestors = folderAncestorIds(scopedFolders, activeFolderId);
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        next.add(activeFolderId);
        for (const a of ancestors) next.add(a);
        return next;
      });
    }
  }, [activeKbKind, activeFolderId, kinds, scopedFolders, selection]);

  const toggleKind = useCallback((kid: string) => {
    setExpandedKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kid)) next.delete(kid);
      else next.add(kid);
      return next;
    });
  }, []);

  const toggleFolder = useCallback((fid: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(fid)) next.delete(fid);
      else next.add(fid);
      return next;
    });
  }, []);

  return (
    <nav className="space-y-0.5" aria-label="知识库目录树">
      {kinds.map((kid) => {
        const label = kbKindLabelById.get(kid) || kid;
        const kindExpanded = expandedKinds.has(kid);
        const kindActive = selection.kind === "kb" && selection.kb_kind === kid;
        const rootCount = kbKindRootFolders(allFolders, kid).length;

        return (
          <div key={kid} className="rounded-md border border-zinc-800/60 bg-zinc-950/25">
            <div className="flex min-w-0 items-center gap-0.5 px-1 py-0.5">
              <button
                type="button"
                aria-label={kindExpanded ? "收起知识库" : "展开知识库"}
                onClick={() => toggleKind(kid)}
                className="shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800/80 hover:text-zinc-300"
              >
                {kindExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => {
                  userHasInteractedRef.current = true;
                  onSelectKb(kid);
                }}
                className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left transition-colors ${
                  kindActive && !activeFolderId ? "bg-zinc-900/80 text-zinc-50" : "text-zinc-300 hover:bg-zinc-900/50"
                }`}
                title="选择知识库根"
              >
                <Layers className="h-4 w-4 shrink-0 text-zinc-500" />
                <span className="truncate text-sm font-medium">{label}</span>
                {rootCount > 0 ? (
                  <span className="ml-auto shrink-0 text-[10px] text-zinc-600">{rootCount}</span>
                ) : null}
              </button>
            </div>

            {kindExpanded ? (
              <div className="border-t border-zinc-800/50 pb-2 pt-1">
                <div className={UNDER_KB_INDENT_CLASS}>
                {kid === KB_KIND_PRIVATE ? (
                  <ul className="m-0 list-none space-y-0.5 p-0" role="group">
                    {(
                      privateKbRootEntries(
                        scopedFolders.filter((f) => folderKbKind(f) === KB_KIND_PRIVATE),
                        privateUnfiledCount,
                      ) as PrivateKbRootEntry[]
                    ).map((entry) => {
                      if (entry.type === "unfiled") {
                        if (searchQ && !"未归档".includes(searchQ) && entry.count === 0) return null;
                        const unfiledActive = kindActive && !activeFolderId;
                        return (
                          <li key="__unfiled__">
                            <TreeRow
                              depth={0}
                              active={unfiledActive}
                              showChevron={false}
                              expanded={false}
                              onSelect={() => {
                                userHasInteractedRef.current = true;
                                onSelectKb(KB_KIND_PRIVATE);
                              }}
                              icon={<FileText className="h-3.5 w-3.5 shrink-0 text-zinc-500" />}
                              label="未归档"
                              count={entry.count}
                            />
                          </li>
                        );
                      }
                      const f = entry.folder;
                      const fid = f.folder_id;
                      const kids = folderChildrenOf(scopedFolders, fid);
                      const hasKids = kids.length > 0;
                      const expanded = expandedFolders.has(fid);
                      const active = activeFolderId === fid;
                      return (
                        <li key={fid}>
                          <TreeRow
                            depth={0}
                            active={active}
                            showChevron
                            expanded={expanded}
                            onToggleExpand={() => toggleFolder(fid)}
                            onSelect={() => {
                              userHasInteractedRef.current = true;
                              onSelectFolder(KB_KIND_PRIVATE, fid);
                              void loadFolderDetail(fid);
                            }}
                            icon={
                              active ? (
                                <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[#2563eb]/80" />
                              ) : (
                                <Folder className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                              )
                            }
                            label={f.name}
                            count={folderTreeBadgeCount(f, scopedFolders)}
                          />
                          {expanded && hasKids ? (
                            <FolderBranch
                              allFolders={scopedFolders}
                              parentId={fid}
                              kbKind={KB_KIND_PRIVATE}
                              depth={1}
                              expandedFolders={expandedFolders}
                              toggleFolder={toggleFolder}
                              activeFolderId={activeFolderId}
                              onSelectFolder={onSelectFolder}
                              loadFolderDetail={loadFolderDetail}
                              userHasInteractedRef={userHasInteractedRef}
                            />
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <FolderBranch
                    allFolders={scopedFolders}
                    parentId={null}
                    kbKind={kid}
                    depth={0}
                    expandedFolders={expandedFolders}
                    toggleFolder={toggleFolder}
                    activeFolderId={activeFolderId}
                    onSelectFolder={onSelectFolder}
                    loadFolderDetail={loadFolderDetail}
                    userHasInteractedRef={userHasInteractedRef}
                  />
                )}
                {kid !== KB_KIND_PRIVATE && kbKindRootFolders(scopedFolders, kid).length === 0 ? (
                  <div className="rounded border border-dashed border-zinc-800/80 px-2 py-2 text-[11px] text-zinc-600">
                    {searchQ ? "暂无匹配文件夹" : "暂无文件夹"}
                  </div>
                ) : null}
                {kid === KB_KIND_PRIVATE &&
                privateKbRootEntries(
                  scopedFolders.filter((f) => folderKbKind(f) === KB_KIND_PRIVATE),
                  privateUnfiledCount,
                ).filter((e) => e.type !== "unfiled" || !searchQ || "未归档".includes(searchQ)).length === 0 ? (
                  <div className="rounded border border-dashed border-zinc-800/80 px-2 py-2 text-[11px] text-zinc-600">
                    {searchQ ? "暂无匹配项" : "暂无文件夹"}
                  </div>
                ) : null}
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
