"""Add CGR³ context fields to bullets table

Revision ID: b2f4e8a1c3d5
Revises: 443cc2c91dfe
Create Date: 2026-02-15

Adds context graph fields for CGR³ (Context Graph Retrieve-Rank-Reason):
- Temporal validity fields (valid_from, valid_until, temporal_confidence, tech_context)
- Locality context fields (team_id, project_ids, applicable_domains)
- Enhanced provenance fields (created_by_type, created_by_id, source_conversation_id, confidence_score)
- BulletLineage table for knowledge relationships
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b2f4e8a1c3d5'
down_revision = '443cc2c91dfe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE creator_type AS ENUM ('human', 'ai', 'derived')")
    op.execute("CREATE TYPE lineage_type AS ENUM ('derived_from', 'refined', 'contradicts', 'supersedes')")

    # Add temporal validity fields to bullets table
    op.add_column('bullets', sa.Column(
        'valid_from', sa.DateTime(), nullable=True,
        comment='When this pattern became valid (null = since creation)'
    ))
    op.add_column('bullets', sa.Column(
        'valid_until', sa.DateTime(), nullable=True,
        comment='When this pattern expires (null = still valid)'
    ))
    op.add_column('bullets', sa.Column(
        'temporal_confidence', sa.Float(), nullable=False, server_default='1.0',
        comment='Confidence score that decays over time (0.0-1.0)'
    ))
    op.add_column('bullets', sa.Column(
        'tech_context', postgresql.JSON(astext_type=sa.Text()), nullable=True,
        comment='Tech stack requirements, e.g., {"python": ">=3.10", "framework": "fastapi"}'
    ))

    # Add locality context fields
    op.add_column('bullets', sa.Column(
        'team_id', sa.String(length=100), nullable=True,
        comment='Team that created/owns this pattern'
    ))
    op.add_column('bullets', sa.Column(
        'project_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True,
        comment='Projects where this pattern has been used'
    ))
    op.add_column('bullets', sa.Column(
        'applicable_domains', postgresql.JSON(astext_type=sa.Text()), nullable=True,
        comment='Domains where this pattern applies (more specific than tags)'
    ))

    # Add enhanced provenance fields
    op.add_column('bullets', sa.Column(
        'created_by_type',
        sa.Enum('human', 'ai', 'derived', name='creator_type', create_type=False),
        nullable=False, server_default='ai',
        comment='Who created this: human, ai, or derived from other patterns'
    ))
    op.add_column('bullets', sa.Column(
        'created_by_id', sa.String(length=255), nullable=True,
        comment='User email, model name, or source pattern ID'
    ))
    op.add_column('bullets', sa.Column(
        'source_conversation_id', sa.String(length=255), nullable=True,
        comment='Link to conversation/session where this was created'
    ))
    op.add_column('bullets', sa.Column(
        'confidence_score', sa.Float(), nullable=False, server_default='0.5',
        comment='How reliable is this pattern? (0.0-1.0)'
    ))

    # Create indexes for CGR³ retrieval
    op.create_index('ix_bullets_team', 'bullets', ['team_id'])
    op.create_index('ix_bullets_created_by_type', 'bullets', ['created_by_type'])
    op.create_index('ix_bullets_temporal', 'bullets', ['valid_from', 'valid_until'])
    op.create_index('ix_bullets_confidence', 'bullets', ['confidence_score'])

    # Create bullet_lineage table for knowledge relationships
    op.create_table(
        'bullet_lineage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('child_bullet_id', sa.Integer(), nullable=False),
        sa.Column('parent_bullet_id', sa.Integer(), nullable=False),
        sa.Column(
            'relationship_type',
            sa.Enum('derived_from', 'refined', 'contradicts', 'supersedes', name='lineage_type', create_type=False),
            nullable=False
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('context', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['child_bullet_id'], ['bullets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_bullet_id'], ['bullets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_lineage_child_parent', 'bullet_lineage', ['child_bullet_id', 'parent_bullet_id'])
    op.create_index('ix_lineage_type', 'bullet_lineage', ['relationship_type'])
    op.create_index('ix_bullet_lineage_child_bullet_id', 'bullet_lineage', ['child_bullet_id'])
    op.create_index('ix_bullet_lineage_parent_bullet_id', 'bullet_lineage', ['parent_bullet_id'])


def downgrade() -> None:
    # Drop bullet_lineage table
    op.drop_index('ix_bullet_lineage_parent_bullet_id', table_name='bullet_lineage')
    op.drop_index('ix_bullet_lineage_child_bullet_id', table_name='bullet_lineage')
    op.drop_index('ix_lineage_type', table_name='bullet_lineage')
    op.drop_index('ix_lineage_child_parent', table_name='bullet_lineage')
    op.drop_table('bullet_lineage')

    # Drop CGR³ indexes from bullets table
    op.drop_index('ix_bullets_confidence', table_name='bullets')
    op.drop_index('ix_bullets_temporal', table_name='bullets')
    op.drop_index('ix_bullets_created_by_type', table_name='bullets')
    op.drop_index('ix_bullets_team', table_name='bullets')

    # Drop enhanced provenance fields
    op.drop_column('bullets', 'confidence_score')
    op.drop_column('bullets', 'source_conversation_id')
    op.drop_column('bullets', 'created_by_id')
    op.drop_column('bullets', 'created_by_type')

    # Drop locality context fields
    op.drop_column('bullets', 'applicable_domains')
    op.drop_column('bullets', 'project_ids')
    op.drop_column('bullets', 'team_id')

    # Drop temporal validity fields
    op.drop_column('bullets', 'tech_context')
    op.drop_column('bullets', 'temporal_confidence')
    op.drop_column('bullets', 'valid_until')
    op.drop_column('bullets', 'valid_from')

    # Drop enum types
    op.execute("DROP TYPE lineage_type")
    op.execute("DROP TYPE creator_type")
