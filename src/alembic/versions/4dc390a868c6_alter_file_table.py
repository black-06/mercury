"""alter file table

Revision ID: 4dc390a868c6
Revises: 
Create Date: 2024-09-24 10:53:40.841420

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4dc390a868c6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("file", "path", new_column_name="name", existing_type=sa.VARCHAR(255))
    op.add_column("file", sa.Column("cos", sa.Boolean(), nullable=False))


def downgrade() -> None:
    pass
