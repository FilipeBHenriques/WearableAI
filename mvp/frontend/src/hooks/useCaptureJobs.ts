import { useCallback, useEffect, useRef, useState } from "react";
import { fetchActiveCaptureJobs } from "../api/notesApi";
import type { CaptureJob } from "../types/note";

type AppEventHandlers = {
  onJobUpdated?: (job: CaptureJob) => void | Promise<void>;
  onNotesChanged?: () => void | Promise<void>;
  onLocationsChanged?: () => void | Promise<void>;
};

const ACTIVE_STATUSES = new Set([
  "recording",
  "transcribing",
  "saved_raw",
  "enriching",
  "failed",
]);

function jobSignature(job: CaptureJob) {
  return [
    job.status,
    job.final_transcript ?? "",
    job.note_id ?? "",
    job.error ?? "",
    job.updated_at,
  ].join("|");
}

export function useCaptureJobs(handlers: AppEventHandlers = {}) {
  const [jobs, setJobs] = useState<CaptureJob[]>([]);
  const handlersRef = useRef(handlers);
  const signaturesRef = useRef<Map<number, string>>(new Map());
  const jobsRef = useRef<Map<number, CaptureJob>>(new Map());

  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  const applyJob = useCallback((job: CaptureJob) => {
    const signature = jobSignature(job);
    const previous = signaturesRef.current.get(job.id);
    if (previous !== signature) {
      signaturesRef.current.set(job.id, signature);
      void handlersRef.current.onJobUpdated?.(job);
    }

    if (ACTIVE_STATUSES.has(job.status)) {
      jobsRef.current.set(job.id, job);
    } else {
      jobsRef.current.delete(job.id);
      signaturesRef.current.delete(job.id);
    }

    setJobs(Array.from(jobsRef.current.values()).sort((a, b) => b.id - a.id));
  }, []);

  const reloadJobs = useCallback(async () => {
    try {
      const activeJobs = await fetchActiveCaptureJobs();
      const nextSignatures = new Map<number, string>();
      const nextJobs = new Map<number, CaptureJob>();

      activeJobs.forEach((job) => {
        const signature = jobSignature(job);
        nextSignatures.set(job.id, signature);
        nextJobs.set(job.id, job);

        if (signaturesRef.current.get(job.id) !== signature) {
          void handlersRef.current.onJobUpdated?.(job);
        }
      });

      jobsRef.current.forEach((job, id) => {
        if (!nextJobs.has(id) && job.status !== "failed") {
          void handlersRef.current.onJobUpdated?.({ ...job, status: "ready" });
        }
      });

      signaturesRef.current = nextSignatures;
      jobsRef.current = nextJobs;
      setJobs(activeJobs);
    } catch {
      // Backend unavailable - keep last known active queue.
    }
  }, []);

  useEffect(() => {
    reloadJobs();
  }, [reloadJobs]);

  useEffect(() => {
    let source: EventSource | null = null;
    let closed = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      if (closed) return;
      source = new EventSource("/api/events");

      source.addEventListener("connected", () => {
        void reloadJobs();
      });

      source.addEventListener("capture_job", (event) => {
        try {
          const job = JSON.parse((event as MessageEvent).data) as CaptureJob;
          applyJob(job);
        } catch {
          // Ignore malformed payloads.
        }
      });

      source.addEventListener("notes_changed", () => {
        void handlersRef.current.onNotesChanged?.();
      });

      source.addEventListener("locations_changed", () => {
        void handlersRef.current.onLocationsChanged?.();
      });

      source.onerror = () => {
        source?.close();
        source = null;
        if (closed) return;
        window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      closed = true;
      window.clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [applyJob, reloadJobs]);

  return { jobs, reloadJobs };
}
