export type AdminDashboardRepresentative = {
  id: number;
  username: string;
  quota_bytes: number;
  used_bytes: number;
  remaining_bytes: number;
  users: number;
  online: number;
  status: "Active" | "Suspended";
  raw_status: string;
  quota_locked: boolean;
};

export type AdminDashboardInbound = {
  id: number;
  name: string;
  label: string;
  node: string;
  port: number;
  protocol: string;
  network: string;
  security: string;
  enabled: boolean;
  clients: number;
  online: number;
  traffic_bytes: number;
  speed_bps: number;
};

export type AdminDashboardTrendPoint = {
  date: string;
  bytes: number;
};

export type AdminDashboardData = {
  summary: {
    representatives: number;
    active: number;
    suspended: number;
    clients: number;
    online: number;
    quota_bytes: number;
    used_bytes: number;
    remaining_bytes: number;
    inbounds: number;
    available_inbounds: number;
  };
  representatives: AdminDashboardRepresentative[];
  inbounds: AdminDashboardInbound[];
  inbounds_live: boolean;
  trend: AdminDashboardTrendPoint[];
};

export async function getAdminDashboard(): Promise<AdminDashboardData> {
  const response = await fetch("/api/admin/dashboard", {
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
    },
  });

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw new Error(
      String(
        data?.detail ||
        data?.message ||
        `Unable to load admin dashboard (${response.status})`,
      ),
    );
  }

  return {
    summary: data?.summary || {
      representatives: 0,
      active: 0,
      suspended: 0,
      clients: 0,
      online: 0,
      quota_bytes: 0,
      used_bytes: 0,
      remaining_bytes: 0,
      inbounds: 0,
      available_inbounds: 0,
    },
    representatives: Array.isArray(data?.representatives)
      ? data.representatives
      : [],
    inbounds: Array.isArray(data?.inbounds)
      ? data.inbounds
      : [],
    inbounds_live: Boolean(data?.inbounds_live),
    trend: Array.isArray(data?.trend)
      ? data.trend
      : [],
  };
}
