export type ResellerUserStatus =
  | "active"
  | "disabled"
  | "expired"
  | "hold";


export type ResellerUser = {

  id: number;

  username: string;

  customer_name:
    string | null;

  service_type: string;

  status: string;

  status_code:
    ResellerUserStatus;

  enabled: boolean;

  online: boolean;

  inbound_ids: number[];

  limit_ip: number;

  traffic_limit_bytes: number;

  used_bytes: number;

  total_used_bytes: number;

  usage_percent: number;

  expire_at_ms: number;

  expires_in: string;

  created_at: string;

  updated_at: string;

  age: string;

  last_online_at:
    string | null;

  comment:
    string | null;
};


export type UsersSummary = {

  total: number;

  active: number;

  online: number;

  disabled: number;

  expired: number;

  on_hold: number;
};


export type ResellerUsersResult = {

  summary:
    UsersSummary;

  users:
    ResellerUser[];
};


type UsersResponse = {

  ok: boolean;

  summary:
    UsersSummary;

  users:
    ResellerUser[];
};


export async function
getResellerUsers():
Promise<ResellerUsersResult> {

  const response =
    await fetch(
      "/api/reseller/users",
      {
        method: "GET",

        credentials:
          "include",

        headers: {
          Accept:
            "application/json"
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
      "Failed to load users";


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


  const result: UsersResponse =
    await response.json();


  return {
    summary:
      result.summary,

    users:
      result.users
  };
}
