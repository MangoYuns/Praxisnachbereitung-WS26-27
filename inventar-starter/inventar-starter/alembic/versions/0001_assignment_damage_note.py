"""Tag 4 A: optionalen Schaden-Vermerk an einer Ausleihe speichern.

Voraussetzung: Das Tag-3-Schema aus db/init wurde bereits angelegt.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_damage_note"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assignment", sa.Column("damage_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("assignment", "damage_note")
