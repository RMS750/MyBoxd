"""add public Letterboxd rating fields

Revision ID: 7d7b82933e24
Revises: 42dc7977f5b4
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa

revision = "7d7b82933e24"
down_revision = "42dc7977f5b4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("letterboxd_rating", sa.Float(), nullable=True))
        batch.add_column(sa.Column("letterboxd_rating_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("letterboxd_url", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("letterboxd_updated_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("movies") as batch:
        batch.drop_column("letterboxd_updated_at")
        batch.drop_column("letterboxd_url")
        batch.drop_column("letterboxd_rating_count")
        batch.drop_column("letterboxd_rating")
