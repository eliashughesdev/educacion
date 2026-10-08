from typing import Annotated, Optional
from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _oid_to_str(v):
    return str(v) if isinstance(v, ObjectId) else v


PyObjectId = Annotated[str, BeforeValidator(_oid_to_str)]


class BaseDocument(BaseModel):
    """Mongo document wrapper: _id <-> id. Reference fields are stored as strings."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        return None if doc is None else cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True)
        if data.get("_id"):
            data["_id"] = ObjectId(data["_id"])
        else:
            data.pop("_id", None)
        return data


def out(doc: dict, exclude: tuple = ("password_hash",)) -> dict:
    if doc is None:
        return None
    return BaseDocument.from_mongo(doc).model_dump(exclude=set(exclude))
