export type AdminRepresentativeStatus =
  | "Active"
  | "Suspended";

export type AdminRepresentative = {
  id: number;
  username: string;
  quota_bytes: number;
  used_bytes: number;
  users: number;
  online: number;
  status: AdminRepresentativeStatus;
  raw_status: string;
  quota_locked: boolean;
  inbound_ids: number[];
  created_at: string;
  updated_at: string;
};

export type AdminInbound = {
  id: number;
  name: string;
  label: string;
  port: number;
  protocol: string;
  network: string;
  security: string;
  enabled: boolean;
};

export type RepresentativeInput = {
  username: string;
  password?: string;
  quota_bytes: number;
  status: AdminRepresentativeStatus;
  inbound_ids: number[];
};

async function api<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const rawDetail = data?.detail ?? data?.message;

    let detail = `Request failed (${response.status})`;

    if (typeof rawDetail === "string" && rawDetail.trim()) {
      detail = rawDetail.trim();
    } else if (Array.isArray(rawDetail)) {
      const messages = rawDetail
        .map((item: any) => {
          if (typeof item === "string") return item;
          const msg = String(item?.msg || item?.message || "").trim();
          const loc = Array.isArray(item?.loc)
            ? item.loc.filter((part: unknown) => part !== "body").join(" → ")
            : "";
          return [loc, msg].filter(Boolean).join(": ");
        })
        .filter(Boolean);

      if (messages.length) {
        detail = messages.join(" · ");
      }
    } else if (rawDetail && typeof rawDetail === "object") {
      detail = String(rawDetail.message || rawDetail.msg || detail);
    }

    throw new Error(detail);
  }

  return data as T;
}

export type AdminRepresentativesData = {
  representatives: AdminRepresentative[];
  archived_used_bytes: number;
};

export async function getAdminRepresentatives(): Promise<AdminRepresentativesData> {
  const data = await api<{
    ok: boolean;
    representatives: AdminRepresentative[];
    archived_used_bytes?: number;
  }>("/api/admin/representatives");

  return {
    representatives: data.representatives || [],
    archived_used_bytes: Number(data.archived_used_bytes || 0),
  };
}

export async function getAdminInbounds(): Promise<AdminInbound[]> {
  const data = await api<{
    ok: boolean;
    inbounds: AdminInbound[];
  }>("/api/admin/inbounds");

  return data.inbounds || [];
}

export async function createAdminRepresentative(
  input: RepresentativeInput & { password: string },
): Promise<AdminRepresentative> {
  const data = await api<{
    ok: boolean;
    representative: AdminRepresentative;
  }>("/api/admin/representatives", {
    method: "POST",
    body: JSON.stringify(input),
  });

  return data.representative;
}

export async function updateAdminRepresentative(
  id: number,
  input: RepresentativeInput,
): Promise<AdminRepresentative> {
  const data = await api<{
    ok: boolean;
    representative: AdminRepresentative;
  }>(`/api/admin/representatives/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

  return data.representative;
}

export async function setAdminRepresentativeStatus(
  id: number,
  status: AdminRepresentativeStatus,
): Promise<AdminRepresentative> {
  const data = await api<{
    ok: boolean;
    representative: AdminRepresentative;
  }>(`/api/admin/representatives/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });

  return data.representative;
}

export async function resetAdminRepresentativeUsage(
  id: number,
): Promise<AdminRepresentative> {
  const data = await api<{
    ok: boolean;
    representative: AdminRepresentative;
  }>(`/api/admin/representatives/${id}/reset-usage`, {
    method: "POST",
    body: JSON.stringify({}),
  });

  return data.representative;
}

export async function deleteAdminRepresentative(
  id: number,
): Promise<void> {
  await api<{ ok: boolean }>(`/api/admin/representatives/${id}`, {
    method: "DELETE",
  });
}
