"""Patch the generated HDS POA model without modifying the vendored release."""
from __future__ import annotations


def project_appointment_created_day(model: dict) -> None:
    """Compute the report date in foldable Power Query, not an unprocessed DAX column."""
    table = next(t for t in model["model"]["tables"] if t["name"] == "AppointmentDim")
    column = next(c for c in table["columns"] if c["name"] == "AppointmentCreatedDay")
    if column.get("sourceColumn") == "AppointmentCreatedDay":
        return
    if column.get("type") != "calculated":
        raise ValueError("Unexpected AppointmentCreatedDay column contract")
    for partition in table["partitions"]:
        source = partition["source"]
        if source.get("type") != "m":
            raise ValueError("POA date projection requires a Power Query partition")
        expression = source["expression"]
        was_list = isinstance(expression, list)
        text = "\n".join(expression) if was_list else expression
        original = 'dbo_appointmentdim = Source{[Schema="dbo",Item="AppointmentDim"]}[Data]'
        if original not in text or "in\n    dbo_appointmentdim" not in text:
            raise ValueError("POA AppointmentDim partition shape changed")
        text = text.replace(original, original + ',\n    WithCreatedDay = Table.AddColumn(dbo_appointmentdim, "AppointmentCreatedDay", each Date.From([AppointmentScheduledDate]), type date)', 1)
        text = text.replace("in\n    dbo_appointmentdim", "in\n    WithCreatedDay", 1)
        source["expression"] = text.splitlines() if was_list else text
    column.pop("type")
    column.pop("expression", None)
    column.update(dataType="dateTime", sourceColumn="AppointmentCreatedDay")
