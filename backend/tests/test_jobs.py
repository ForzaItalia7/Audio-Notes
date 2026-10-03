import unittest
from unittest.mock import patch
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Upload, ProcessingJob
from app import jobs


class JobTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.upload = Upload(filename='test.wav', stored_at='/tmp/test.wav', status='completed', transcript='Meeting notes', notes='Previous notes')
        self.db.add(self.upload)
        self.db.commit()
        self.keys = patch.dict('os.environ', {'GEMINI_API_KEY': 'test', 'GNANI_API_KEY': 'test'})
        self.keys.start()

    def tearDown(self):
        self.keys.stop()
        self.db.close()
        self.engine.dispose()

    def test_duplicate_enqueue_creates_one_job(self):
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        self.assertEqual(self.db.query(ProcessingJob).count(), 1)

    def test_notes_complete_without_browser(self):
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        def generate(upload_id, db):
            db.get(Upload, upload_id).notes = 'New notes'
            db.commit()
        with patch.object(jobs, 'generate_upload_notes', side_effect=generate):
            jobs.process_next(self.db)
        self.assertEqual(self.db.query(ProcessingJob).one().status, 'completed')
        self.assertEqual(self.db.get(Upload, self.upload.id).notes, 'New notes')

    def test_failure_preserves_notes_and_allows_retry(self):
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        with patch.object(jobs, 'generate_upload_notes', side_effect=HTTPException(502, 'Provider unavailable')):
            jobs.process_next(self.db)
        job = self.db.query(ProcessingJob).one()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error, 'Provider unavailable')
        self.assertEqual(self.upload.notes, 'Previous notes')
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        self.assertEqual(job.status, 'queued')
        self.assertIsNone(job.error)

    def test_restart_preserves_queue_and_resumes_remote_job(self):
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        self.upload.status = 'processing'
        self.upload.gnani_job_id = 'existing-provider-job'
        self.db.add(ProcessingJob(upload_id=self.upload.id, kind='transcription', status='running'))
        self.db.commit()
        jobs.recover_jobs(self.db)
        states = {j.kind: j.status for j in self.db.query(ProcessingJob)}
        self.assertEqual(states, {'notes': 'queued', 'transcription': 'running'})

    def test_interrupted_notes_require_explicit_retry(self):
        jobs.enqueue_job(self.db, self.upload.id, 'notes')
        job = self.db.query(ProcessingJob).one()
        job.status = 'running'
        self.db.commit()
        jobs.recover_jobs(self.db)
        self.assertEqual(job.status, 'failed')
        self.assertIn('interrupted', job.error)
        self.assertEqual(self.upload.notes, 'Previous notes')

    def test_provider_poll_failure_retries_existing_job(self):
        self.upload.status = 'processing'
        self.upload.gnani_job_id = 'existing-provider-job'
        self.db.add(ProcessingJob(upload_id=self.upload.id, kind='transcription', status='running', next_run_at=jobs.now()-timedelta(seconds=1)))
        self.db.commit()
        with patch.object(jobs, 'check_transcription', side_effect=HTTPException(502, 'Temporary')):
            jobs.process_next(self.db)
        job = self.db.query(ProcessingJob).one()
        self.assertEqual(job.status, 'running')
        self.assertEqual(job.failures, 1)
        self.assertEqual(self.upload.gnani_job_id, 'existing-provider-job')


if __name__ == '__main__':
    unittest.main()
