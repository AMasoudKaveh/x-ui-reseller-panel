export type AdminClientRow = {
  id: number;
  username: string;
  owner: string;
  owner_id: number;
  status: string;
  enabled: boolean;
  online: boolean;
  expires_in: string;
  expire_at_ms: number;
  used_bytes: number;
  limit_bytes: number;
  usage_percent: number;
  inbound_ids: number[];
  inbound: string;
  age: string;
  created_at: string;
  updated_at: string;
  disable_reason: string;
  rep_quota_hold: boolean;
  own_limit_exhausted: boolean;
};

export type AdminClientsSummary = {
  total: number;
  active: number;
  online: number;
  disabled: number;
  expired: number;
};

export type AdminClientsResponse = {
  ok: boolean;
  poll_hint_ms: number;
  summary: AdminClientsSummary;
  clients: AdminClientRow[];
};

export type AdminClientDetail = {
  id: number;
  username: string;
  owner_id: number;
  owner: string;
  traffic_gb: number;
  expiry_date: string;
  start_after_first_use: boolean;
  start_after_days: number;
  enabled: boolean;
  comment: string;
  inbound_ids: number[];
  limit_ip: number;
  telegram_user_id: string;
  uuid: string;
  sub_id: string;
  panel_connected: boolean;
  panel_error: string;
};

export type AdminClientInbound = {
  id: number;
  name?: string;
  label?: string;
  remark?: string;
  port?: number;
  protocol?: string;
  network?: string;
  security?: string;
  enabled?: boolean;
};

export type ModifyAdminClientPayload = {
  traffic_gb: number;
  expiry_date: string;
  start_after_first_use: boolean;
  start_after_days: number;
  enabled: boolean;
  comment: string;
  inbound_ids: number[];
  limit_ip: number;
  telegram_user_id: string;
};

export type AdminClientAccess = {
  ok: boolean;
  username: string;
  uuid: string;
  sub_id: string;
  subscription_url: string;
  links: string[];
  configs: { name: string; link: string }[];
  qr_svg: string;
};

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return body.detail || body.error || fallback;
  } catch {
    return fallback;
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
      ...(options?.headers || {})
    }
  });

  if (response.status === 401) {
    if (window.location.hash.startsWith("#/admin")) {
      window.location.hash = "#/admin/login";
    }
  }

  if (!response.ok) {
    throw new Error(await readError(response, "Request failed"));
  }

  return response.json();
}

export function getAdminClients(): Promise<AdminClientsResponse> {
  return request<AdminClientsResponse>("/api/admin/clients");
}

export async function getAdminClientDetail(clientId: number): Promise<AdminClientDetail> {
  const result = await request<{ ok: boolean; user: AdminClientDetail }>(
    `/api/admin/clients/${clientId}/details`
  );
  return result.user;
}

export async function getAdminClientInbounds(clientId: number): Promise<AdminClientInbound[]> {
  const result = await request<{ ok: boolean; inbounds: AdminClientInbound[] }>(
    `/api/admin/clients/${clientId}/inbounds`
  );
  return result.inbounds || [];
}

export async function modifyAdminClient(clientId: number, payload: ModifyAdminClientPayload): Promise<void> {
  await request(`/api/admin/clients/${clientId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getAdminClientAccess(clientId: number): Promise<AdminClientAccess> {
  return request<AdminClientAccess>(`/api/admin/clients/${clientId}/access`);
}

export async function toggleAdminClient(clientId: number, enabled: boolean): Promise<void> {
  await request(`/api/admin/clients/${clientId}/toggle`, {
    method: "POST",
    body: JSON.stringify({ enabled })
  });
}

export async function resetAdminClientUsage(clientId: number): Promise<void> {
  await request(`/api/admin/clients/${clientId}/reset-usage`, { method: "POST" });
}

export async function revokeAdminClientSubscription(clientId: number): Promise<void> {
  await request(`/api/admin/clients/${clientId}/revoke-subscription`, { method: "POST" });
}

export async function removeAdminClient(clientId: number): Promise<void> {
  await request(`/api/admin/clients/${clientId}`, { method: "DELETE" });
}
