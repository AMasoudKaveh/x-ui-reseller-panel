export type AuthRole =
  | "admin"
  | "reseller";


export type AuthUser = {
  username: string;
  role: AuthRole;
};


type AuthResponse = {
  ok: boolean;

  user: AuthUser;
};


async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {

  const response = await fetch(
    url,
    {
      credentials: "include",

      ...options,

      headers: {
        "Content-Type": "application/json",
        ...(options?.headers || {}),
      },
    },
  );


  if (!response.ok) {

    let message = "Request failed";

    try {

      const body = await response.json();

      message =
        body.detail ||
        message;

    } catch {
      //
    }


    throw new Error(message);
  }


  return response.json() as Promise<T>;
}


export async function loginAdmin(
  username: string,
  password: string,
): Promise<AuthUser> {

  const result =
    await request<AuthResponse>(
      "/api/auth/admin/login",
      {
        method: "POST",

        body: JSON.stringify({
          username,
          password,
        }),
      },
    );


  return result.user;
}


export async function loginReseller(
  username: string,
  password: string,
): Promise<AuthUser> {

  const result =
    await request<AuthResponse>(
      "/api/auth/reseller/login",
      {
        method: "POST",

        body: JSON.stringify({
          username,
          password,
        }),
      },
    );


  return result.user;
}


export async function getCurrentUser():
Promise<AuthUser | null> {

  try {

    const result =
      await request<AuthResponse>(
        "/api/auth/me",
      );

    return result.user;

  } catch {

    return null;
  }
}


export async function logout():
Promise<void> {

  try {

    await request<{ ok: boolean }>(
      "/api/auth/logout",
      {
        method: "POST",
      },
    );

  } catch {

    // حتی اگر Backend در دسترس نبود
    // UI از حساب خارج می‌شود
  }
}
