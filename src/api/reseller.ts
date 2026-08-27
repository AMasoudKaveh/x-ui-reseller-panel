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
