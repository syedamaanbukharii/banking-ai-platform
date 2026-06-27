// Thin API client. Tokens are kept in memory for the session; the backend also
// sets HttpOnly cookies on login, which the browser sends automatically.
export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Login failed");
  return res.json();
}

export async function getReviewQueue(token: string) {
  const res = await fetch("/api/v1/workflows", {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load review queue");
  return res.json();
}

export async function decide(
  token: string,
  workflowId: string,
  action: "approve" | "reject" | "escalate",
  reason: string,
) {
  const res = await fetch(`/api/v1/workflows/${workflowId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ reason }),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Failed to ${action}`);
  return res.json();
}
