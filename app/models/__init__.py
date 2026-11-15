"""Mapped tables for hospital wayfinding."""

from app.models.building import Building
from app.models.department import Department
from app.models.floor import Floor
from app.models.hospital_site import HospitalSite
from app.models.kiosk import Kiosk
from app.models.navigation_edge import NavigationEdge
from app.models.navigation_node import NavigationNode
from app.models.room import Room
from app.models.service import Service
from app.models.service_alias import ServiceAlias
from app.models.service_location import ServiceLocation

__all__ = [
    "Building",
    "Department",
    "Floor",
    "HospitalSite",
    "Kiosk",
    "NavigationEdge",
    "NavigationNode",
    "Room",
    "Service",
    "ServiceAlias",
    "ServiceLocation",
]
