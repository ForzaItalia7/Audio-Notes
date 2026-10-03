# Gnani internship task: pre-deployment checklist

Scope comes from `Gnani - Internship Task.pdf`. This file distinguishes what the
local app proves from what must be completed before submitting a deployed URL.

| PDF requirement | Current evidence | Status before deployment |
| --- | --- | --- |
| Upload an audio file; comfortably support at least 2 minutes | Generated 120-second WAV was uploaded successfully and was 3.84 MB. Browser recording was not exercised, per the user's instruction. | **Core flow verified; browser recording not verified.** |
| Any audio length or size | Private S3-compatible storage and short-lived Gnani cloud-storage URLs are implemented. With the bucket configured, uploads default to a 2 GB size cap. Without it, upload size is capped at 10 MB to match Gnani's direct-upload path. Gnani documents a 4-hour duration ceiling. | **Implementation ready; not verified against a configured cloud bucket.** No service can accept literally unlimited duration. |
| Transcribe using Gnani ASR | A synthetic 120-second recording completed transcription; result persisted in PostgreSQL. | **Complete for direct files within current limit.** |
| Display transcript | Transcript appears in upload history; copy and text download controls exist. | **Complete locally.** |
| Display an LLM-generated summary | Gemini generated and saved structured notes from the test transcript. | **Complete locally.** |
| List past uploads and reopen them | PostgreSQL upload history refreshes; transcript and notes are retained. With a bucket configured, audio bytes are stored there; without one, local audio lives on disk. | **Complete locally; bucket behavior awaits credentials.** |
| Next.js, FastAPI, PostgreSQL, storage bucket, background jobs | Frontend, API, PostgreSQL queue worker, S3-compatible storage, and Gnani cloud-storage submission are implemented. | **Implementation ready; production infrastructure not configured.** |
| Deploy a usable public URL | No Git repository or remote is configured in this workspace; app is still configured for local addresses. | **Not complete.** Needs source hosting, production API/frontend URLs, persistent services, secrets, and a public smoke check. |
| `/architecture` page with flow, file locations, long-audio approach, sync/background split, tradeoffs, GitHub link | Page explains local and bucket storage, PostgreSQL queue, background worker, and production limits. No repository remote exists. | **Page exists; source link requires publishing.** |
| Visible failures | Upload, transcription, and notes errors are shown; job state and retry controls appear in history. | **Implemented locally; deployed-provider failure checks remain.** |
| Progress for long jobs | Queue states persist in PostgreSQL; the page refreshes history every four seconds; completed 2-minute run verified independently of the browser. | **Implemented locally; public deployment check remains.** |

## Deployment gate

Do not describe the project as meeting every requirement or submit it until these
remaining items are done:

1. Configure durable bucket storage and send larger files to Gnani using its
   documented cloud-storage batch input. Align client/server limits so an upload
   is not accepted if the selected transcription path cannot process it.
2. Publish the repository and add its URL to `NEXT_PUBLIC_GITHUB_URL` so the
   architecture page links to real source code.
3. Deploy the frontend, API, PostgreSQL, and worker with persistent audio storage;
   configure HTTPS origins, `NEXT_PUBLIC_API_URL`, API URLs, and server-side Gnani/Gemini/database
   secrets. Do not put provider secrets in frontend variables.
4. Open the public URL and verify upload, progress, transcript, notes, reopen,
   and visible retry/error behavior. The evaluator should need no local setup.
5. Decide whether the public demo can accept unauthenticated uploads. As built,
   the API has no user sign-in or quota controls; a public URL can be abused to
   consume provider credits. Keep it private or add access controls before broad
   public exposure.

The PDF's instruction to try Gnani's separate demo is a suggested research step,
not a feature requirement; it is not claimed as completed here.
