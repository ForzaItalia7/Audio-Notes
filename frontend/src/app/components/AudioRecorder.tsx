"use client";

import { useEffect, useRef, useState } from "react";

// Five minutes of mono 16 kHz PCM fits under the provider's 10 MB limit.
const MAX_SECONDS = 300;

async function toWav(blob: Blob): Promise<Blob> {
  const decoder = new AudioContext();
  try {
    const decoded = await decoder.decodeAudioData(await blob.arrayBuffer());
    if (decoded.duration > MAX_SECONDS + 2) throw new Error("Recording is too long. Please keep it under five minutes.");
    const renderer = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
    const source = renderer.createBufferSource();
    source.buffer = decoded;
    source.connect(renderer.destination);
    source.start();
    const samples = (await renderer.startRendering()).getChannelData(0);
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    function label(offset: number, value: string) {
      for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
    }
    label(0, "RIFF"); view.setUint32(4, buffer.byteLength - 8, true);
    label(8, "WAVE"); label(12, "fmt "); view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    label(36, "data"); view.setUint32(40, samples.length * 2, true);
    samples.forEach((sample, i) => {
      const value = Math.max(-1, Math.min(1, sample));
      view.setInt16(44 + i * 2, value < 0 ? value * 32768 : value * 32767, true);
    });
    return new Blob([buffer], { type: "audio/wav" });
  } finally {
    await decoder.close();
  }
}

export default function AudioRecorder({ onSelect, disabled }: { onSelect: (file: File) => void; disabled: boolean }) {
  const [phase, setPhase] = useState<"idle" | "requesting" | "recording" | "preparing">("idle");
  const [seconds, setSeconds] = useState(0);
  const [message, setMessage] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const audioPreview = useRef<HTMLAudioElement | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);
  const starting = useRef(false);

  function releaseMicrophone() {
    if (timer.current) clearInterval(timer.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (recorder.current) {
        recorder.current.onstop = null;
        recorder.current.ondataavailable = null;
        recorder.current.onerror = null;
        if (recorder.current.state !== "inactive") recorder.current.stop();
      }
      releaseMicrophone();
    };
  }, []);

  useEffect(() => {
    if (!file || !audioPreview.current) return;
    const url = URL.createObjectURL(file);
    audioPreview.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file, phase]);

  function stop() {
    if (recorder.current?.state === "recording") {
      setPhase("preparing");
      recorder.current.stop();
      releaseMicrophone();
    }
  }

  async function start() {
    if (starting.current || phase !== "idle") return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMessage("Recording is unavailable in this browser. Open the app on localhost or HTTPS, or upload an audio file.");
      return;
    }
    starting.current = true;
    setPhase("requesting");
    setMessage("");
    try {
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current) { microphone.getTracks().forEach((track) => track.stop()); return; }
      stream.current = microphone;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type));
      const active = new MediaRecorder(microphone, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 64000 });
      recorder.current = active;
      const chunks: Blob[] = [];
      let failed = false;
      active.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      active.onerror = () => { failed = true; releaseMicrophone(); if (mounted.current) { setPhase("idle"); setMessage("Recording failed. Check your microphone and try again."); } };
      active.onstop = async () => {
        releaseMicrophone();
        if (!mounted.current || failed) return;
        setPhase("preparing");
        try {
          const wav = await toWav(new Blob(chunks, { type: active.mimeType }));
          if (!mounted.current) return;
          if (wav.size <= 44) throw new Error("No audio was captured. Try again.");
          if (wav.size > 10 * 1024 * 1024) throw new Error("Recording exceeds 10 MB. Please make a shorter recording.");
          setFile(new File([wav], `recording-${new Date().toISOString().replace(/[:.]/g, "-")}.wav`, { type: "audio/wav" }));
          setMessage("Recording ready. Listen, then select it for upload.");
        } catch (error) {
          if (mounted.current) setMessage(error instanceof Error ? error.message : "Could not prepare the recording. Try again.");
        } finally {
          if (mounted.current) setPhase("idle");
        }
      };
      active.start(1000);
      setSeconds(0);
      setPhase("recording");
      const started = performance.now();
      timer.current = setInterval(() => {
        const elapsed = Math.floor((performance.now() - started) / 1000);
        setSeconds(elapsed);
        if (elapsed >= MAX_SECONDS) stop();
      }, 250);
    } catch (error) {
      releaseMicrophone();
      if (mounted.current) {
        setPhase("idle");
        setMessage(error instanceof DOMException && error.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access in your browser and try again."
          : "Could not access the microphone. Check that it is connected and available.");
      }
    } finally { starting.current = false; }
  }

  return (
    <section className="mb-6 rounded-lg border border-slate-700 p-4" aria-label="Record audio">
      <h2 className="font-semibold">Record audio</h2>
      <p className="mt-1 text-sm text-slate-400">Record up to 5 minutes, including recordings of 2 minutes or longer. Keep this page open until you stop and upload.</p>
      <p className="my-3 font-mono text-xl" aria-label="Recording duration">{Math.floor(seconds / 60).toString().padStart(2, "0")}:{(seconds % 60).toString().padStart(2, "0")}</p>
      {phase === "recording" ? (
        <button type="button" onClick={stop} className="rounded-lg bg-red-500 px-4 py-2 font-semibold">Stop recording</button>
      ) : (
        <button type="button" onClick={() => void start()} disabled={disabled || phase !== "idle"} className="rounded-lg bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50">
          {phase === "requesting" ? "Waiting for microphone…" : phase === "preparing" ? "Preparing recording…" : file ? "Record again" : "Start recording"}
        </button>
      )}
      {file && phase === "idle" && (
        <div className="mt-4">
          <audio ref={audioPreview} controls className="w-full" aria-label="Recording preview" />
          <button type="button" disabled={disabled} onClick={() => { onSelect(file); setMessage("Recording selected. Click Upload audio below to save it."); }} className="mt-3 rounded-lg border border-cyan-400 px-3 py-2 text-cyan-300 disabled:opacity-50">Use this recording</button>
        </div>
      )}
      <p role="status" className="mt-2 text-sm text-slate-300">{message || (phase === "recording" ? "Microphone is recording." : "")}</p>
    </section>
  );
}
