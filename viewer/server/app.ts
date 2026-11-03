import express, { type NextFunction, type Request, type Response } from "express";
import { SaveRefused } from "../shared/api";
import type { ViewerConfig } from "./config";
import { loadSnapshot, saveFiles, type WriteOps } from "./store";

const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

function hostname(value: string): string {
  try {
    return new URL(value.includes("://") ? value : `http://${value}`).hostname;
  } catch {
    return "";
  }
}

/**
 * Local only. Binding 127.0.0.1 keeps other machines out; checking Host and
 * Origin keeps out web pages in the browser (DNS rebinding, cross-site POSTs).
 */
function localOnly(req: Request, res: Response, next: NextFunction) {
  const host = req.headers.host ?? "";
  const origin = req.headers.origin;
  if (!LOCAL_HOSTS.has(hostname(host)) || (origin !== undefined && !LOCAL_HOSTS.has(hostname(origin)))) {
    res.status(403).json({ error: "The viewer API only answers local requests." });
    return;
  }
  next();
}

export function createApp(config: ViewerConfig, ops?: WriteOps) {
  const app = express();
  app.disable("x-powered-by");
  app.use(localOnly);

  app.get("/api/snapshot", (_req, res) => {
    res.json(loadSnapshot(config));
  });

  // A full guard backfill is every item file at once: allow a large body.
  app.post("/api/save", express.json({ limit: "64mb" }), async (req, res, next) => {
    try {
      res.json(await saveFiles(config, req.body, ops));
    } catch (error) {
      if (error instanceof SaveRefused) {
        res.status(409).json({ error: error.message, problems: error.problems });
        return;
      }
      next(error);
    }
  });

  app.use("/api", (_req, res) => {
    res.status(404).json({ error: "Unknown API route." });
  });

  app.use((error: Error, _req: Request, res: Response, _next: NextFunction) => {
    console.error(error);
    res.status(500).json({ error: `Server error: ${error.message}` });
  });
  return app;
}
