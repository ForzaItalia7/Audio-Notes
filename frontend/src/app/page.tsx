"use client";
import AudioRecorder from "./components/AudioRecorder";
import { useEffect,useState, type ChangeEvent } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

type UploadStatus = "uploaded" | "processing" | "completed" | "failed";

type UploadRecord = {
  id: number;
  filename: string;
  content_type: string | null;
  stored_at: string;
  created_at: string;
  status: UploadStatus;
  transcript: string | null;
  notes: string | null;
  gnani_job_id: string | null;
  transcription_job_status: string | null;
  transcription_error: string | null;
  notes_job_status: string | null;
  notes_error: string | null;
};

function TextActions({ text, filename, kind, uploadId }: {
  text: string;
  filename: string;
  kind: "transcript" | "notes";
  uploadId: number;
}) {
  const [message, setMessage] = useState("");
  const [copying, setCopying] = useState(false);

  async function copyText() {
    setCopying(true);
    setMessage("");
    try {
      await navigator.clipboard.writeText(text);
      setMessage(`${kind === "notes" ? "Notes" : "Transcript"} copied.`);
    } catch {
      setMessage("Copy was blocked by your browser. Select the text to copy it, or download it.");
    } finally {
      setCopying(false);
    }
  }

  function downloadText() {
    setMessage("");
    let url: string | undefined;
    const link = document.createElement("a");
    try {
      const base = filename.replace(/\.[^.]+$/, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").trim().slice(0, 100) || "recording";
      url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      link.href = url;
      link.download = `${base}-${uploadId}-${kind}.txt`;
      document.body.appendChild(link);
      link.click();
      setMessage("Download requested. Check your browser's downloads.");
    } catch {
      setMessage("Could not download this file. Try copying the text instead.");
    } finally {
      link.remove();
      if (url) {
        const downloadUrl = url;
        window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      }
    }
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void copyText()} disabled={copying}
          className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50">
          {copying ? "Copying..." : `Copy ${kind}`}
        </button>
        <button type="button" onClick={downloadText}
          className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">
          Download {kind} (.txt)
        </button>
      </div>
      <p role="status" aria-live="polite" className="mt-1 text-sm text-slate-400">{message}</p>
    </div>
  );
}

export default function Home() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [backendStatus, setBackendStatus] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [uploadsStatus, setUploadsStatus] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [languageCode, setLanguageCode] = useState("hi-IN");
  const [transcribingUploadId, setTranscribingUploadId] = useState<number | null>(null);
  const [generatingNotesId, setGeneratingNotesId] = useState<number | null>(null);
  const [deletingUploadId, setDeletingUploadId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const isProcessing = (upload: UploadRecord) =>
    upload.status === "processing" || [upload.transcription_job_status, upload.notes_job_status].some((status) => status === "queued" || status === "running");
  const needsRetry = (upload: UploadRecord) =>
    upload.status === "failed" || upload.transcription_job_status === "failed" || upload.notes_job_status === "failed";
  const query = search.trim().toLocaleLowerCase();
  const visibleUploads = uploads.filter((upload) => {
    const matchesSearch = [upload.filename, upload.transcript, upload.notes, String(upload.id)]
      .some((value) => value?.toLocaleLowerCase().includes(query));
    const matchesStatus = historyFilter === "all"
      || (historyFilter === "processing" && isProcessing(upload))
      || (historyFilter === "retry" && needsRetry(upload))
      || (historyFilter === "ready" && !!upload.notes && !isProcessing(upload) && !needsRetry(upload))
      || (historyFilter === "uploaded" && upload.status === "uploaded");
    return matchesSearch && matchesStatus;
  });
  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (file) {
      setSelectedFile(file);
    }
  }
  async function checkBackendConnection() {
    setBackendStatus("Checking Backend...");

    try {
      const response = await fetch(`${API_BASE}/`);
      const data = await response.json();
      setBackendStatus(data.message);
    }
    catch {
      setBackendStatus("Could not reach the backend.");
    }
  }
  async function loadUploads() {
    try {
      const response = await fetch(`${API_BASE}/uploads`);
      if (!response.ok) {
        throw new Error("Could not load uploads.");
      }
      const data: UploadRecord[] = await response.json();
      setUploads(data);
      setUploadsStatus(data.length === 0 ? "No uploads yet." : null);
    } catch {
      setUploadsStatus("Could not load uploads.");
    }
  }
  async function transcribeUpload(upload: UploadRecord) {
    setTranscribingUploadId(upload.id);
    setUploadStatus(`Submitting upload #${upload.id} to Gnani...`);
    try {
      const response = await fetch(`${API_BASE}/uploads/${upload.id}/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language_code: languageCode }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail ?? "Transcription failed.");
      }
      await response.json();
      await loadUploads();

      setUploadStatus(`Transcription queued for upload #${upload.id}. You can leave this page and return later.`);
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Transcription failed.");
      await loadUploads();
    } finally {
      setTranscribingUploadId(null);
    }
  }
  async function deleteUpload(upload: UploadRecord) {
    const confirmed = window.confirm(
      `Delete upload #${upload.id} (${upload.filename}) and its audio file?`,
    );
    if (!confirmed) {
      return;
    }

    setDeletingUploadId(upload.id);
    try {
      const response = await fetch(`${API_BASE}/uploads/${upload.id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail ?? "Could not delete upload.");
      }
      await loadUploads();
    } catch (error) {
      setUploadsStatus(error instanceof Error ? error.message : "Could not delete upload.");
    } finally {
      setDeletingUploadId(null);
    }
  }
  async function generateNotes(upload: UploadRecord) {
    setGeneratingNotesId(upload.id);
    setUploadStatus(`Sending transcript for upload #${upload.id} to Gemini...`);

    try {
      const response = await fetch(`${API_BASE}/uploads/${upload.id}/notes`, {
        method: "POST",
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail ?? "Could not generate notes.");
      }
      await response.json();
      setUploadStatus(`Notes queued for upload #${upload.id}. You can leave this page and return later.`);
      await loadUploads();
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Could not generate notes.");
    } finally {
      setGeneratingNotesId(null);
    }
  }
  useEffect(() => {
    let isActive = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();

    async function fetchInitialUploads() {
      try {
        const response = await fetch(`${API_BASE}/uploads`, { signal: controller.signal });
        if (!response.ok) {
          throw new Error("Could not load uploads.");
        }
        const data: UploadRecord[] = await response.json();
        if (isActive) {
          setUploads(data);
          setUploadsStatus(data.length === 0 ? "No uploads yet." : null);
        }
      } catch {
        if (isActive) {
          setUploadsStatus("Could not load uploads.");
        }
      } finally {
        if (isActive) timer = setTimeout(() => void fetchInitialUploads(), 4000);
      }
    }

    void fetchInitialUploads();

    return () => {
      isActive = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);
  async function uploadSelectedFile() {
    if (!selectedFile || isUploading) {
      return;
    }
    setIsUploading(true);
    setUploadStatus("Uploading audio...");
    const formData = new FormData();
    formData.append("audio", selectedFile);

    try {
      const response = await fetch(`${API_BASE}/uploads`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail ?? "Upload failed.");
      }
      const data = await response.json();
      setUploadStatus(`Saved upload #${data.id}: ${data.filename}`);
      await loadUploads();
    }
    catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <header className="mx-auto flex max-w-3xl items-center justify-between border-b border-slate-800 pb-6">
        <span className="font-semibold text-slate-100">Gnani Audio Notes</span>

        <a
          href="/architecture"
          className="text-sm font-medium text-blue-400 hover:text-cyan-300"
        >
          Architecture
        </a>
      </header>
      <section className="mx-auto max-w-3xl">
        <p className="mb-4 text-sm font-bold tracking-widest text-red-400">
          GNANI AUDIO NOTES
        </p>
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
          Turn audio into clear, useful notes.
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
          Upload an audio recording, receive a transcript, and get a structured
          summary you can review later.
        </p>
        <div className="mt-10">
          <AudioRecorder onSelect={setSelectedFile} disabled={isUploading} />
          <label
            htmlFor="audio-file"
            className="inline-flex cursor-pointer rounded-lg bg-blue-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-cyan-300"
          >
            Choose an audio file
          </label>
          <div className="mt-10 border-t border-slate-800 pt-6">
            <button
              type="button"
              onClick={checkBackendConnection}
              className="rounded-lg border border-cyan-400 px-4 py-2 text-sm font-semibold text-cyan-400 hover:bg-cyan-400 hover:text-slate-950"
            >
              Check backend connection
            </button>

            {backendStatus && (
              <p className="mt-3 text-sm text-slate-300">{backendStatus}</p>
            )}
          </div>
          <input
            id="audio-file"
            type="file"
            accept="audio/*"
            onChange={handleFileChange}
            className="hidden"
          />
          {selectedFile && (
            <p className="mt-4 text-sm text-slate-300">
              Selected file: {selectedFile.name}
            </p>

          )}
          {selectedFile && (
            <button
              type="button"
              onClick={uploadSelectedFile}
              disabled={isUploading}
              className="mt-4 rounded-lg bg-cyan-400 px-5 py-3 font-semibold text-slate-950 hover:bg-cyan-300"
            >
              {isUploading ? "Uploading..." : "Upload audio"}
            </button>
          )}

          {uploadStatus && (
            <p className="mt-3 text-sm text-slate-300">{uploadStatus}</p>
          )}

          <section className="mt-12 border-t border-slate-800 pt-6">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-xl font-semibold">Upload history</h2>
              <button
                type="button"
                onClick={loadUploads}
                className="rounded-lg border border-cyan-400 px-4 py-2 text-sm font-semibold text-cyan-400 hover:bg-cyan-400 hover:text-slate-950"
              >
                Refresh history
              </button>
            </div>

            <div className="mt-5 flex flex-wrap items-end gap-3">
              <label className="min-w-48 flex-1 text-sm text-slate-300">
                Search recordings
                <input type="search" value={search} onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search names, transcripts, or notes"
                  className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100" />
              </label>
              <label className="text-sm text-slate-300">
                Show
                <select value={historyFilter} onChange={(event) => setHistoryFilter(event.target.value)}
                  className="mt-1 block rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100">
                  <option value="all">All recordings</option>
                  <option value="uploaded">Awaiting transcription</option>
                  <option value="processing">Processing</option>
                  <option value="ready">Notes ready</option>
                  <option value="retry">Needs retry</option>
                </select>
              </label>
              {(search || historyFilter !== "all") && (
                <button type="button" onClick={() => { setSearch(""); setHistoryFilter("all"); }}
                  className="rounded-lg border border-slate-600 px-3 py-2 text-sm">Clear filters</button>
              )}
            </div>
            <p role="status" className="mt-3 text-sm text-slate-400">
              Showing {visibleUploads.length} of {uploads.length} recordings · Progress updates automatically
            </p>
            {uploads.length > 0 && visibleUploads.length === 0 && (
              <p className="mt-4 rounded-lg border border-slate-700 p-4 text-slate-300">No recordings match. Try a different search or clear the filters.</p>
            )}

            <label className="mt-5 block text-sm text-slate-300">
              Transcription language
              <select
                value={languageCode}
                onChange={(event) => setLanguageCode(event.target.value)}
                className="ml-3 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
              >
                <option value="hi-IN">Hindi</option>
                <option value="en-IN">Indian English</option>
                <option value="bn-IN">Bengali</option>
                <option value="kn-IN">Kannada</option>
                <option value="ml-IN">Malayalam</option>
                <option value="mr-IN">Marathi</option>
                <option value="ta-IN">Tamil</option>
                <option value="te-IN">Telugu</option>
              </select>
            </label>

            {uploadsStatus && (
              <p className="mt-4 text-sm text-slate-300">{uploadsStatus}</p>
            )}

            <ul className="mt-4 space-y-3">
              {visibleUploads.map((upload) => (
                <li key={upload.id} className="rounded-lg border border-slate-800 p-4">
                  <p className="font-medium">{upload.filename}</p>
                  <p className="mt-1 text-sm text-slate-400">
                    Upload #{upload.id} · {new Date(upload.created_at).toLocaleString()}
                  </p>
                  <p className="mt-1 text-sm text-cyan-300">
                    Transcription: {upload.transcription_job_status === "queued" ? "Waiting to start" : upload.transcription_job_status === "running" ? "In progress" : upload.status === "completed" ? "Ready" : upload.status === "failed" ? "Needs retry" : upload.status === "processing" ? "In progress" : "Not started"}
                    {` · Notes: ${upload.notes_job_status === "queued" ? "Waiting to start" : upload.notes_job_status === "running" ? "Generating" : upload.notes_job_status === "failed" ? "Needs retry" : upload.notes ? "Ready" : "Not generated"}`}

                  </p>
                  {(upload.transcription_error || upload.notes_error) && (
                    <p role="status" className="mt-2 text-sm text-amber-300">
                      {upload.transcription_error && `Transcription: ${upload.transcription_error} `}
                      {upload.notes_error && `Notes: ${upload.notes_error}`}
                    </p>
                  )}
                  {upload.transcript && (
                    <>
                      <h3 className="mt-4 text-sm font-semibold text-slate-300">Transcript</h3>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">
                        {upload.transcript}
                      </p>
                      <TextActions text={upload.transcript} filename={upload.filename} kind="transcript" uploadId={upload.id} />
                      <button
                        type="button"
                        onClick={() => void generateNotes(upload)}
                        disabled={generatingNotesId === upload.id || ["queued", "running"].includes(upload.notes_job_status ?? "")}
                        className="mt-3 rounded-lg border border-violet-400 px-3 py-1.5 text-sm text-violet-300 disabled:opacity-50"
                      >
                        {generatingNotesId === upload.id || ["queued", "running"].includes(upload.notes_job_status ?? "")
                          ? "Generating notes..."
                          : upload.notes_job_status === "failed"
                            ? "Retry notes with Gemini"
                          : upload.notes
                            ? "Regenerate notes with Gemini"
                            : "Generate notes with Gemini"}
                      </button>
                    </>
                  )}
                  {upload.notes && (
                    <>
                      <h3 className="mt-4 text-sm font-semibold text-slate-300">Notes</h3>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">
                        {upload.notes}
                      </p>
                      <TextActions text={upload.notes} filename={upload.filename} kind="notes" uploadId={upload.id} />
                    </>
                  )}
                  {(upload.status === "uploaded" || upload.status === "failed" || upload.status === "processing") && (
                    <button
                      type="button"
                      onClick={() => void transcribeUpload(upload)}
                      disabled={transcribingUploadId === upload.id || ["queued", "running"].includes(upload.transcription_job_status ?? "")}
                      className="mt-3 rounded-lg border border-cyan-400 px-3 py-1.5 text-sm text-cyan-300 disabled:opacity-50"
                    >
                      {transcribingUploadId === upload.id || ["queued", "running"].includes(upload.transcription_job_status ?? "")
                        ? "Transcribing..."
                        : upload.status === "processing"
                          ? "Check transcription"
                          : upload.status === "failed"
                            ? "Retry transcription"
                            : "Transcribe with Gnani"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void deleteUpload(upload)}
                    disabled={deletingUploadId === upload.id || [upload.transcription_job_status, upload.notes_job_status].some((status) => status === "queued" || status === "running")}
                    className="ml-2 mt-3 rounded-lg border border-red-400 px-3 py-1.5 text-sm text-red-300 disabled:opacity-50"
                  >
                    {deletingUploadId === upload.id ? "Deleting..." : "Delete upload"}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </section>
    </main>
  );
}
