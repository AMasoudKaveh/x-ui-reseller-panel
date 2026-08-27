export type LiveAdminInbound = {
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

export async function getLiveAdminInbounds(): Promise<LiveAdminInbound[]> {
  const response = await fetch("/api/admin/inbounds", {
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
        `Unable to load inbounds (${response.status})`,
      ),
    );
  }

  return Array.isArray(data?.inbounds)
    ? data.inbounds
    : [];
}
