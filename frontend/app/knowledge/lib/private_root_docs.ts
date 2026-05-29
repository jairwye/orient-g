export type UnfiledPrivateDoc = {
  folder_ids?: string[];
  status?: string;
};

export type FolderBulkCheckState = "none" | "all" | "partial";

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - allow importing JS module
import {
  docIsActiveStatus as _docIsActiveStatus,
  docIsRunningStatus as _docIsRunningStatus,
  folderBulkCheckState as _folderBulkCheckState,
  folderBulkToggleAll as _folderBulkToggleAll,
  isInternalPrivateFolderId as _isInternalPrivateFolderId,
  isUnfiledPrivateDoc as _isUnfiledPrivateDoc,
  nonInternalFolderBindings as _nonInternalFolderBindings,
  visibleFolderBindings as _visibleFolderBindings,
  visibleFolderIdSet as _visibleFolderIdSet,
} from "./private_root_docs.js";

export const isInternalPrivateFolderId: (folderId: string) => boolean = _isInternalPrivateFolderId;
export const visibleFolderIdSet: (folders: { folder_id?: string }[]) => Set<string> = _visibleFolderIdSet;
export const nonInternalFolderBindings: (doc: UnfiledPrivateDoc) => string[] = _nonInternalFolderBindings;
export const visibleFolderBindings: (doc: UnfiledPrivateDoc, visibleIds: Set<string>) => string[] =
  _visibleFolderBindings;
export const isUnfiledPrivateDoc: (
  doc: UnfiledPrivateDoc,
  visibleIds: Set<string>,
  opts?: { includeRunning?: boolean },
) => boolean = _isUnfiledPrivateDoc;
export const docIsActiveStatus: (status?: string | null) => boolean = _docIsActiveStatus;
export const docIsRunningStatus: (status?: string | null) => boolean = _docIsRunningStatus;
export const folderBulkCheckState: (allDocIds: string[], selectedDocIds: string[]) => FolderBulkCheckState =
  _folderBulkCheckState;
export const folderBulkToggleAll: (state: FolderBulkCheckState, allDocIds: string[]) => string[] =
  _folderBulkToggleAll;
