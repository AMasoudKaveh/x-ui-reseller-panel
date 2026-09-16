export type UpdateState = {
  status?: string;
  tag?: string;
  message?: string;
  commit?: string;
  updated_at?: string;
};

export type SystemUpdateStatus = {
  current_version: string;
  current_commit: string;
  latest_version: string | null;
  tag?: string;
  name?: string;
  available: boolean;
  published_at?: string;
  changelog?: string;
  release_url: string;
  update_command: string;
  checked_at: string;
  check_error?: string | null;
  message?: string;
  update_state?: UpdateState | null;
};

export async function getSystemUpdateStatus(refresh = false): Promise<SystemUpdateStatus> {
  const response = await fetch(`/api/admin/system/update-status${refresh ? "?refresh=true" : ""}`, {
    credentials: "include"
  });
  const text = await response.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch {}
  if (!response.ok) throw new Error(data?.detail || `Update check failed (${response.status})`);
  return data;
}
