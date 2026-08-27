export type ConfigProxyOverride = {
  inbound_id: number;
  host: string;
  port: number;
  reality_sid: string;
};

export type AdminSettingsData = {
  username: string;
  config_overrides: ConfigProxyOverride[];
  subscription: {
    host: string;
    port: number;
    detected_port: number;
    effective_port: number;
    fallback_port: number;
  };
};

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  });
  const text = await response.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `Request failed (${response.status})`);
  }
  return data as T;
}

export async function getAdminSettings(): Promise<AdminSettingsData> {
  const result = await api<{ok: boolean} & AdminSettingsData>("/api/admin/settings");
  return result;
}

export async function saveConfigProxy(input: ConfigProxyOverride): Promise<void> {
  await api("/api/admin/settings/config-proxy", {
    method: "PUT",
    body: JSON.stringify(input)
  });
}

export async function removeConfigProxy(inboundId: number): Promise<void> {
  await api(`/api/admin/settings/config-proxy/${inboundId}`, { method: "DELETE" });
}

export async function saveSubscriptionProxy(host: string, port: number): Promise<void> {
  await api("/api/admin/settings/subscription-proxy", {
    method: "PUT",
    body: JSON.stringify({ host, port })
  });
}

export async function updateAdminCredentials(input: {
  current_password: string;
  username: string;
  new_password: string;
}): Promise<{username: string}> {
  return api("/api/admin/settings/credentials", {
    method: "PUT",
    body: JSON.stringify(input)
  });
}

export async function downloadAdminBackup(): Promise<void> {
  const response = await fetch("/api/admin/settings/backup", { credentials: "include" });
  if (!response.ok) {
    const text = await response.text();
    let message = `Backup failed (${response.status})`;
    try { message = JSON.parse(text)?.detail || message; } catch {}
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `xui-panel-backup-${Date.now()}.sqlite3`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function restoreAdminBackup(file: File): Promise<{relogin_required: boolean; safety_backup?: string}> {
  const response = await fetch("/api/admin/settings/restore", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const text = await response.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch {}
  if (!response.ok) throw new Error(data?.detail || `Restore failed (${response.status})`);
  return data;
}
