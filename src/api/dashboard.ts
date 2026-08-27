export type DashboardSystem = {
  cpu_percent: number;
  cpu_cores: number;

  ram_used_bytes: number;
  ram_total_bytes: number;
  ram_percent: number;

  disk_used_bytes: number;
  disk_total_bytes: number;
  disk_percent: number;

  network_upload_bytes: number;
  network_download_bytes: number;
  network_total_bytes: number;

  uptime_seconds: number;
};


export type DashboardUsers = {
  total: number;
  active: number;
  online: number;
  expired: number;
  limited: number;
  on_hold: number;
  disabled: number;
};


export type DashboardUsagePoint = {
  date: string;
  label: string;
  bytes: number;
};


export type ResellerDashboard = {
  reseller: {
    id: number;
    username: string;
    status: string;

    quota_bytes: number;
    used_bytes: number;
    remaining_bytes: number;
    quota_percent: number;
  };

  system: DashboardSystem;

  users: DashboardUsers;

  usage: DashboardUsagePoint[];
};


type DashboardResponse = {
  ok: boolean;
  dashboard: ResellerDashboard;
};


export async function
getResellerDashboard():
Promise<ResellerDashboard> {

  const response = await fetch(
    "/api/reseller/dashboard",
    {
      method: "GET",

      credentials: "include",

      headers: {
        Accept: "application/json"
      }
    }
  );


  if (!response.ok) {


    if (
      response.status === 401
      || response.status === 403
    ) {
      window.location.hash = "#/reseller/login";
    }

let message =
      "Failed to load dashboard";


    try {

      const body =
        await response.json();


      if (
        body
        &&
        body.detail
      ) {

        message =
          body.detail;
      }

    } catch {
      //
    }


    throw new Error(
      message
    );
  }


  const result: DashboardResponse =
    await response.json();


  return result.dashboard;
}
