"""MVP enum names for the first Spine model layer."""

from enum import StrEnum


class ItemType(StrEnum):
    EVENT = "event"
    TASK = "task"
    PROJECT = "project"
    COLLECTION = "collection"


class ItemStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
