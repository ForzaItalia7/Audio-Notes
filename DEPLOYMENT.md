# Free demo deployment

This repo is prepared for the following split deployment:

- Vercel Hobby serves the Next.js frontend.
- Render Free runs FastAPI and its PostgreSQL-backed job worker in one web service.
- Supabase Free provides managed PostgreSQL.
- Amazon S3 stores audio privately.

## Limits to keep in mind

- Render Free sleeps after 15 minutes without inbound requests and can take about a minute to wake. It has an ephemeral filesystem, so audio must use S3.
- Supabase Free can pause after seven days of low activity. Its free database has a 500 MB size quota.
- Vercel Hobby is for personal, non-commercial use.
- Free allowances and AWS S3 usage are subject to provider limits. Check each dashboard's usage and billing before deployment.

## Deployment order

1. Create a Supabase project. In Connect, choose a connection string suitable for a persistent IPv4 backend (session pooler). Use SSL and adapt its scheme to postgresql+psycopg:// for this backend. Keep the connection string private.
2. In Render, create a Blueprint from this GitHub repository. Render reads render.yaml; set the prompted secrets there. Keep DATABASE_URL, Gnani/Gemini keys, and S3 credentials in the Render service environment only.
3. After Render deploys, copy its HTTPS API URL.
4. In Vercel, import ForzaItalia7/Audio-Notes, set the Root Directory to frontend, and add NEXT_PUBLIC_API_URL to the Render API URL and NEXT_PUBLIC_GITHUB_URL to the GitHub repository URL. Deploy.
5. Copy the Vercel HTTPS URL into Render's FRONTEND_ORIGINS, then redeploy the API.
6. Verify upload, transcription, notes, history after refresh, and visible failure messages.

The Render start command applies Alembic migrations before starting FastAPI. The API starts the background worker in its lifespan. No separate worker service is needed.

The API has no sign-in or per-user quota controls. Keep this deployment private while configuring it; before sharing the public demo, consider the risk of untrusted users consuming Gnani/Gemini credits or filling the bucket.
