from pydantic import BaseModel
from typing import List

class NodePositionUpdate(BaseModel):
    node_id: str
    x: float
    y: float

class PositionsUpdate(BaseModel):
    positions: List[NodePositionUpdate]
