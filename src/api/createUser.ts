export type XuiInbound = {
  id: number;
  label: string;
  remark: string;
  port: number;
  protocol: string;
  network: string;
  security: string;
  enabled: boolean;
};


export type CreateUserPayload = {
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
};

export type BulkCreateUserPayload = {
  inbound_ids: number[];
  method: "random" | "sequential";
  username_prefix: string;
  number_of_clients: number;
  subscription_id: string;
  group: string;
  hwid_limit: number;
  comment: string;
  limit_ip: number;
  traffic_gb: number;
  start_after_first_use: boolean;
  duration_days: number;
  auto_renew: number;
  renew_on_day: number;
  max_renewals: number;
  traffic_reset: number;
  enabled: boolean;
};

export type BulkOperationResult = {
  ok: boolean;
  created: Array<{ id: number; username: string }>;
  errors: Array<{ username: string; detail: string }>;
};


type InboundsResponse = {
  ok: boolean;
  inbounds: XuiInbound[];
};


type CreateUserResponse = {
  ok: boolean;

  user: {
    id: number;
    username: string;
    uuid: string;
    sub_id: string;
    inbound_ids: number[];
    traffic_limit_bytes: number;
    expire_at_ms: number;
    enabled: boolean;
  };

  xui: {
    method: string | null;
    confirmed: boolean;
  };
};


async function errorMessage(
  response: Response,
  fallback: string,
): Promise<string> {

  try {

    const body = await response.json();

    return (
      body.detail
      ||
      body.error
      ||
      fallback
    );

  } catch {

    return fallback;
  }
}


export async function
getXuiInbounds():
Promise<XuiInbound[]> {

  const response = await fetch(
    "/api/reseller/inbounds",
    {
      credentials: "include",

      headers: {
        Accept: "application/json"
      }
    }
  );


  if (!response.ok) {

    throw new Error(
      await errorMessage(
        response,
        "Unable to load x-ui inbounds"
      )
    );
  }


  const result: InboundsResponse =
    await response.json();


  return result.inbounds;
}


export async function
createXuiUser(
  payload: CreateUserPayload
): Promise<CreateUserResponse> {

  const response = await fetch(
    "/api/reseller/users",
    {
      method: "POST",

      credentials: "include",

      headers: {
        "Content-Type":
          "application/json",

        Accept:
          "application/json"
      },

      body:
        JSON.stringify(payload)
    }
  );


  if (!response.ok) {

    throw new Error(
      await errorMessage(
        response,
        "Unable to create user"
      )
    );
  }


  const result: CreateUserResponse =
    await response.json();


  return result;
}

export async function createBulkXuiUsers(payload: BulkCreateUserPayload): Promise<BulkOperationResult> {
  const response = await fetch("/api/reseller/users/bulk", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await errorMessage(response, "Unable to create users"));
  return response.json();
}
