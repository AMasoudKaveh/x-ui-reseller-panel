export type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  active: boolean;
  created_at: number;
  last_used_at: number | null;
  expires_at: number | null;
  revoked_at: number | null;
};

export type ApiKeyListResponse = {
  ok: boolean;
  keys: ApiKeyItem[];
  available_scopes: string[];
};

export type CreateApiKeyInput = {
  name: string;
  scopes?: string[];
  expires_in_days?: number;
};

export type CreatedApiKey = {
  id: number;
  name: string;
  token: string;
  key_prefix: string;
  scopes: string[];
  expires_at: number | null;
};

type CreateApiKeyResponse = {
  ok: boolean;
  api_key: CreatedApiKey;
  warning: string;
};

async function readError(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const body = await response.json();

    if (body?.detail) {
      return typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail);
    }

    if (body?.error?.message) {
      return body.error.message;
    }
  } catch {
    // Ignore invalid JSON error bodies.
  }

  return fallback;
}

function handleAuthFailure(response: Response) {
  if (
    response.status === 401 ||
    response.status === 403
  ) {
    window.location.hash =
      "#/reseller/login";
  }
}

export async function listApiKeys():
Promise<ApiKeyListResponse> {

  const response = await fetch(
    "/api/reseller/api-keys",
    {
      method: "GET",
      credentials: "include",
      headers: {
        Accept: "application/json"
      }
    }
  );

  if (!response.ok) {
    handleAuthFailure(response);

    throw new Error(
      await readError(
        response,
        "Failed to load API keys"
      )
    );
  }

  return response.json();
}

export async function createApiKey(
  input: CreateApiKeyInput
): Promise<CreateApiKeyResponse> {

  const response = await fetch(
    "/api/reseller/api-keys",
    {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(input)
    }
  );

  if (!response.ok) {
    handleAuthFailure(response);

    throw new Error(
      await readError(
        response,
        "Failed to create API key"
      )
    );
  }

  return response.json();
}

export async function revokeApiKey(
  keyId: number
): Promise<void> {

  const response = await fetch(
    `/api/reseller/api-keys/${keyId}/revoke`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json"
      }
    }
  );

  if (!response.ok) {
    handleAuthFailure(response);

    throw new Error(
      await readError(
        response,
        "Failed to revoke API key"
      )
    );
  }
}
