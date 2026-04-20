"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAuthHeaders } from "../lib/auth";

const DEFAULT_FINANCE_PATH = "/finance";
const ROLE_ADMIN = "admin";
const ROLE_MANAGEMENT = "管理层";
/** 用户可选部门（与后端 fixtures 对齐；API 返回的其它部门会追加在末尾） */
const DEPARTMENT_CHOICES = ["总裁办", "财务部", "研发部"] as const;

/** 默认可读模板 / 特殊文档 ACL 的勾选维度（写入 policy_json、acl_json） */
const KB_READ_POLICY_DIMS = [
  { key: "allow_all", label: "全员" },
  { key: "allow_dept_member", label: "本部门成员" },
  { key: "allow_dept_lead", label: "本部门负责人" },
  { key: "allow_project_member", label: "本项目成员" },
  { key: "allow_project_lead", label: "本项目负责人" },
  { key: "allow_owner", label: "文档所有者" },
] as const;

const KB_READ_KIND_ORDER = [
  "Private",
  "DeptPublic",
  "DeptLead",
  "ProjectPublic",
  "ProjectLead",
  "MultiDeptPublic",
  "MultiDeptLead",
  "MultiProjectPublic",
  "MultiProjectLead",
  "CompanyPublic",
] as const;

const KB_READ_KIND_LABELS: Record<string, string> = {
  Private: "私人知识库",
  DeptPublic: "部门公共库",
  DeptLead: "部门负责人库",
  ProjectPublic: "项目公共库",
  ProjectLead: "项目负责人库",
  MultiDeptPublic: "多部门公共库",
  MultiDeptLead: "多部门负责人库",
  MultiProjectPublic: "多项目公共库",
  MultiProjectLead: "多项目负责人库",
  CompanyPublic: "公司公共库",
};

function normalizeKbReadPolicy(p: unknown): Record<string, boolean> {
  const o = p && typeof p === "object" ? (p as Record<string, unknown>) : {};
  const out: Record<string, boolean> = {};
  for (const d of KB_READ_POLICY_DIMS) {
    out[d.key] = Boolean(o[d.key]);
  }
  // 文档 owner 永远可读：UI 强制呈现为勾选
  out["allow_owner"] = true;
  return out;
}

function normalizeSpecialCollections(
  raw: unknown
): Array<{ collection_id: string; label: string; space_type?: string; name?: string }> | undefined {
  if (!Array.isArray(raw)) return undefined;
  const out: Array<{ collection_id: string; label: string; space_type?: string; name?: string }> = [];
  for (const it of raw) {
    if (!it || typeof it !== "object") continue;
    const o = it as Record<string, unknown>;
    const collection_id = typeof o.collection_id === "string" ? o.collection_id : String(o.collection_id ?? "");
    const label = typeof o.label === "string" ? o.label : String(o.label ?? "");
    if (!collection_id || !label) continue;
    const space_type = typeof o.space_type === "string" ? o.space_type : undefined;
    const name = typeof o.name === "string" ? o.name : undefined;
    out.push({ collection_id, label, space_type, name });
  }
  return out.length ? out : undefined;
}

function deriveEffectiveReadFromShareScope(doc: { share_scope?: { kinds?: string[] } }): Record<string, boolean> {
  const kinds = new Set((doc.share_scope?.kinds ?? []).map(String));
  const out: Record<string, boolean> = {};
  // Multi*：实际可读来自 share_scope（共享时选择的部门/项目范围）
  if (kinds.has("MultiDeptPublic")) out["allow_dept_member"] = true;
  if (kinds.has("MultiDeptLead")) out["allow_dept_lead"] = true;
  if (kinds.has("MultiProjectPublic")) out["allow_project_member"] = true;
  if (kinds.has("MultiProjectLead")) out["allow_project_lead"] = true;
  // CompanyPublic：全员可读（展示层面）
  if (kinds.has("CompanyPublic")) out["allow_all"] = true;
  // owner 永远可读（展示层面也保持一致）
  out["allow_owner"] = true;
  return out;
}

function mergeKbDefaultReadItems(raw: { kb_kind: string; policy: unknown }[]) {
  const byKind = new Map<string, Record<string, boolean>>();
  for (const x of raw) {
    byKind.set(x.kb_kind, normalizeKbReadPolicy(x.policy));
  }
  return KB_READ_KIND_ORDER.map((k) => ({ kb_kind: k, policy: byKind.get(k) ?? normalizeKbReadPolicy({}) }));
}

type UserItem = {
  username: string;
  roles?: string[];
  department?: string;
  is_department_lead?: boolean;
  projects?: Array<{ project_id: string; is_project_lead?: boolean }>;
};

type CollectionItem = {
  collection_id: string;
  space_type?: string;
  name?: string;
  type?: string;
  department_id?: string;
  project_id?: string;
  owner_user_id?: string;
};

type KBProjectItem = {
  project_id: string;
  name?: string;
  policy: { allow_leads: boolean; allow_members: boolean };
  members: { leads: string[]; members: string[] };
};

type KBDepartmentItem = {
  department_id: string;
  name?: string;
  policy: { allow_leads: boolean; allow_members: boolean };
};

type KBPrivateOwnerItem = { private_collection_id: string; name?: string; owner_username?: string | null };
type KBDocAssignmentItem = { doc_id: string; title?: string; collection_ids: string[] };
type KBTableAssignmentItem = { table_id: string; name?: string; collection_ids: string[] };

type KBDocOwnerItem = { doc_id: string; title?: string; owner_username?: string | null };
type KBTableOwnerItem = { table_id: string; name?: string; owner_username?: string | null };

type KbSpecialDocRow = {
  doc_id: string;
  title?: string;
  special_collection_ids: string[];
  special_collections?: Array<{ collection_id: string; label: string; space_type?: string; name?: string }>;
  acl: Record<string, boolean>;
  share_scope?: { kinds?: string[]; department_ids?: string[]; project_ids?: string[] };
};

export default function AdminPage() {
  const [financePath, setFinancePath] = useState(DEFAULT_FINANCE_PATH);

  // 当前登录用户是否为管理员（来自 /api/auth/me）
  const [isAdmin, setIsAdmin] = useState(false);

  const [users, setUsers] = useState<UserItem[]>([]);
  const [newUsername, setNewUsername] = useState("");
  const [userAddLoading, setUserAddLoading] = useState(false);
  const [userAddMessage, setUserAddMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [resettingUser, setResettingUser] = useState<string | null>(null);
  const [deletingUser, setDeletingUser] = useState<string | null>(null);
  const [updatingRolesUser, setUpdatingRolesUser] = useState<string | null>(null);

  // KB ACL（rel_only）
  const [, setKbDepartments] = useState<KBDepartmentItem[]>([]);
  const [kbProjects, setKbProjects] = useState<KBProjectItem[]>([]);
  const [kbPrivateOwners, setKbPrivateOwners] = useState<KBPrivateOwnerItem[]>([]);
  const [kbResourceAssignments, setKbResourceAssignments] = useState<{ docs: KBDocAssignmentItem[]; tables: KBTableAssignmentItem[] }>({
    docs: [],
    tables: [],
  });
  const [kbResourceOwners, setKbResourceOwners] = useState<{ docs: KBDocOwnerItem[]; tables: KBTableOwnerItem[] }>({ docs: [], tables: [] });
  const [kbCollections, setKbCollections] = useState<CollectionItem[]>([]);
  const [kbSaving, setKbSaving] = useState(false);
  const [kbMessage, setKbMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [projectOptions, setProjectOptions] = useState<Array<{ project_id: string; name?: string }>>([]);
  const [departmentOptions, setDepartmentOptions] = useState<string[]>([]);

  const [overridesUsername, setOverridesUsername] = useState<string>("");
  const [kbPermReadAllow, setKbPermReadAllow] = useState<string[]>([]);
  const [kbPermWriteAllow, setKbPermWriteAllow] = useState<string[]>([]);
  const [overridesLoading, setOverridesLoading] = useState(false);

  const [kbDefaultReadItems, setKbDefaultReadItems] = useState<Array<{ kb_kind: string; policy: Record<string, boolean> }>>([]);
  const [kbSpecialDocs, setKbSpecialDocs] = useState<KbSpecialDocRow[]>([]);

  const usernameOptions = users.map((u) => u.username).filter(Boolean);

  useEffect(() => {
    fetch("/api/settings", { credentials: "include", headers: getAuthHeaders() })
      .then((r) =>
        r.ok ? r.json() : { finance_path: DEFAULT_FINANCE_PATH, users: [{ username: "admin", roles: [ROLE_ADMIN], department: "" }] }
      )
      .then((data: { finance_path?: string; users?: UserItem[] }) => {
        const p = data.finance_path ?? DEFAULT_FINANCE_PATH;
        setFinancePath(p);
        setUsers(
          (data.users ?? [{ username: "admin", roles: [ROLE_ADMIN], department: "" }]).map((u) => ({
            username: u.username,
            roles: u.roles ?? [],
            department: u.department ?? "",
            is_department_lead: Boolean((u as UserItem).is_department_lead),
            projects: (u as UserItem).projects ?? [],
          }))
        );
        // 简单根据配置中的 admin 账号推断当前页面是否只应由管理员访问；后续再结合 /api/auth/me 精细化
        const hasAdmin = (data.users ?? []).some((u) => (u.roles ?? []).includes(ROLE_ADMIN));
        if (hasAdmin) {
          setIsAdmin(true);
        }
      })
      .catch(() => {});
  }, []);

  // 用户维度（projects/departments）用于“用户与权限”里的项目多选展示
  useEffect(() => {
    const loadUserDims = async () => {
      try {
        const r = await fetch("/api/settings/users/projects", { credentials: "include", headers: getAuthHeaders() });
        const data = r.ok ? await r.json() : { projects: [], departments: [] };
        setProjectOptions((data?.projects ?? []) as Array<{ project_id: string; name?: string }>);
        setDepartmentOptions((data?.departments ?? []) as string[]);
      } catch {
        // ignore
      }
    };
    loadUserDims();
  }, []);

  useEffect(() => {
    // 仅在管理员时加载 kb-acl / kb-meta 相关数据
    if (!isAdmin) return;
    const loadKbMeta = async () => {
      try {
        const [defReadRes, specDocsRes] = await Promise.all([
          fetch("/api/settings/kb-meta/default-read-policies", { credentials: "include", headers: getAuthHeaders() }),
          fetch("/api/settings/kb-meta/special-docs", { credentials: "include", headers: getAuthHeaders() }),
        ]);
        const defReadData = defReadRes.ok ? await defReadRes.json() : { items: [] };
        const specDocsData = specDocsRes.ok ? await specDocsRes.json() : { items: [] };
        setKbDefaultReadItems(mergeKbDefaultReadItems((defReadData?.items ?? []) as { kb_kind: string; policy: unknown }[]));
        setKbSpecialDocs(
          ((specDocsData?.items ?? []) as Array<Record<string, unknown>>).map((x) => ({
            doc_id: String(x.doc_id ?? ""),
            title: typeof x.title === "string" ? x.title : undefined,
            special_collection_ids: Array.isArray(x.special_collection_ids)
              ? (x.special_collection_ids as string[]).map(String)
              : [],
            special_collections: normalizeSpecialCollections(x.special_collections),
            acl: normalizeKbReadPolicy(x.acl),
            share_scope: x.share_scope ? (x.share_scope as Record<string, unknown>) : undefined,
          }))
        );
      } catch {
        // ignore
      }
    };
    loadKbMeta();
  }, [isAdmin]);

  const refreshKbAcl = async () => {
    if (!isAdmin) return;
    try {
      const [defReadRes, specDocsRes, depsRes, projRes, ownersRes, assignsRes, privateOwnersRes] = await Promise.all([
        fetch("/api/settings/kb-meta/default-read-policies", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-meta/special-docs", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-acl/departments", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-acl/projects", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-acl/resource-owners", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-acl/resource-assignments", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/settings/kb-acl/private-owners", { credentials: "include", headers: getAuthHeaders() }),
      ]);
      const defReadData = defReadRes.ok ? await defReadRes.json() : { items: [] };
      const specDocsData = specDocsRes.ok ? await specDocsRes.json() : { items: [] };
      setKbDefaultReadItems(mergeKbDefaultReadItems((defReadData?.items ?? []) as { kb_kind: string; policy: unknown }[]));
      setKbSpecialDocs(
        ((specDocsData?.items ?? []) as Array<Record<string, unknown>>).map((x) => ({
          doc_id: String(x.doc_id ?? ""),
          title: typeof x.title === "string" ? x.title : undefined,
          special_collection_ids: Array.isArray(x.special_collection_ids)
            ? (x.special_collection_ids as string[]).map(String)
            : [],
          special_collections: normalizeSpecialCollections(x.special_collections),
          acl: normalizeKbReadPolicy(x.acl),
          share_scope: x.share_scope ? (x.share_scope as Record<string, unknown>) : undefined,
        }))
      );

      const depsData = depsRes.ok ? await depsRes.json() : { items: [] };
      setKbDepartments(Array.isArray(depsData?.items) ? (depsData.items as KBDepartmentItem[]) : []);

      const projData = projRes.ok ? await projRes.json() : { items: [] };
      setKbProjects(Array.isArray(projData?.items) ? (projData.items as KBProjectItem[]) : []);

      const ownersData = ownersRes.ok ? await ownersRes.json() : { docs: [], tables: [] };
      setKbResourceOwners({
        docs: Array.isArray(ownersData?.docs) ? (ownersData.docs as KBDocOwnerItem[]) : [],
        tables: Array.isArray(ownersData?.tables) ? (ownersData.tables as KBTableOwnerItem[]) : [],
      });

      const assignsData = assignsRes.ok ? await assignsRes.json() : { docs: [], tables: [], collections: [] };
      setKbResourceAssignments({
        docs: Array.isArray(assignsData?.docs) ? (assignsData.docs as KBDocAssignmentItem[]) : [],
        tables: Array.isArray(assignsData?.tables) ? (assignsData.tables as KBTableAssignmentItem[]) : [],
      });
      setKbCollections(Array.isArray(assignsData?.collections) ? (assignsData.collections as CollectionItem[]) : []);

      const privData = privateOwnersRes.ok ? await privateOwnersRes.json() : { items: [] };
      setKbPrivateOwners(Array.isArray(privData?.items) ? (privData.items as KBPrivateOwnerItem[]) : []);
    } catch {
      // ignore
    }
  };

  const toggleKbDefaultRead = (kbKind: string, dimKey: string) => {
    setKbDefaultReadItems((prev) =>
      prev.map((row) =>
        row.kb_kind === kbKind ? { ...row, policy: { ...row.policy, [dimKey]: !row.policy[dimKey] } } : row
      )
    );
  };

  const toggleKbSpecialDocAcl = (docId: string, dimKey: string) => {
    // allow_owner 在展示层强制为 true，不允许通过特殊 ACL 取消
    if (dimKey === "allow_owner") return;
    setKbSpecialDocs((prev) =>
      prev.map((row) => (row.doc_id === docId ? { ...row, acl: { ...row.acl, [dimKey]: !row.acl[dimKey] } } : row))
    );
  };

  const handleSaveKbDefaultReadPolicies = async () => {
    if (!isAdmin) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      const r = await fetch("/api/settings/kb-meta/default-read-policies", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ items: kbDefaultReadItems }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || "保存默认可读失败");
      setKbMessage({ type: "success", text: "知识库类型默认可读已保存。" });
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存默认可读失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleSaveKbSpecialDocs = async () => {
    if (!isAdmin) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      const r = await fetch("/api/settings/kb-meta/special-docs", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ items: kbSpecialDocs.map((x) => ({ doc_id: x.doc_id, acl: x.acl })) }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || "保存特殊文档 ACL 失败");
      setKbMessage({ type: "success", text: "特殊文档读权限已保存。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存特殊文档 ACL 失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleSaveResourceOwners = async () => {
    setKbSaving(true);
    setKbMessage(null);
    try {
      const items = [
        ...kbResourceOwners.docs
          .filter((d) => (d.owner_username || "").trim())
          .map((d) => ({ resource_type: "doc", resource_id: d.doc_id, owner_username: (d.owner_username || "").trim() })),
        ...kbResourceOwners.tables
          .filter((t) => (t.owner_username || "").trim())
          .map((t) => ({ resource_type: "table", resource_id: t.table_id, owner_username: (t.owner_username || "").trim() })),
      ];
      const r = await fetch("/api/settings/kb-acl/resource-owners", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ items }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || "保存资源 owner 失败");
      setKbMessage({ type: "success", text: "资源 owner 已保存（owner 默认可改）。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const loadUserKbPermissions = async (username: string) => {
    if (!isAdmin) return;
    const un = (username || "").trim();
    if (!un) return;
    setOverridesLoading(true);
    try {
      const [previewRes, readRes, writeRes] = await Promise.all([
        fetch(`/api/settings/kb-acl/preview/${encodeURIComponent(un)}`, { credentials: "include", headers: getAuthHeaders() }),
        fetch(`/api/settings/kb-acl/user-overrides/${encodeURIComponent(un)}`, { credentials: "include", headers: getAuthHeaders() }),
        fetch(`/api/settings/kb-acl/user-write-overrides/${encodeURIComponent(un)}`, { credentials: "include", headers: getAuthHeaders() }),
      ]);
      const previewData = await previewRes.json().catch(() => ({}));
      const readData = await readRes.json().catch(() => ({}));
      const writeData = await writeRes.json().catch(() => ({}));
      if (!previewRes.ok) throw new Error(typeof previewData.detail === "string" ? previewData.detail : "加载默认权限失败");
      if (!readRes.ok) throw new Error(typeof readData.detail === "string" ? readData.detail : "加载可读 overrides 失败");
      if (!writeRes.ok) throw new Error(typeof writeData.detail === "string" ? writeData.detail : "加载可写 overrides 失败");

      // 默认（自动计算）先勾上
      const defaultRead = (previewData?.scope?.allowed_collection_ids ?? []) as string[];
      const defaultWrite = (previewData?.scope?.writable_collection_ids ?? []) as string[];

      // 手工覆盖（allow）叠加进来
      const readAllow = (readData.overrides || [])
        .filter((x: unknown) => {
          if (!x || typeof x !== "object") return false;
          const o = x as { effect?: unknown; resource_type?: unknown; resource_id?: unknown };
          return o.effect === "allow" && o.resource_type === "collection" && typeof o.resource_id === "string";
        })
        .map((x: unknown) => (x as { resource_id: string }).resource_id);
      const writeAllow = (writeData.overrides || [])
        .filter((x: unknown) => {
          if (!x || typeof x !== "object") return false;
          const o = x as { effect?: unknown; collection_id?: unknown };
          return o.effect === "allow" && typeof o.collection_id === "string";
        })
        .map((x: unknown) => (x as { collection_id: string }).collection_id);

      setKbPermReadAllow(Array.from(new Set([...(defaultRead || []), ...(readAllow || [])])));
      setKbPermWriteAllow(Array.from(new Set([...(defaultWrite || []), ...(writeAllow || [])])));
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "加载失败" });
    } finally {
      setOverridesLoading(false);
    }
  };

  const saveUserKbPermissions = async () => {
    if (!isAdmin) return;
    const username = overridesUsername.trim();
    if (!username) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      const readOverrides = kbPermReadAllow.map((cid) => ({ effect: "allow", resource_type: "collection", resource_id: cid }));
      const writeOverrides = kbPermWriteAllow.map((cid) => ({ effect: "allow", collection_id: cid }));
      const [r1, r2] = await Promise.all([
        fetch("/api/settings/kb-acl/user-overrides", {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ username, overrides: readOverrides }),
        }),
        fetch("/api/settings/kb-acl/user-write-overrides", {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ username, overrides: writeOverrides }),
        }),
      ]);
      const d1 = await r1.json().catch(() => ({}));
      const d2 = await r2.json().catch(() => ({}));
      if (!r1.ok) throw new Error(typeof d1.detail === "string" ? d1.detail : "保存可读权限失败");
      if (!r2.ok) throw new Error(typeof d2.detail === "string" ? d2.detail : "保存可写权限失败");
      setKbMessage({ type: "success", text: "知识库可读/可写权限已保存（doc/table 跟随知识库归属）。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleSaveProjectPolicyAndMembers = async () => {
    if (!isAdmin || kbProjects.length === 0) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      for (const p of kbProjects) {
        const r1 = await fetch(`/api/settings/kb-acl/projects/${p.project_id}/policy`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ allow_leads: p.policy.allow_leads, allow_members: p.policy.allow_members }),
        });
        if (!r1.ok) throw new Error((await r1.json().catch(() => ({})))?.detail || "保存 ProjectPublic policy 失败");

        const r2 = await fetch(`/api/settings/kb-acl/projects/${p.project_id}/members`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ leads: p.members.leads, members: p.members.members }),
        });
        if (!r2.ok) throw new Error((await r2.json().catch(() => ({})))?.detail || "保存 project members 失败");
      }

      setKbMessage({ type: "success", text: "ProjectPublic ACL 已保存。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleSavePrivateOwners = async () => {
    if (!isAdmin) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      const items = kbPrivateOwners
        .map((it) => ({ private_collection_id: it.private_collection_id, owner_username: it.owner_username || "" }))
        .filter((x) => x.owner_username);

      const r = await fetch("/api/settings/kb-acl/private-owners", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ items }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || "保存 private owner 失败");

      setKbMessage({ type: "success", text: "Private owner 已保存。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleSaveResourceAssignments = async () => {
    if (!isAdmin) return;
    setKbSaving(true);
    setKbMessage(null);
    try {
      const payload = {
        docs: kbResourceAssignments.docs.map((d) => ({ doc_id: d.doc_id, collection_ids: d.collection_ids })),
        tables: kbResourceAssignments.tables.map((t) => ({ table_id: t.table_id, collection_ids: t.collection_ids })),
      };

      const r = await fetch("/api/settings/kb-acl/resource-assignments", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail || "保存 resource assignments 失败");

      setKbMessage({ type: "success", text: "doc/table -> collection 分配已保存。" });
      await refreshKbAcl();
    } catch (e) {
      setKbMessage({ type: "error", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setKbSaving(false);
    }
  };

  const handleAddUser = async () => {
    const username = newUsername.trim();
    if (!username) {
      setUserAddMessage({ type: "error", text: "请输入用户名" });
      return;
    }
    if (!/^[a-zA-Z0-9_]+$/.test(username)) {
      setUserAddMessage({ type: "error", text: "用户名仅允许字母、数字、下划线" });
      return;
    }
    setUserAddLoading(true);
    setUserAddMessage(null);
    try {
      const res = await fetch("/api/settings/users", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "添加失败";
        throw new Error(msg);
      }
      setUsers((prev) => [
        ...prev,
        {
          username: data.username ?? username,
          roles: data.roles ?? [],
          department: data.department ?? "",
          is_department_lead: Boolean(data.is_department_lead),
          projects: data.projects ?? [],
        },
      ]);
      setNewUsername("");
      setUserAddMessage({ type: "success", text: "已添加用户，默认密码为 123456，首次登录须修改密码。" });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "添加失败，请重试",
      });
    } finally {
      setUserAddLoading(false);
    }
  };

  const handleResetPassword = async (username: string) => {
    setResettingUser(username);
    try {
      const res = await fetch("/api/settings/users/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "重设失败";
        throw new Error(msg);
      }
      setUserAddMessage({ type: "success", text: `已将用户「${username}」的密码重设为 123456，该用户下次登录须修改密码。` });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "重设失败，请重试",
      });
    } finally {
      setResettingUser(null);
    }
  };

  const handleDeleteUser = async (username: string) => {
    if (!confirm(`确定要删除用户「${username}」吗？`)) return;
    setDeletingUser(username);
    setUserAddMessage(null);
    try {
      const res = await fetch("/api/settings/users", {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ username }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "删除失败";
        throw new Error(msg);
      }
      setUsers((prev) => prev.filter((u) => u.username.toLowerCase() !== username.toLowerCase()));
      setUserAddMessage({ type: "success", text: `已删除用户「${username}」。` });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "删除失败，请重试",
      });
    } finally {
      setDeletingUser(null);
    }
  };

  const handleUpdateRolesAndDepartment = async (
    username: string,
    roles: string[],
    department: string,
    isDepartmentLead?: boolean,
    projects?: Array<{ project_id: string; is_project_lead?: boolean }>
  ) => {
    setUpdatingRolesUser(username);
    setUserAddMessage(null);
    try {
      const res = await fetch("/api/settings/users/roles", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ username, roles, department, is_department_lead: isDepartmentLead, projects }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "保存失败";
        throw new Error(msg);
      }
      setUsers((prev) =>
        prev.map((u) =>
          u.username.toLowerCase() === username.toLowerCase()
            ? {
                ...u,
                roles: data.roles ?? roles,
                department: data.department ?? department,
                is_department_lead: data.is_department_lead ?? isDepartmentLead ?? u.is_department_lead,
                projects: data.projects ?? projects ?? u.projects ?? [],
              }
            : u
        )
      );
      setUserAddMessage({ type: "success", text: `已更新用户「${username}」权限。` });
    } catch (err) {
      setUserAddMessage({
        type: "error",
        text: err instanceof Error ? err.message : "保存失败，请重试",
      });
    } finally {
      setUpdatingRolesUser(null);
    }
  };

  const toggleRole = (u: UserItem, role: string, checked: boolean): string[] => {
    const roles = u.roles ?? [];
    const has = roles.some((r) => (r || "").toLowerCase() === role.toLowerCase() || r === role);
    if (checked && !has) return [...roles, role === ROLE_ADMIN ? ROLE_ADMIN : role];
    if (!checked && has) return roles.filter((r) => (r || "").toLowerCase() !== role.toLowerCase() && r !== role);
    return roles;
  };

  const departmentSelectOptions = (() => {
    const out: string[] = [...DEPARTMENT_CHOICES];
    for (const d of departmentOptions) {
      const s = (d || "").trim();
      if (s && !out.includes(s)) out.push(s);
    }
    return out;
  })();

  const formatCollectionLabel = (collectionId: string) => {
    const c = kbCollections.find((x) => x.collection_id === collectionId);
    if (!c) return collectionId;
    const t = c.type || "";
    let prefix = "知识库";
    if (t === "public") prefix = "公司-公共";
    else if (t === "department") prefix = `${c.department_id || "部门"}-公共`;
    else if (t === "project") prefix = `${c.name || c.project_id || "项目"}-公共`;
    else if (t === "private") prefix = `${c.owner_user_id || "个人"}-私有`;
    return `${prefix}（${collectionId}）`;
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">管理后台</h1>
        <p className="mt-1 text-sm text-zinc-500">管理用户与登录设置（财务后台请前往单独入口）。</p>
        <p className="mt-2">
          <Link href={financePath} className="text-sm text-zinc-400 hover:text-zinc-300">
            前往财务后台
          </Link>
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
      {/* 用户与权限管理 */}
      <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">用户与权限管理</h2>
        <p className="mb-3 text-xs text-zinc-500">
          新增用户仅需填写用户名，默认密码为 123456；首次登录须修改密码。每位用户可勾选「管理员」「管理层」；在「部门」中选择总裁办/财务部/研发部等，并可勾选「部门负责人」。在「项目」中对各项目勾选是否参与，参与后再勾选是否「项目负责人」。管理员、管理层、部门=财务部均可查看经营数据页；仅管理员可进管理后台与财务后台。
        </p>
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-medium text-zinc-500">现有用户与权限</h3>
            {users.length === 0 ? (
              <p className="text-sm text-zinc-500">暂无用户</p>
            ) : (
              <ul className="space-y-2">
                {users.map((u) => (
                  <li key={u.username} className="flex flex-col gap-2 rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1 truncate text-sm text-zinc-200">{u.username}</div>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleResetPassword(u.username)}
                          disabled={resettingUser !== null}
                          className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-600 disabled:opacity-50"
                        >
                          {resettingUser === u.username ? "处理中…" : "重设为默认密码"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteUser(u.username)}
                          disabled={deletingUser !== null || users.length <= 1}
                          title={users.length <= 1 ? "至少保留一名用户" : "删除该用户"}
                          className="rounded border border-red-900/60 bg-red-900/30 px-2 py-1 text-xs text-red-300 hover:bg-red-900/50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {deletingUser === u.username ? "删除中…" : "删除"}
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-400">
                        <input
                          type="checkbox"
                          checked={(u.roles ?? []).some((r) => (r || "").toLowerCase() === ROLE_ADMIN)}
                          onChange={(e) =>
                            handleUpdateRolesAndDepartment(
                              u.username,
                              toggleRole(u, ROLE_ADMIN, e.target.checked),
                              u.department ?? "",
                              Boolean(u.is_department_lead),
                              u.projects ?? []
                            )
                          }
                          disabled={updatingRolesUser !== null}
                          className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-zinc-200"
                        />
                        管理员
                      </label>
                      <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-400">
                        <input
                          type="checkbox"
                          checked={(u.roles ?? []).some((r) => r === ROLE_MANAGEMENT)}
                          onChange={(e) =>
                            handleUpdateRolesAndDepartment(
                              u.username,
                              toggleRole(u, ROLE_MANAGEMENT, e.target.checked),
                              u.department ?? "",
                              Boolean(u.is_department_lead),
                              u.projects ?? []
                            )
                          }
                          disabled={updatingRolesUser !== null}
                          className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-zinc-200"
                        />
                        管理层
                      </label>
                      <span className="mx-1 h-4 w-px bg-zinc-700/60" />
                      <span className="text-xs font-medium text-zinc-500">部门</span>
                      <select
                        value={u.department ?? ""}
                        onChange={(e) =>
                          handleUpdateRolesAndDepartment(
                            u.username,
                            u.roles ?? [],
                            e.target.value,
                            Boolean(u.is_department_lead),
                            u.projects ?? []
                          )
                        }
                        disabled={updatingRolesUser !== null}
                        className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-zinc-200 text-xs"
                      >
                        <option value="">未设置</option>
                        {departmentSelectOptions.map((d) => (
                          <option key={`dep-opt-${d}`} value={d}>
                            {d}
                          </option>
                        ))}
                      </select>
                      <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-400">
                        <input
                          type="checkbox"
                          checked={Boolean(u.is_department_lead)}
                          onChange={(e) =>
                            handleUpdateRolesAndDepartment(
                              u.username,
                              u.roles ?? [],
                              u.department ?? "",
                              e.target.checked,
                              u.projects ?? []
                            )
                          }
                          disabled={updatingRolesUser !== null}
                          className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-zinc-200"
                        />
                        部门负责人
                      </label>
                      {updatingRolesUser === u.username && <span className="text-xs text-zinc-500">保存中…</span>}
                    </div>
                    <div className="border-t border-zinc-700/60 pt-2">
                      <div className="mb-2 text-xs font-medium text-zinc-500">项目（可多选；先勾选「参与」，再勾选「项目负责人」）</div>
                      <div className="flex flex-wrap gap-2">
                        {(projectOptions || []).length === 0 ? (
                          <span className="text-xs text-zinc-500">暂无项目配置（请确认后端 fixtures / projects 表已同步）</span>
                        ) : (
                          (projectOptions || []).map((po) => {
                            const entry = (u.projects || []).find((p) => p.project_id === po.project_id);
                            const inProject = Boolean(entry);
                            const isLead = Boolean(entry?.is_project_lead);
                            const label = po.name || po.project_id;
                            return (
                              <div
                                key={`proj-role-${u.username}-${po.project_id}`}
                                className="flex flex-wrap items-center gap-2 rounded border border-zinc-700 bg-zinc-900/40 px-2 py-1.5 text-xs text-zinc-300"
                              >
                                <span className="text-zinc-200">{label}</span>
                                <label className="flex cursor-pointer items-center gap-1.5 text-zinc-400">
                                  <input
                                    type="checkbox"
                                    checked={inProject}
                                    disabled={updatingRolesUser !== null}
                                    onChange={(e) => {
                                      const kept = (u.projects || []).filter((p) => p.project_id !== po.project_id);
                                      const projects = e.target.checked
                                        ? [...kept, { project_id: po.project_id, is_project_lead: false }]
                                        : kept;
                                      handleUpdateRolesAndDepartment(
                                        u.username,
                                        u.roles ?? [],
                                        u.department ?? "",
                                        Boolean(u.is_department_lead),
                                        projects
                                      );
                                    }}
                                    className="h-4 w-4 rounded border-zinc-600 bg-zinc-800"
                                  />
                                  参与
                                </label>
                                <label className="flex cursor-pointer items-center gap-1.5 text-zinc-400">
                                  <input
                                    type="checkbox"
                                    checked={isLead}
                                    disabled={updatingRolesUser !== null || !inProject}
                                    onChange={(e) => {
                                      const kept = (u.projects || []).filter((p) => p.project_id !== po.project_id);
                                      const projects = [
                                        ...kept,
                                        { project_id: po.project_id, is_project_lead: e.target.checked },
                                      ];
                                      handleUpdateRolesAndDepartment(
                                        u.username,
                                        u.roles ?? [],
                                        u.department ?? "",
                                        Boolean(u.is_department_lead),
                                        projects
                                      );
                                    }}
                                    className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 disabled:opacity-40"
                                  />
                                  项目负责人
                                </label>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-zinc-500">新增用户</h3>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[140px]">
                <label className="mb-1 block text-xs text-zinc-500">用户名</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="字母、数字、下划线"
                  className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
                />
              </div>
              <button
                type="button"
                onClick={handleAddUser}
                disabled={userAddLoading}
                className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
              >
                {userAddLoading ? "添加中…" : "添加用户"}
              </button>
            </div>
          </div>
        </div>
        {userAddMessage && (
          <p className={`mt-2 text-sm ${userAddMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {userAddMessage.text}
          </p>
        )}
      </div>

      {/* 知识库设置（按当前设想：先只展示“默认可读”与“特殊文档权限”） */}
      <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-2 text-sm font-medium text-zinc-300">知识库设置</h2>
        <p className="mb-4 text-xs text-zinc-500">默认可读模板与特殊文档权限；其余 ACL 调试工具暂不显示。</p>

        {kbMessage && (
          <p className={`mb-4 text-sm ${kbMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>{kbMessage.text}</p>
        )}

        {/* 知识库类型默认可读（模板，与执行层 policy 可双写；此处落 kb_kind_default_read_policy） */}
        <div className="mb-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm text-zinc-200">知识库类型 · 默认可读勾选</h3>
              <p className="mt-1 text-xs text-zinc-500">按 10 类 kb_kind 配置模板维度；枚举英文，文案中文。执行仍以部门/项目 policy 与 ACL 为准。</p>
            </div>
            <button
              type="button"
              disabled={kbSaving}
              onClick={handleSaveKbDefaultReadPolicies}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存默认可读"}
            </button>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-400">
                  <th className="py-2 pr-3 font-medium">类型</th>
                  {KB_READ_POLICY_DIMS.map((d) => (
                    <th key={d.key} className="px-1 py-2 font-medium text-center">
                      {d.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {kbDefaultReadItems.map((row) => (
                  <tr key={row.kb_kind} className="border-b border-zinc-800/80">
                    <td className="py-2 pr-3 text-zinc-200">
                      {KB_READ_KIND_LABELS[row.kb_kind] ?? row.kb_kind}
                      <span className="ml-1 text-zinc-500">({row.kb_kind})</span>
                    </td>
                    {KB_READ_POLICY_DIMS.map((d) => (
                      <td key={d.key} className="px-1 py-2 text-center">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                          checked={!!row.policy[d.key]}
                          disabled={kbSaving || d.key === "allow_owner"}
                          onChange={() => toggleKbDefaultRead(row.kb_kind, d.key)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 多部门/多项目/公司公共等特殊库上的文档 */}
        <div className="mb-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm text-zinc-200">特殊知识库文档 · 读权限勾选</h3>
              <p className="mt-1 text-xs text-zinc-500">列出已关联多部门/多项目/公司公共等特殊 collection 的文档，勾选维度写入 kb_special_doc_acl。</p>
            </div>
            <button
              type="button"
              disabled={kbSaving || kbSpecialDocs.length === 0}
              onClick={handleSaveKbSpecialDocs}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存特殊文档 ACL"}
            </button>
          </div>
          <div className="mt-4 space-y-4">
            {kbSpecialDocs.length === 0 ? (
              <p className="text-sm text-zinc-500">当前无关联特殊库的文档（共享到 Multi* / 公司公共等后会出现）。</p>
            ) : (
              kbSpecialDocs.map((doc) => (
                <div key={doc.doc_id} className="rounded-md border border-zinc-800 bg-zinc-950/30 p-3">
                  <div className="mb-2 text-sm text-zinc-200">{doc.title || doc.doc_id}</div>
                  <div className="mb-2 text-xs text-zinc-500">
                    特殊知识库：
                    {(doc.special_collections?.length
                      ? doc.special_collections.map((c) => c.label || c.collection_id).join("、")
                      : doc.special_collection_ids.join("、")) || "—"}
                  </div>
                  {!!((doc.share_scope?.department_ids?.length ?? 0) > 0 || (doc.share_scope?.project_ids?.length ?? 0) > 0) && (
                    <div className="mb-2 space-y-1 text-xs text-zinc-500">
                      {doc.share_scope?.department_ids?.length ? (
                        <div>共享范围（部门）: {doc.share_scope?.department_ids?.join(", ")}</div>
                      ) : null}
                      {doc.share_scope?.project_ids?.length ? (
                        <div>共享范围（项目）: {doc.share_scope?.project_ids?.join(", ")}</div>
                      ) : null}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-4">
                    {(() => {
                      const eff = deriveEffectiveReadFromShareScope(doc);
                      return KB_READ_POLICY_DIMS.map((d) => {
                        const derived = !!eff[d.key];
                        const explicit = !!doc.acl[d.key];
                        const checked = derived || explicit;
                        const disabled = kbSaving || derived || d.key === "allow_owner";
                        const title = derived ? "由共享范围/类型决定（只读展示）" : "特殊文档 ACL 覆盖（可编辑）";
                        return (
                          <label key={d.key} className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300" title={title}>
                            <input
                              type="checkbox"
                              className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800 disabled:opacity-50"
                              checked={checked}
                              disabled={disabled}
                              onChange={() => toggleKbSpecialDocAcl(doc.doc_id, d.key)}
                            />
                            {d.label}
                          </label>
                        );
                      });
                    })()}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 以下调试/覆盖工具 */}
        {/* ProjectPublic */}
        <div className="mb-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm text-zinc-200">ProjectPublic：负责人可访问 / 成员可访问</h3>
            <button
              type="button"
              disabled={kbSaving}
              onClick={handleSaveProjectPolicyAndMembers}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存 ProjectPublic"}
            </button>
          </div>

          <div className="mt-4 space-y-4">
            {kbProjects.length === 0 ? (
              <p className="text-sm text-zinc-500">暂无 ProjectPublic 数据</p>
            ) : (
              kbProjects.map((p) => (
                <div key={p.project_id} className="rounded-md border border-zinc-800 bg-zinc-950/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-[220px]">
                      <div className="text-xs text-zinc-400">项目</div>
                      <div className="text-sm text-zinc-200">{p.name || p.project_id}</div>
                    </div>
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2 text-xs text-zinc-300">
                        <input
                          type="checkbox"
                          checked={p.policy.allow_leads}
                          disabled={kbSaving}
                          onChange={(e) =>
                            setKbProjects((prev) =>
                              prev.map((x) => (x.project_id === p.project_id ? { ...x, policy: { ...x.policy, allow_leads: e.target.checked } } : x))
                            )
                          }
                          className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                        />
                        允许负责人
                      </label>
                      <label className="flex items-center gap-2 text-xs text-zinc-300">
                        <input
                          type="checkbox"
                          checked={p.policy.allow_members}
                          disabled={kbSaving}
                          onChange={(e) =>
                            setKbProjects((prev) =>
                              prev.map((x) => (x.project_id === p.project_id ? { ...x, policy: { ...x.policy, allow_members: e.target.checked } } : x))
                            )
                          }
                          className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                        />
                        允许成员
                      </label>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                    <div>
                      <div className="text-xs text-zinc-400 mb-1">负责人（leads）</div>
                      <div className="flex flex-wrap gap-3">
                        {usernameOptions.map((u) => {
                          const checked = p.members.leads.includes(u);
                          return (
                            <label key={`${p.project_id}-lead-${u}`} className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={kbSaving}
                                onChange={(e) => {
                                  setKbProjects((prev) =>
                                    prev.map((x) => {
                                      if (x.project_id !== p.project_id) return x;
                                      if (e.target.checked) {
                                        const nextLeads = Array.from(new Set([...x.members.leads, u]));
                                        const nextMembers = x.members.members.filter((m) => m !== u);
                                        return { ...x, members: { ...x.members, leads: nextLeads, members: nextMembers } };
                                      }
                                      const nextLeads = x.members.leads.filter((m) => m !== u);
                                      return { ...x, members: { ...x.members, leads: nextLeads } };
                                    })
                                  );
                                }}
                                className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                              />
                              {u}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-zinc-400 mb-1">成员（members）</div>
                      <div className="flex flex-wrap gap-3">
                        {usernameOptions.map((u) => {
                          const checked = p.members.members.includes(u);
                          return (
                            <label key={`${p.project_id}-member-${u}`} className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={kbSaving}
                                onChange={(e) => {
                                  setKbProjects((prev) =>
                                    prev.map((x) => {
                                      if (x.project_id !== p.project_id) return x;
                                      if (e.target.checked) {
                                        const nextMembers = Array.from(new Set([...x.members.members, u]));
                                        const nextLeads = x.members.leads.filter((m) => m !== u);
                                        return { ...x, members: { ...x.members, leads: nextLeads, members: nextMembers } };
                                      }
                                      const nextMembers = x.members.members.filter((m) => m !== u);
                                      return { ...x, members: { ...x.members, members: nextMembers } };
                                    })
                                  );
                                }}
                                className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                              />
                              {u}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Private owners */}
        <div className="mb-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm text-zinc-200">Private owner</h3>
            <button
              type="button"
              disabled={kbSaving}
              onClick={handleSavePrivateOwners}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存 Private owner"}
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {kbPrivateOwners.length === 0 ? (
              <p className="text-sm text-zinc-500">暂无 private collection 数据</p>
            ) : (
              kbPrivateOwners.map((it) => (
                <div key={it.private_collection_id} className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-[220px]">
                    <div className="text-xs text-zinc-400">Private collection</div>
                    <div className="text-sm text-zinc-200">{it.name || it.private_collection_id}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-xs text-zinc-400">Owner</div>
                    <select
                      value={it.owner_username || ""}
                      disabled={kbSaving}
                      onChange={(e) =>
                        setKbPrivateOwners((prev) =>
                          prev.map((x) => (x.private_collection_id === it.private_collection_id ? { ...x, owner_username: e.target.value } : x))
                        )
                      }
                      className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
                    >
                      <option value="">未指定</option>
                      {usernameOptions.map((u) => (
                        <option key={`owner-${it.private_collection_id}-${u}`} value={u}>
                          {u}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Resource assignments */}
        <div className="rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm text-zinc-200">doc/table -&gt; collection 分配</h3>
            <button
              type="button"
              disabled={kbSaving}
              onClick={handleSaveResourceAssignments}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存 分配"}
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
              <div className="text-xs text-zinc-400 mb-2">Documents（多选）</div>
              <div className="space-y-3">
                {kbResourceAssignments.docs.length === 0 ? (
                  <p className="text-sm text-zinc-500">暂无 docs</p>
                ) : (
                  kbResourceAssignments.docs.map((d) => (
                    <div key={d.doc_id} className="rounded border border-zinc-800 bg-zinc-950/20 p-3">
                      <div className="text-sm text-zinc-200 mb-2">{d.title || d.doc_id}</div>
                      <div className="flex flex-wrap gap-3">
                        {kbCollections.map((c) => {
                          const checked = (d.collection_ids || []).includes(c.collection_id);
                          return (
                            <label key={`doc-${d.doc_id}-c-${c.collection_id}`} className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={kbSaving}
                                onChange={(e) => {
                                  const next = new Set(d.collection_ids || []);
                                  if (e.target.checked) next.add(c.collection_id);
                                  else next.delete(c.collection_id);
                                  setKbResourceAssignments((prev) => ({
                                    ...prev,
                                    docs: prev.docs.map((x) => (x.doc_id === d.doc_id ? { ...x, collection_ids: Array.from(next) } : x)),
                                  }));
                                }}
                                className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                              />
                              {formatCollectionLabel(c.collection_id)}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
              <div className="text-xs text-zinc-400 mb-2">Tables（单选）</div>
              <div className="space-y-3">
                {kbResourceAssignments.tables.length === 0 ? (
                  <p className="text-sm text-zinc-500">暂无 tables</p>
                ) : (
                  kbResourceAssignments.tables.map((t) => {
                    const selected = (t.collection_ids || [])[0] || "";
                    return (
                      <div key={t.table_id} className="rounded border border-zinc-800 bg-zinc-950/20 p-3">
                        <div className="text-sm text-zinc-200 mb-2">{t.name || t.table_id}</div>
                        <select
                          value={selected}
                          disabled={kbSaving}
                          onChange={(e) => {
                            const v = e.target.value;
                            setKbResourceAssignments((prev) => ({
                              ...prev,
                              tables: prev.tables.map((x) => (x.table_id === t.table_id ? { ...x, collection_ids: v ? [v] : [] } : x)),
                            }));
                          }}
                          className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
                        >
                          <option value="">未分配</option>
                          {kbCollections.map((c) => (
                            <option key={`table-${t.table_id}-c-${c.collection_id}`} value={c.collection_id}>
                            {formatCollectionLabel(c.collection_id)}
                            </option>
                          ))}
                        </select>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Resource owners */}
        <div className="mt-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm text-zinc-200">资源 owner（默认 owner 可改）</h3>
            <button
              type="button"
              disabled={kbSaving}
              onClick={handleSaveResourceOwners}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存 owner"}
            </button>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
              <div className="text-xs text-zinc-400 mb-2">Documents owner</div>
              <div className="space-y-3">
                {kbResourceOwners.docs.length === 0 ? (
                  <p className="text-sm text-zinc-500">暂无 docs</p>
                ) : (
                  kbResourceOwners.docs.map((d) => (
                    <div key={`owner-doc-${d.doc_id}`} className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-[220px]">
                        <div className="text-sm text-zinc-200">{d.title || d.doc_id}</div>
                        <div className="text-xs text-zinc-500">{d.doc_id}</div>
                      </div>
                      <select
                        value={d.owner_username || ""}
                        disabled={kbSaving}
                        onChange={(e) =>
                          setKbResourceOwners((prev) => ({
                            ...prev,
                            docs: prev.docs.map((x) => (x.doc_id === d.doc_id ? { ...x, owner_username: e.target.value } : x)),
                          }))
                        }
                        className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
                      >
                        <option value="">未指定</option>
                        {usernameOptions.map((u) => (
                          <option key={`owner-doc-${d.doc_id}-${u}`} value={u}>
                            {u}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))
                )}
              </div>
            </div>
            <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
              <div className="text-xs text-zinc-400 mb-2">Tables owner</div>
              <div className="space-y-3">
                {kbResourceOwners.tables.length === 0 ? (
                  <p className="text-sm text-zinc-500">暂无 tables</p>
                ) : (
                  kbResourceOwners.tables.map((t) => (
                    <div key={`owner-table-${t.table_id}`} className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-[220px]">
                        <div className="text-sm text-zinc-200">{t.name || t.table_id}</div>
                        <div className="text-xs text-zinc-500">{t.table_id}</div>
                      </div>
                      <select
                        value={t.owner_username || ""}
                        disabled={kbSaving}
                        onChange={(e) =>
                          setKbResourceOwners((prev) => ({
                            ...prev,
                            tables: prev.tables.map((x) => (x.table_id === t.table_id ? { ...x, owner_username: e.target.value } : x)),
                          }))
                        }
                        className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
                      >
                        <option value="">未指定</option>
                        {usernameOptions.map((u) => (
                          <option key={`owner-table-${t.table_id}-${u}`} value={u}>
                            {u}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* KB permissions */}
        <div className="mt-6 rounded-md border border-zinc-800 bg-zinc-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm text-zinc-200">知识库权限（可读 / 可写）</h3>
            <button
              type="button"
              disabled={kbSaving || overridesLoading || !overridesUsername.trim()}
              onClick={saveUserKbPermissions}
              className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {kbSaving ? "保存中…" : "保存 权限"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-xs text-zinc-400">用户</span>
            <select
              value={overridesUsername}
              disabled={kbSaving}
              onChange={async (e) => {
                const un = e.target.value;
                setOverridesUsername(un);
                setKbPermReadAllow([]);
                setKbPermWriteAllow([]);
                if (un) await loadUserKbPermissions(un);
              }}
              className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
            >
              <option value="">请选择</option>
              {usernameOptions.map((u) => (
                <option key={`ov-user-${u}`} value={u}>
                  {u}
                </option>
              ))}
            </select>
            {overridesLoading && <span className="text-xs text-zinc-500">加载中…</span>}
          </div>
          <div className="mt-3">
            <div className="mb-2 text-xs text-zinc-400">按知识库勾选（doc/table 不单独设置，跟随归属知识库）</div>
            <div className="space-y-2">
              {kbCollections.map((c) => {
                const cid = c.collection_id;
                const readChecked = kbPermReadAllow.includes(cid);
                const writeChecked = kbPermWriteAllow.includes(cid);
                return (
                  <div
                    key={`kbperm-${cid}`}
                    className="flex flex-wrap items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950/10 px-3 py-2"
                  >
                    <div className="text-xs text-zinc-300">{formatCollectionLabel(cid)}</div>
                    <div className="flex items-center gap-4">
                      <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                        <input
                          type="checkbox"
                          checked={readChecked}
                          disabled={kbSaving || !overridesUsername.trim()}
                          onChange={(e) => {
                            const next = new Set(kbPermReadAllow);
                            if (e.target.checked) next.add(cid);
                            else next.delete(cid);
                            setKbPermReadAllow(Array.from(next));
                          }}
                          className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                        />
                        可读
                      </label>
                      <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                        <input
                          type="checkbox"
                          checked={writeChecked}
                          disabled={kbSaving || !overridesUsername.trim()}
                          onChange={(e) => {
                            const next = new Set(kbPermWriteAllow);
                            if (e.target.checked) next.add(cid);
                            else next.delete(cid);
                            setKbPermWriteAllow(Array.from(next));
                          }}
                          className="h-4 w-4 rounded border border-zinc-600 bg-zinc-800"
                        />
                        可写
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
