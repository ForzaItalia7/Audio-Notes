# Two-minute flow verification — October 3, 2026

Verified against the running local backend with synthetic English speech.
No microphone input or personal recording was used for this check.

| Check | Result |
| --- | --- |
| Test recording | Exactly 120 seconds, mono 16 kHz, 16-bit WAV |
| File size | 3,840,044 bytes; below the 10 MB direct transcription limit |
| Upload | Saved as upload #10, `two-minute-test.wav` |
| Transcription submission | HTTP 202; background job accepted |
| Background transcription | Completed; 2,069 transcript characters saved |
| Notes submission | HTTP 202; background job accepted |
| Background notes | Completed; 1,387 notes characters saved |
| Persistence | Results retrieved through the upload-history endpoint |
| Notes review | Expected title, summary, key points, decision, owners, deadlines, and unresolved questions present |

The verifier only read upload history while waiting. It did not call the
transcription-status endpoint to advance processing. The backend worker handled
both provider operations independently.

This confirms the two-minute WAV upload-to-notes path. It does **not** verify
browser microphone permissions, MediaRecorder capture, browser WAV conversion,
playback, clipboard access, or downloads. Browser testing remains necessary:

1. Allow microphone access and record at least 2 minutes.
2. Stop and play the recording to confirm audio was captured.
3. Select the recording, upload it, and start transcription.
4. Refresh the page while it runs and confirm saved progress returns.
5. Generate notes and check the results, copy, and download controls.

The synthetic test upload is retained in history for inspection.
