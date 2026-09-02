from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class FHIRResourceTransformConfig:
    """
    Configuration for extracting and transforming properties from a FHIR resource.

    Attributes:
        properties (List[str]): A list of property names to extract from the FHIR resource.
        value_transformers (Optional[Dict[str, Callable[[Dict, str], Any]]]): 
            A mapping of property names to transformation functions. Each function takes 
            the FHIR resource and the property name as input and returns the transformed value.
    """
    properties: List[str]
    value_transformers: Optional[Dict[str, Callable[[Dict, str], Any]]] = None