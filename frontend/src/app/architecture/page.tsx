const githubUrl = process.env.NEXT_PUBLIC_GITHUB_URL;
const apiUrl = process.env.NEXT_PUBLIC_API_URL;

const flow = [
  {
    title: "1. Upload",
    text: "The Next.js page accepts an audio file or captures browser audio. FastAPI writes recordings to a private S3-compatible bucket when configured, then saves metadata in PostgreSQL; local development can use the backend uploads folder.",
  },
  {
    title: "2. Transcribe in the background",
    text: "The API saves a transcription job in PostgreSQL and returns immediately. A worker claims jobs using a PostgreSQL advisory lock and submits the audio to Gnani's asynchronous Batch Speech-to-Text API. It checks progress, downloads the transcript, and saves it to the upload record.",
  },
  {
    title: "3. Generate notes in the background",
    text: "The user can request notes after transcription. A separate saved job sends the transcript and the notes prompt to Gemini 3.8 Flash. The worker saves the result and reports failures while preserving existing notes.",
  },
  {
    title: "4. Reopen results",
    text: "The page refreshes upload history from the API, so saved audio metadata, transcripts, notes, job states, and errors return after a page refresh.",
  },
];

export default function ArchitecturePage() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <section className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm font-medium text-cyan-400 hover:text-cyan-300">← Back to home</Link>
        <p className="mt-10 text-sm font-semibold tracking-widest text-cyan-400">SYSTEM ARCHITECTURE</p>
        <h1 className="mt-4 text-4xl font-bold tracking-tight">How an audio note is processed</h1>
        <ol className="mt-8 space-y-4">
          {flow.map((step) => (
            <li key={step.title} className="rounded-lg border border-slate-800 p-5">
              <strong>{step.title}</strong>
              <p className="mt-2 leading-7 text-slate-300">{step.text}</p>
            </li>
          ))}
        </ol>

        <section className="mt-8 rounded-lg border border-amber-700/70 bg-amber-950/30 p-5">
          <h2 className="text-lg font-semibold text-amber-200">Current storage and audio limits</h2>
            <p className="mt-2 leading-7 text-slate-300">
              {apiUrl ? "The frontend sends API requests to the configured production API." : "The frontend currently uses the local development API address. Set NEXT_PUBLIC_API_URL to the deployed API before building the production frontend."} When AUDIO_BUCKET and S3 credentials are configured, the API stores recordings in a private S3-compatible bucket and sends Gnani a short-lived signed download URL. Without a bucket, development recordings live in the backend uploads folder, which is not persistent on typical cloud hosts. Gnani accepts direct audio uploads up to 10 MB and cloud-storage audio up to four hours. Configure MAX_UPLOAD_SIZE_BYTES to the host&apos;s request limit; the default is 2 GB.
          </p>
          <p className="mt-3 leading-7 text-slate-300">
            Background jobs and results are stored in PostgreSQL. A single worker runs alongside the FastAPI process and acquires a database lock. For deployment, keep the API and worker alive, use persistent PostgreSQL, and use a persistent audio bucket.
          </p>
        </section>

        <section className="mt-8 rounded-lg border border-slate-800 p-5">
          <h2 className="text-lg font-semibold">What I would change for production</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 leading-7 text-slate-300">
            <li>Store private recordings in an object-storage bucket and submit large-file paths to Gnani.</li>
            <li>Run the worker as a separately monitored deployment service.</li>
            <li>Add user accounts and authorization before accepting private recordings from multiple people.</li>
            <li>Use separate development and production secrets and review retention, access controls, and provider data settings.</li>
          </ul>
        </section>

        <section className="mt-8 border-t border-slate-800 pt-6">
          <h2 className="text-lg font-semibold">Source code</h2>
          {githubUrl ? (
            <a href={githubUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block text-cyan-400 underline hover:text-cyan-300">Open the GitHub repository</a>
          ) : (
            <p className="mt-2 text-slate-300">The GitHub repository link will be added after this project is published. The current workspace has no GitHub remote.</p>
          )}
        </section>
      </section>
    </main>
  );
}
import Link from "next/link";
