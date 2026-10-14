import { apiRequest } from "../../api/client";
export type Account = {
  id: string;
  username: string;
  role: "admin" | "operator" | "viewer";
  enabled?: boolean;
};
export type AccessStatus = {
  enabled: boolean;
  user: Account | null;
  passkey_configured: boolean;
};
const send = <T>(path: string, body = {}, method = "POST") =>
  apiRequest<T>("/api/v1/auth" + path, { method, body: JSON.stringify(body) });
export const accessApi = {
  status: () => apiRequest<AccessStatus>("/api/v1/auth/status"),
  login: (username: string, password: string) =>
    send<Account>("/login", { username, password }),
  setup: (username: string, password: string) =>
    send<Account>("/setup", { username, password }),
  logout: () => send("/logout"),
  users: () => apiRequest<Account[]>("/api/v1/auth/users"),
  addUser: (username: string, password: string, role: string) =>
    send<Account>("/users", { username, password, role }),
  updateUser: (
    id: string,
    body: { enabled: boolean; role: string; password?: string },
  ) => send<Account>("/users/" + id, body, "PUT"),
  tokens: () =>
    apiRequest<
      { id: string; name: string; scope: string; expires_at: string }[]
    >("/api/v1/auth/tokens"),
  token: (name: string, scope: string, days: number) =>
    send<{ token: string }>("/tokens", { name, scope, days }),
  revoke: (id: string) => send("/tokens/" + id, {}, "DELETE"),
  config: () =>
    apiRequest<{ origin: string; rp_id: string }>(
      "/api/v1/auth/passkeys/config",
    ),
  saveConfig: (origin: string) => send("/passkeys/config", { origin }, "PUT"),
  passkeys: () =>
    apiRequest<{ id: string; name: string }[]>("/api/v1/auth/passkeys"),
  removePasskey: (id: string) =>
    send("/passkeys/" + encodeURIComponent(id), {}, "DELETE"),
};

function decode(value: string): ArrayBuffer {
  const raw = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0)).buffer;
}
function encode(value: ArrayBuffer | null): string | null {
  if (value === null) return null;
  return btoa(String.fromCharCode(...new Uint8Array(value)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
export async function usePasskey(register: boolean, name = "Passkey") {
  if (!window.isSecureContext || !navigator.credentials)
    throw new Error("Passkey 需要 HTTPS 域名或 localhost。");
  const mode = register ? "register" : "login";
  const result = await send<{
    challenge_id: string;
    options: Record<string, unknown>;
  }>(`/passkeys/${mode}/options`);
  const publicKey = {
    ...result.options,
    challenge: decode(result.options.challenge as string),
  } as Record<string, unknown>;
  for (const key of ["excludeCredentials", "allowCredentials"]) {
    if (Array.isArray(publicKey[key]))
      publicKey[key] = (publicKey[key] as { id: string }[]).map((c) => ({
        ...c,
        id: decode(c.id),
      }));
  }
  if (register) {
    const user = publicKey.user as { id: string };
    publicKey.user = { ...user, id: decode(user.id) };
  }
  const credential = (
    register
      ? await navigator.credentials.create({
          publicKey: publicKey as unknown as PublicKeyCredentialCreationOptions,
        })
      : await navigator.credentials.get({
          publicKey: publicKey as unknown as PublicKeyCredentialRequestOptions,
        })
  ) as PublicKeyCredential | null;
  if (!credential) throw new Error("Passkey 操作已取消");
  const response = credential.response;
  const serialized = register
    ? {
        clientDataJSON: encode(response.clientDataJSON),
        attestationObject: encode(
          (response as AuthenticatorAttestationResponse).attestationObject,
        ),
        transports: (
          response as AuthenticatorAttestationResponse
        ).getTransports(),
      }
    : {
        clientDataJSON: encode(response.clientDataJSON),
        authenticatorData: encode(
          (response as AuthenticatorAssertionResponse).authenticatorData,
        ),
        signature: encode(
          (response as AuthenticatorAssertionResponse).signature,
        ),
        userHandle: encode(
          (response as AuthenticatorAssertionResponse).userHandle,
        ),
      };
  return send<Account>(`/passkeys/${mode}/verify`, {
    challenge_id: result.challenge_id,
    name,
    credential: {
      id: credential.id,
      rawId: encode(credential.rawId),
      type: credential.type,
      response: serialized,
      clientExtensionResults: credential.getClientExtensionResults(),
      authenticatorAttachment: credential.authenticatorAttachment,
    },
  });
}
