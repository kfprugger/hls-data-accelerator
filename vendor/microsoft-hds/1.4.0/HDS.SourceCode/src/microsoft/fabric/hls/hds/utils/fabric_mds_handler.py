# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from logging import LogRecord
from typing import Dict, Any
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from synapse.ml.pymds.handler import SynapseHandler
from synapse.ml.internal_utils.session_utils import get_fabric_context


class FabricMDSHandler(SynapseHandler):
    """
    Handler for logging events to Microsoft Diagnostic Service (MDS) in Fabric Environment.

    Inherits from SynapseHandler and adds additional functionality for logging to MDS.

    Attributes:
        extra_keys (list[str]): List of keys for additional data to be logged.
    """
    extra_keys: list[str] = GC.HDS_KUSTO_CUSTOM_DIMENSIONS
    
    def get_mds_event_fields(self, record: LogRecord) -> Dict[str, Any]:
        """
        Get the fields for an MDS event from a log record.

        This method overrides the base method in SynapseHandler. It adds additional fields to the event,
        including artifactId, and artifactType.

        Args:
            record (LogRecord): The log record.

        Returns:
            dict: A dictionary containing the fields for the MDS event.
        """
        res = super().get_mds_event_fields(record)
        
        try:
            for key in record.__dict__:
                if key in self.extra_keys:
                    res[key] = record.__dict__.get(key)

            res["artifactId"] =  get_fabric_context().get('trident.artifact.id', '')
            res["artifactType"] =  get_fabric_context().get('trident.artifact.type', '')
            return res
        except Exception:
            return res