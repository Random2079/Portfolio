/*
 * Poll STT daemon for commands produced by global PTT (works while Discord unfocused).
 *
 * Chromium freezes/throttles setInterval when Discord is in the background (in-game).
 * We keep a near-silent AudioContext alive and also flush on visibility/focus.
 */

import { parseVoiceCommand, type VoiceCommand } from "./parseCommand";

const STT_BASE = "http://127.0.0.1:39281";
const POLL_MS = 400;

export interface GlobalCommandPollOptions {
    onCommand: (cmd: VoiceCommand, transcript: string) => void;
    onRaw?: (transcript: string, freeText: string) => void;
    onError?: (message: string) => void;
}

export class GlobalCommandPoller {
    private timer: number | null = null;
    private seen = new Set<number>();
    private busy = false;
    private tickCount = 0;
    private running = false;
    private audioCtx: AudioContext | null = null;
    private readonly opts: GlobalCommandPollOptions;
    private readonly onVis: () => void;
    private readonly onFocus: () => void;

    constructor(opts: GlobalCommandPollOptions) {
        this.opts = opts;
        this.onVis = () => {
            if (document.visibilityState === "visible") void this.tick();
        };
        this.onFocus = () => void this.tick();
    }

    start() {
        this.stop();
        this.running = true;
        this.armKeepAlive();
        document.addEventListener("visibilitychange", this.onVis);
        window.addEventListener("focus", this.onFocus);
        this.scheduleNext(0);
        // #region agent log
        fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
            body: JSON.stringify({
                sessionId: "121a69",
                runId: "post-fix",
                hypothesisId: "A2",
                location: "globalCommandPoll.ts:start",
                message: "poller_started_keepalive",
                data: { pollMs: POLL_MS },
                timestamp: Date.now()
            })
        }).catch(() => undefined);
        // #endregion
    }

    stop() {
        this.running = false;
        if (this.timer != null) {
            window.clearTimeout(this.timer);
            this.timer = null;
        }
        document.removeEventListener("visibilitychange", this.onVis);
        window.removeEventListener("focus", this.onFocus);
        try {
            void this.audioCtx?.close();
        } catch {
            /* ignore */
        }
        this.audioCtx = null;
    }

    /** Prevent Chromium from freezing background timers (Discord unfocused / in game). */
    private armKeepAlive() {
        try {
            const AC = window.AudioContext || (window as any).webkitAudioContext;
            if (!AC) return;
            const ctx: AudioContext = new AC();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            gain.gain.value = 0.00001;
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            this.audioCtx = ctx;
            void ctx.resume();
        } catch {
            /* ignore — poll still works when Discord focused */
        }
    }

    private scheduleNext(ms: number) {
        if (!this.running) return;
        this.timer = window.setTimeout(() => {
            void this.tick().finally(() => this.scheduleNext(POLL_MS));
        }, ms);
    }

    private async tick() {
        if (this.busy) return;
        this.busy = true;
        this.tickCount++;
        try {
            const ctrl = typeof AbortSignal !== "undefined" && "timeout" in AbortSignal
                ? { signal: AbortSignal.timeout(2000) }
                : {};
            const r = await fetch(`${STT_BASE}/commands/pending`, ctrl);
            if (!r.ok) {
                // #region agent log
                if (this.tickCount <= 3) {
                    fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
                        method: "POST",
                        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
                        body: JSON.stringify({
                            sessionId: "121a69",
                            runId: "post-fix",
                            hypothesisId: "A2",
                            location: "globalCommandPoll.ts:tick",
                            message: "pending_http_not_ok",
                            data: { status: r.status, tick: this.tickCount },
                            timestamp: Date.now()
                        })
                    }).catch(() => undefined);
                }
                // #endregion
                return;
            }
            const j = await r.json();
            const list = (j?.commands as any[]) || [];
            // #region agent log
            if (list.length > 0 || this.tickCount <= 2 || this.tickCount % 30 === 0) {
                fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
                    body: JSON.stringify({
                        sessionId: "121a69",
                        runId: "post-fix",
                        hypothesisId: "A2",
                        location: "globalCommandPoll.ts:tick",
                        message: "poll_ok",
                        data: {
                            tick: this.tickCount,
                            pending: list.length,
                            visible: document.visibilityState,
                            ids: list.map((x: any) => x?.id)
                        },
                        timestamp: Date.now()
                    })
                }).catch(() => undefined);
            }
            // #endregion
            const ackIds: number[] = [];

            for (const item of list) {
                const id = Number(item?.id);
                if (!Number.isFinite(id) || this.seen.has(id)) {
                    if (Number.isFinite(id)) ackIds.push(id);
                    continue;
                }
                this.seen.add(id);
                ackIds.push(id);

                const transcript = String(item?.transcript || "").trim();
                const free = String(item?.free_text || "").trim();
                if (!transcript) continue;

                this.opts.onRaw?.(transcript, free);
                const cmd = parseVoiceCommand(transcript);
                // #region agent log
                fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
                    body: JSON.stringify({
                        sessionId: "121a69",
                        runId: "post-fix",
                        hypothesisId: "B",
                        location: "globalCommandPoll.ts:parse",
                        message: cmd ? "parse_ok" : "parse_fail",
                        data: {
                            id,
                            transcript: transcript.slice(0, 120),
                            free: free.slice(0, 80),
                            action: cmd?.action ?? null,
                            slot: cmd?.slot ?? null
                        },
                        timestamp: Date.now()
                    })
                }).catch(() => undefined);
                // #endregion
                if (cmd) {
                    console.info("[VoiceMuteSlots] global PTT →", cmd.action, cmd.slot, transcript);
                    this.opts.onCommand(cmd, transcript);
                } else {
                    console.info("[VoiceMuteSlots] global PTT no parse:", transcript, "free=", free);
                    this.opts.onError?.(`Не распознал: «${transcript}»`);
                }
            }

            if (ackIds.length) {
                await fetch(`${STT_BASE}/commands/ack`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ids: ackIds }),
                    ...(typeof AbortSignal !== "undefined" && "timeout" in AbortSignal
                        ? { signal: AbortSignal.timeout(2000) }
                        : {})
                }).catch(() => undefined);
            }

            if (this.seen.size > 200) {
                const keep = [...this.seen].slice(-80);
                this.seen = new Set(keep);
            }
        } catch (err) {
            // #region agent log
            if (this.tickCount <= 5 || this.tickCount % 40 === 0) {
                fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
                    body: JSON.stringify({
                        sessionId: "121a69",
                        runId: "post-fix",
                        hypothesisId: "A2",
                        location: "globalCommandPoll.ts:tick",
                        message: "poll_error",
                        data: { tick: this.tickCount, err: String(err) },
                        timestamp: Date.now()
                    })
                }).catch(() => undefined);
            }
            // #endregion
        } finally {
            this.busy = false;
        }
    }
}
