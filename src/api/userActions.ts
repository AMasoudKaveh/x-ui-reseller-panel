export type UserActionDetail = {
  id: number;
  username: string;
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

export type ModifyUserPayload = {
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

export type UserAccessInfo = {
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
  if (!response.ok) {
    throw new Error(await readError(response, "Request failed"));
  }
  return response.json();
}

export async function getUserDetail(clientId: number): Promise<UserActionDetail> {
  const result = await request<{ ok: boolean; user: UserActionDetail }>(
    `/api/reseller/users/${clientId}/details`
  );
  return result.user;
}

export async function modifyUser(clientId: number, payload: ModifyUserPayload): Promise<void> {
  await request(`/api/reseller/users/${clientId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function getUserAccess(clientId: number): Promise<UserAccessInfo> {
  return request<UserAccessInfo>(`/api/reseller/users/${clientId}/access`);
}

export async function toggleUser(clientId: number, enabled: boolean): Promise<void> {
  await request(`/api/reseller/users/${clientId}/toggle`, {
    method: "POST",
    body: JSON.stringify({ enabled })
  });
}

export async function resetUserUsage(clientId: number): Promise<void> {
  await request(`/api/reseller/users/${clientId}/reset-usage`, { method: "POST" });
}

export async function revokeSubscription(clientId: number): Promise<void> {
  await request(`/api/reseller/users/${clientId}/revoke-subscription`, { method: "POST" });
}

export async function removeUser(clientId: number): Promise<void> {
  await request(`/api/reseller/users/${clientId}`, { method: "DELETE" });
}
