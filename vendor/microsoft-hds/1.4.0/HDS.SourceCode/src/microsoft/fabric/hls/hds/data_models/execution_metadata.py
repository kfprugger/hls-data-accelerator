from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict
class ExecutionDataType(Enum):
    deltaTable = "DeltaTable"
    file = "File"
    api = "API"
    
@dataclass
class ExecutionMetadata:
    sourceType: ExecutionDataType # Source type of the execution
    sourcePath: str # Path of the source
    targetType: ExecutionDataType # Target type of the execution
    targetPath: str # Path of the target
    sourceLakehouseName: Optional[str] = None # Name of the source lakehouse
    sourceLakehouseIdentifier: Optional[str] = None # Identifier of the source lakehouse
    targetLakehouseName: Optional[str] = None # Name of the target lakehouse
    targetLakehouseIdentifier: Optional[str] = None # Identifier of the target lakehouse
    executionAttributes: Optional[Dict[str, str]] = None # Additional execution metadata attributes
    