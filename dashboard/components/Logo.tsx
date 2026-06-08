"use client";

import { useState } from "react";
import { Funnel } from "@phosphor-icons/react/dist/ssr";

/**
 * Brand logo. Renders /public/logo.svg — drop your own `logo.svg` there to swap the mark with no
 * code change. Falls back to a funnel glyph (a nod to "Sift") if the file is missing.
 */
export function Logo({ size = 22 }: { size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <Funnel weight="fill" size={size} color="var(--cyan)" />;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/logo.svg"
      alt=""
      width={size}
      height={size}
      onError={() => setFailed(true)}
      style={{ display: "block" }}
    />
  );
}
