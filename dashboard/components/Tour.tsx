"use client";

import { useEffect, useState } from "react";
import { Question, CaretRight, CaretLeft, X } from "@phosphor-icons/react/dist/ssr";

import styles from "./Tour.module.css";

export interface TourStep {
  title: string;
  body: string;
}

/**
 * Lightweight guided tour: opens once on first visit (remembered in localStorage by `id`), and a
 * floating "Tour" button replays it. Purely presentational — it changes nothing in the workflow.
 */
export function Tour({ id, title, steps }: { id: string; title: string; steps: TourStep[] }) {
  const key = `sift_tour_${id}`;
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);

  useEffect(() => {
    try {
      if (!localStorage.getItem(key)) setOpen(true);
    } catch {
      /* localStorage unavailable — just don't auto-open */
    }
  }, [key]);

  function close() {
    try {
      localStorage.setItem(key, "seen");
    } catch {
      /* ignore */
    }
    setOpen(false);
    setI(0);
  }

  const step = steps[i];
  const last = i === steps.length - 1;

  return (
    <>
      <button
        className={styles.launch}
        onClick={() => {
          setI(0);
          setOpen(true);
        }}
        aria-label="Take the tour"
      >
        <Question size={15} weight="bold" /> Tour
      </button>

      {open && step && (
        <div className={styles.scrim} role="dialog" aria-modal="true" aria-label={`${title} tour`}>
          <div className={styles.card}>
            <div className={styles.head}>
              <span className={styles.kicker}>{title}</span>
              <button className={styles.x} onClick={close} aria-label="Close tour">
                <X size={16} />
              </button>
            </div>
            <h3 className={styles.title}>{step.title}</h3>
            <p className={styles.body}>{step.body}</p>
            <div className={styles.dots} aria-hidden>
              {steps.map((_, n) => (
                <span key={n} className={styles.dot} data-on={n === i} />
              ))}
            </div>
            <div className={styles.actions}>
              {i > 0 ? (
                <button className={styles.ghost} onClick={() => setI(i - 1)}>
                  <CaretLeft size={14} /> Back
                </button>
              ) : (
                <span />
              )}
              <span className={styles.count}>
                {i + 1} / {steps.length}
              </span>
              {last ? (
                <button className={styles.primary} onClick={close}>
                  Got it
                </button>
              ) : (
                <button className={styles.primary} onClick={() => setI(i + 1)}>
                  Next <CaretRight size={14} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
