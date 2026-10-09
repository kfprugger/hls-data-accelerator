import { Alert, Box } from "@mui/material";


export function MockDataBanner() {
    return (<Alert style={{ marginBottom: 12 }} severity={"warning"}>
      <Box>
        <strong>Mock data in use</strong> — The backend is unavailable. Displaying simulated data.
      </Box>
    </Alert>);
}
