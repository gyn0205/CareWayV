"""create wayfinding schema

Revision ID: 0001
Create Date: 2026-11-15 22:17:13.195026

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'hospital_sites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_hospital_sites')),
        sa.UniqueConstraint('code', name=op.f('uq_hospital_sites_code')),
    )
    op.create_table(
        'buildings',
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id'],
            ['hospital_sites.id'],
            name=op.f('fk_buildings_site_id_hospital_sites'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_buildings')),
        sa.UniqueConstraint('site_id', 'code', name=op.f('uq_buildings_site_id_code')),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_buildings_site_id_id')),
    )
    op.create_table(
        'departments',
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id'],
            ['hospital_sites.id'],
            name=op.f('fk_departments_site_id_hospital_sites'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_departments')),
        sa.UniqueConstraint('site_id', 'code', name=op.f('uq_departments_site_id_code')),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_departments_site_id_id')),
    )
    op.create_table(
        'services',
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('normalized_name', sa.String(length=160), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id'],
            ['hospital_sites.id'],
            name=op.f('fk_services_site_id_hospital_sites'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_services')),
        sa.UniqueConstraint('site_id', 'code', name=op.f('uq_services_site_id_code')),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_services_site_id_id')),
    )
    op.create_index(
        op.f('ix_services_site_id_normalized_name'),
        'services',
        ['site_id', 'normalized_name'],
        unique=False,
    )
    op.create_table(
        'floors',
        sa.Column('building_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('map_asset_url', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id', 'building_id'],
            ['buildings.site_id', 'buildings.id'],
            name=op.f('fk_floors_site_id_building_id_buildings'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_floors')),
        sa.UniqueConstraint(
            'site_id',
            'building_id',
            'level',
            name=op.f('uq_floors_site_id_building_id_level'),
        ),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_floors_site_id_id')),
    )
    op.create_table(
        'service_aliases',
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('normalized_alias', sa.String(length=160), nullable=False),
        sa.Column('alias', sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id', 'service_id'],
            ['services.site_id', 'services.id'],
            name=op.f('fk_service_aliases_site_id_service_id_services'),
        ),
        sa.PrimaryKeyConstraint(
            'site_id',
            'service_id',
            'normalized_alias',
            name=op.f('pk_service_aliases'),
        ),
    )
    op.create_index(
        op.f('ix_service_aliases_site_id_normalized_alias'),
        'service_aliases',
        ['site_id', 'normalized_alias'],
        unique=False,
    )
    op.create_table(
        'navigation_nodes',
        sa.Column('floor_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('label', sa.String(length=160), nullable=True),
        sa.Column('x', sa.Float(), nullable=True),
        sa.Column('y', sa.Float(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            '(x IS NULL AND y IS NULL) OR (x IS NOT NULL AND y IS NOT NULL AND x BETWEEN 0 AND 1 AND y BETWEEN 0 AND 1)',
            name=op.f('ck_navigation_nodes_map_coordinates'),
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'floor_id'],
            ['floors.site_id', 'floors.id'],
            name=op.f('fk_navigation_nodes_site_id_floor_id_floors'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_navigation_nodes')),
        sa.UniqueConstraint(
            'site_id',
            'floor_id',
            'code',
            name=op.f('uq_navigation_nodes_site_id_floor_id_code'),
        ),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_navigation_nodes_site_id_id')),
    )
    op.create_table(
        'kiosks',
        sa.Column('origin_node_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id', 'origin_node_id'],
            ['navigation_nodes.site_id', 'navigation_nodes.id'],
            name=op.f('fk_kiosks_site_id_origin_node_id_navigation_nodes'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_kiosks')),
        sa.UniqueConstraint('site_id', 'code', name=op.f('uq_kiosks_site_id_code')),
    )
    op.create_index(
        op.f('ix_kiosks_site_id_origin_node_id'),
        'kiosks',
        ['site_id', 'origin_node_id'],
        unique=False,
    )
    op.create_table(
        'navigation_edges',
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('from_node_id', sa.Integer(), nullable=False),
        sa.Column('to_node_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('cost_seconds', sa.Integer(), nullable=False),
        sa.Column('wheelchair_accessible', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind <> 'stairs' OR NOT wheelchair_accessible",
            name=op.f('ck_navigation_edges_stairs_accessibility'),
        ),
        sa.CheckConstraint(
            "kind IN ('walk', 'stairs', 'elevator')",
            name=op.f('ck_navigation_edges_valid_kind'),
        ),
        sa.CheckConstraint('cost_seconds > 0', name=op.f('ck_navigation_edges_positive_cost')),
        sa.CheckConstraint(
            'from_node_id <> to_node_id',
            name=op.f('ck_navigation_edges_distinct_nodes'),
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'from_node_id'],
            ['navigation_nodes.site_id', 'navigation_nodes.id'],
            name=op.f('fk_navigation_edges_site_id_from_node_id_navigation_nodes'),
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'to_node_id'],
            ['navigation_nodes.site_id', 'navigation_nodes.id'],
            name=op.f('fk_navigation_edges_site_id_to_node_id_navigation_nodes'),
        ),
        sa.PrimaryKeyConstraint(
            'site_id',
            'from_node_id',
            'to_node_id',
            'kind',
            name=op.f('pk_navigation_edges'),
        ),
    )
    op.create_index(
        op.f('ix_navigation_edges_site_id_to_node_id'),
        'navigation_edges',
        ['site_id', 'to_node_id'],
        unique=False,
    )
    op.create_table(
        'rooms',
        sa.Column('entrance_node_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id', 'department_id'],
            ['departments.site_id', 'departments.id'],
            name=op.f('fk_rooms_site_id_department_id_departments'),
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'entrance_node_id'],
            ['navigation_nodes.site_id', 'navigation_nodes.id'],
            name=op.f('fk_rooms_site_id_entrance_node_id_navigation_nodes'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_rooms')),
        sa.UniqueConstraint('site_id', 'code', name=op.f('uq_rooms_site_id_code')),
        sa.UniqueConstraint('site_id', 'id', name=op.f('uq_rooms_site_id_id')),
    )
    op.create_index(
        op.f('ix_rooms_site_id_department_id'),
        'rooms',
        ['site_id', 'department_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_rooms_site_id_entrance_node_id'),
        'rooms',
        ['site_id', 'entrance_node_id'],
        unique=False,
    )
    op.create_table(
        'service_locations',
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.ForeignKeyConstraint(
            ['site_id', 'room_id'],
            ['rooms.site_id', 'rooms.id'],
            name=op.f('fk_service_locations_site_id_room_id_rooms'),
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'service_id'],
            ['services.site_id', 'services.id'],
            name=op.f('fk_service_locations_site_id_service_id_services'),
        ),
        sa.PrimaryKeyConstraint(
            'site_id',
            'service_id',
            'room_id',
            name=op.f('pk_service_locations'),
        ),
    )
    op.create_index(
        op.f('ix_service_locations_site_id_room_id'),
        'service_locations',
        ['site_id', 'room_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('service_locations')
    op.drop_table('rooms')
    op.drop_table('navigation_edges')
    op.drop_table('kiosks')
    op.drop_table('navigation_nodes')
    op.drop_table('service_aliases')
    op.drop_table('floors')
    op.drop_table('services')
    op.drop_table('departments')
    op.drop_table('buildings')
    op.drop_table('hospital_sites')
