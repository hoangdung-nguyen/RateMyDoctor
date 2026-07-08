from typing import TypedDict, NotRequired
from uuid import UUID
from datetime import datetime

"""
Defines the dictionary fields that are expected by functions in
database.py. Full schema is described with the commented-out portions
included, and anything with #R excluded.

The #R means the input will be used to create a link between nodes,
instead of existing as a property.
"""


class User(TypedDict):
    username: str

class UserLogin(User):
    password: str

class Doctor(User):
    name: str
    specialty: str
    hostpitalID: UUID #R

class Hospital(TypedDict):
    name: str
    address: str  #Cut zip out
    zip: int
    uuid: NotRequired[UUID]

class Comment(TypedDict):
    content: str
    username: str
    parentID: UUID     
    posted: NotRequired[datetime]
    removed: NotRequired[bool]
    uuid: NotRequired[UUID]

class Review(Comment):
    score: int
