"use client";

import { useState } from "react";
import { decide, getReviewQueue, login } from "@/lib/api";

type Workflow = {
  id: string;
  workflow_type: string;
  status: string;
  created_at: string;
};

/**
 * Minimal operator console (scaffold). Demonstrates the human-in-the-loop path:
 * sign in, list workflows awaiting approval, and approve/reject them. A full
 * frontend (document upload, search, audit views, dashboards) is intentionally
 * out of scope for this pass — see docs/architecture.md.
 */
export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("admin@local.dev");
  const [password, setPassword] = useState("Admin123!Local");
  const [queue, setQueue] = useState<Workflow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setError(null);
    try {
      const tokens = await login(email, password);
      setToken(tokens.access_token);
      const data = await getReviewQueue(tokens.access_token);
      setQueue(data.items ?? []);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleDecision(id: string, action: "approve" | "reject") {
    if (!token) return;
    await decide(token, id, action, `${action} via console`);
    const data = await getReviewQueue(token);
    setQueue(data.items ?? []);
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Banking AI — Operator Console</h1>
      <p className="mt-1 text-sm text-slate-500">
        Human-in-the-loop review of agent-assisted workflows.
      </p>

      {!token ? (
        <section className="mt-6 space-y-3 rounded-lg border bg-white p-6 shadow-sm">
          <input
            className="w-full rounded border px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
          />
          <input
            className="w-full rounded border px-3 py-2"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password"
          />
          <button
            className="rounded bg-slate-900 px-4 py-2 text-white"
            onClick={handleLogin}
          >
            Sign in
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </section>
      ) : (
        <section className="mt-6 space-y-3">
          <h2 className="text-lg font-medium">Awaiting approval</h2>
          {queue.length === 0 && (
            <p className="text-sm text-slate-500">Nothing in the queue.</p>
          )}
          {queue.map((wf) => (
            <div
              key={wf.id}
              className="flex items-center justify-between rounded-lg border bg-white p-4 shadow-sm"
            >
              <div>
                <p className="font-medium">{wf.workflow_type}</p>
                <p className="text-xs text-slate-500">{wf.id}</p>
              </div>
              <div className="space-x-2">
                <button
                  className="rounded bg-emerald-600 px-3 py-1 text-white"
                  onClick={() => handleDecision(wf.id, "approve")}
                >
                  Approve
                </button>
                <button
                  className="rounded bg-red-600 px-3 py-1 text-white"
                  onClick={() => handleDecision(wf.id, "reject")}
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
    </main>
  );
}
