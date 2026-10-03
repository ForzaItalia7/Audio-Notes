"""Initial uploads and background jobs schema."""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('uploads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100)),
        sa.Column('stored_at', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.String(30), server_default='uploaded', nullable=False),
        sa.Column('transcript', sa.Text()),
        sa.Column('notes', sa.Text()),
        sa.Column('gnani_job_id', sa.String(64)),
    )
    op.create_table('processing_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('upload_id', sa.Integer(), sa.ForeignKey('uploads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('language_code', sa.String(10), nullable=False),
        sa.Column('error', sa.Text()),
        sa.Column('next_run_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.UniqueConstraint('upload_id', 'kind'),
    )


def downgrade():
    # Initial schema contains user recordings/results: never drop it implicitly.
    raise RuntimeError('The initial schema cannot be downgraded automatically. Restore a verified backup if needed.')
