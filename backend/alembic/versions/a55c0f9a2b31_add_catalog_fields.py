"""add local catalogue metadata fields

Revision ID: a55c0f9a2b31
Revises: 7d7b82933e24
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa

revision = "a55c0f9a2b31"
down_revision = "7d7b82933e24"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("catalog_rating", sa.Float(), nullable=True))
        batch.add_column(sa.Column("catalog_rating_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("catalog_popularity", sa.Float(), nullable=True))
        batch.add_column(sa.Column("catalog_source", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("imdb_id", sa.String(length=20), nullable=True))
        batch.create_index("ix_movies_imdb_id", ["imdb_id"], unique=False)


def downgrade():
    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_imdb_id")
        batch.drop_column("imdb_id")
        batch.drop_column("catalog_source")
        batch.drop_column("catalog_popularity")
        batch.drop_column("catalog_rating_count")
        batch.drop_column("catalog_rating")
