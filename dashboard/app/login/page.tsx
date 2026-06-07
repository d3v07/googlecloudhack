"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Database, SignIn } from "@phosphor-icons/react/dist/ssr";

import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setError(
          res.status === 401
            ? "Invalid username or password."
            : "Sign-in is unavailable right now.",
        );
        setPending(false);
        return;
      }
      const data = (await res.json()) as { role: "user" | "dbre" };
      router.replace(data.role === "user" ? "/console" : "/dbre");
      router.refresh();
    } catch {
      setError("Network error — please try again.");
      setPending(false);
    }
  }

  return (
    <main className={styles.wrap}>
      <form className={styles.card} onSubmit={onSubmit}>
        <div className={styles.brand}>
          <Database weight="fill" size={26} />
          <span>DBRE Console</span>
        </div>
        <p className={styles.tagline}>
          Sign in to run database workloads, or to triage the slowest queries.
        </p>

        <label className={styles.field}>
          <span>Username</span>
          <input
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>

        <label className={styles.field}>
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <button type="submit" className={styles.submit} disabled={pending}>
          <SignIn size={18} weight="bold" />
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
