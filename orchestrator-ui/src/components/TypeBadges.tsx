import { Chip } from "@mui/material";
/**
 * Consistent Azure/Fabric/SPN badge components used across the app.
 * Azure Blue (#0078D4), Fabric Teal (#117865).
 */



const AZURE_BLUE = "#0078D4";
const FABRIC_TEAL = "#117865";
const ENTRA_BLUE = "#3A96DD";

export function AzureBadge() {
    return (<Chip style={{
            backgroundColor: AZURE_BLUE,
            color: "white",
        }} component="span" size="small" variant="filled" label={<>
      Azure
    </>}/>);
}

export function FabricBadge() {
    return (<Chip style={{
            backgroundColor: FABRIC_TEAL,
            color: "white",
        }} component="span" size="small" variant="filled" label={<>
      Fabric
    </>}/>);
}

export function EntraIdBadge() {
    return (<Chip style={{
            backgroundColor: ENTRA_BLUE,
            color: "white",
        }} component="span" size="small" variant="filled" label={<>
      Entra ID
    </>}/>);
}

export function typeBadge(type: "fabric" | "azure" | "spn") {
    switch (type) {
        case "fabric":
            return <FabricBadge />;
        case "azure":
            return <AzureBadge />;
        case "spn":
            return <EntraIdBadge />;
    }
}
