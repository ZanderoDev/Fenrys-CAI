import { spawn, ChildProcess } from "child_process";
import { EventEmitter } from "events";
import type { JsonRpcRequest, JsonRpcResponse, JsonRpcEvent, EventParams } from "../types.js";

export class GatewayClient extends EventEmitter {
  private process: ChildProcess;
  private requestId = 0;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private buffer = "";

  constructor(pythonPath: string, gatewayModule: string) {
    super();
    this.process = spawn(pythonPath, ["-m", gatewayModule], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.process.stdout?.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      const lines = this.buffer.split("\n");
      this.buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const msg = JSON.parse(line);
          this.handleMessage(msg);
        } catch {
          // Ignore parse errors for now
        }
      }
    });

    this.process.stderr?.on("data", (data: Buffer) => {
      const text = data.toString().trim();
      if (text) {
        this.emit("stderr", text);
      }
    });

    this.process.on("exit", (code) => {
      this.emit("exit", code);
    });
  }

  private handleMessage(msg: JsonRpcResponse | JsonRpcEvent): void {
    if ("id" in msg && msg.id !== undefined) {
      // Response to a request
      const handler = this.pending.get(msg.id);
      if (handler) {
        this.pending.delete(msg.id);
        if ("error" in msg && msg.error) {
          handler.reject(new Error(msg.error.message));
        } else {
          handler.resolve("result" in msg ? msg.result : null);
        }
      }
    } else if ("method" in msg && msg.method === "event") {
      // Event from server
      this.emit("event", (msg as JsonRpcEvent).params);
    }
  }

  async request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const id = ++this.requestId;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: resolve as (v: unknown) => void,
        reject,
      });

      const request: JsonRpcRequest = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

      this.process.stdin?.write(JSON.stringify(request) + "\n");
    });
  }

  async newSession(target?: string, mode?: string): Promise<{ session_id: string; target: string; mode: string }> {
    return this.request("session.new", { target: target || "", mode: mode || "CTF" });
  }

  async listSessions(): Promise<{ sessions: Array<{ id: string; target: string; mode: string; status: string }> }> {
    return this.request("session.list");
  }

  async getSession(sessionId: string): Promise<{ session: Record<string, unknown> }> {
    return this.request("session.get", { session_id: sessionId });
  }

  async deleteSession(sessionId: string): Promise<{ deleted: string }> {
    return this.request("session.delete", { session_id: sessionId });
  }

  sendPrompt(text: string, sessionId?: string): void {
    // Prompt is fire-and-forget, events come back asynchronously
    const id = ++this.requestId;
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id,
      method: "prompt",
      params: { text, session_id: sessionId },
    };
    this.process.stdin?.write(JSON.stringify(request) + "\n");
  }

  async ping(): Promise<{ pong: boolean; sessions: number }> {
    return this.request("ping");
  }

  async health(): Promise<Record<string, unknown>> {
    return this.request("health");
  }

  kill(): void {
    this.process.kill();
  }

  get pid(): number | undefined {
    return this.process.pid ?? undefined;
  }
}
