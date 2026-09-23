export type ResellerProfile = {
  id: number;
  username: string;
  role: "reseller";
  display_role: string;
  status: string;
  quota_bytes: number;
  used_bytes: number;
  remaining_bytes: number;
  usage_percent: number;
  total_users: number;
  subscription_brand: string;
};

type ProfileResponse = {
  ok: boolean;
  profile: ResellerProfile;
};

export async function getResellerProfile(): Promise<ResellerProfile> {
  const response = await fetch("/api/reseller/profile", {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json"
    }
  });

  if (!response.ok) {

    if (
      response.status === 401
      || response.status === 403
    ) {
      window.location.hash = "#/reseller/login";
    }

let message = "Failed to load reseller profile";

    try {
      const body = await response.json();

      if (body && body.detail) {
        message = body.detail;
      }
    } catch {
      // ignore invalid error body
    }

    throw new Error(message);
  }

  const result: ProfileResponse = await response.json();

  return result.profile;
}

export async function updateSubscriptionBrand(subscriptionBrand: string): Promise<string> {
  const response = await fetch("/api/reseller/settings/subscription-brand", {
    method: "PUT",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ subscription_brand: subscriptionBrand })
  });

  if (!response.ok) {
    let message = "Failed to save Subscription Brand";
    try {
      const body = await response.json();
      if (body?.detail) message = body.detail;
    } catch {
      // Keep the generic message for an invalid error body.
    }
    throw new Error(message);
  }

  const result: { ok: boolean; subscription_brand: string } = await response.json();
  return result.subscription_brand;
}
