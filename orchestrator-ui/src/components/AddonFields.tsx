import { Checkbox, FormControl, FormControlLabel, FormHelperText, FormLabel, TextField, Typography } from "@mui/material";
import { makeStyles } from "@griffel/react";

import type { AddonName, AddonOptions } from "../api";

export function getAddonOptions(value: Partial<AddonOptions> = {}): AddonOptions {
  return {
    deploy_databricks: value.deploy_databricks ?? false,
    databricks_environment: value.databricks_environment ?? "dev",
    databricks_admin_group: value.databricks_admin_group ?? "",
    deploy_rayfin_apps: value.deploy_rayfin_apps ?? false,
    deploy_cardiology: value.deploy_cardiology ?? false,
    cardiology_location: value.cardiology_location ?? "eastus2",
    cardiology_prefix: value.cardiology_prefix ?? "",
    cardiology_app_users: (value.cardiology_app_users ?? []).map((user) => user.trim()).filter(Boolean),
    cardiology_reviewer_users: (value.cardiology_reviewer_users ?? []).map((user) => user.trim()).filter(Boolean),
    cardiology_chat_model: value.cardiology_chat_model ?? "",
    cardiology_chat_model_version: value.cardiology_chat_model_version ?? "",
  };
}

const useStyles = makeStyles({
    root: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
    },
    section: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
    },
    options: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
        gap: "16px",
        paddingLeft: "24px",
    },
    help: {
        color: "var(--m3-colorNeutralForeground2)",
    },
});

interface AddonFieldsProps {
  value: Partial<AddonOptions>;
  onChange: (patch: Partial<AddonOptions>) => void;
  disabled?: boolean;
  unavailable?: AddonName[];
  adminGroup?: string;
}

export function AddonFields({ value, onChange, disabled = false, unavailable = [], adminGroup }: AddonFieldsProps) {
    const styles = useStyles();
    const databricksDisabled = disabled || unavailable.includes("databricks");
    const rayfinDisabled = disabled || unavailable.includes("rayfin");
    const cardiologyDisabled = disabled || unavailable.includes("cardiology");
    return (<div className={styles.root}>
      <div className={styles.section}>
        <FormControlLabel label={"Azure Databricks"} control={<Checkbox checked={value.deploy_databricks ?? false} onChange={(event) => {
                const data = { checked: event.target.checked };
                return onChange({ deploy_databricks: !!data.checked });
            }} disabled={databricksDisabled}/>} disabled={databricksDisabled}/>
        <Typography className={styles.help} component="span" variant="caption">
          Runs after the base deployment using an isolated FHIR export snapshot. Adding later creates a fresh export.
          Unity Catalog metastore assignment is automatic when permitted. If account-admin permission is needed,
          the run pauses for up to 24 hours: ask a Databricks account admin to assign the regional metastore,
          then select Continue in the deployment monitor.
        </Typography>
        {value.deploy_databricks && (<div className={styles.options}>
            <FormControl><FormLabel id="field-addonfields-1-label" htmlFor="field-addonfields-1">{"Databricks environment"}</FormLabel>
              <TextField value={value.databricks_environment ?? "dev"} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ databricks_environment: data.value });
            }} disabled={databricksDisabled} fullWidth size="small" id="field-addonfields-1"/>
            <FormHelperText>{"Environment name used by the Databricks deployment scripts."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-2-label" htmlFor="field-addonfields-2">{"Databricks admin group"}</FormLabel>
              <TextField value={value.databricks_admin_group ?? ""} placeholder={adminGroup || "Use deployment admin security group"} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ databricks_admin_group: data.value });
            }} disabled={databricksDisabled} fullWidth size="small" id="field-addonfields-2"/>
            <FormHelperText>{"Leave blank to use the deployment's admin security group."}</FormHelperText></FormControl>
          </div>)}
      </div>
      <div className={styles.section}>
        <FormControlLabel label={"Rayfin apps"} control={<Checkbox checked={value.deploy_rayfin_apps ?? false} onChange={(event) => {
                const data = { checked: event.target.checked };
                return onChange({ deploy_rayfin_apps: !!data.checked });
            }} disabled={rayfinDisabled}/>} disabled={rayfinDisabled}/>
        <Typography className={styles.help} component="span" variant="caption">
          Deploys the Rayfin applications against this deployment's Fabric workspace after the base deployment finishes.
        </Typography>
      </div>
      <div className={styles.section}>
        <FormControlLabel label={"Cardiology app"} control={<Checkbox checked={value.deploy_cardiology ?? false} onChange={(event) => {
                const data = { checked: event.target.checked };
                return onChange({ deploy_cardiology: !!data.checked });
            }} disabled={cardiologyDisabled}/>} disabled={cardiologyDisabled}/>
        <Typography className={styles.help} component="span" variant="caption">
          Deploys the cardiology application against this deployment's healthcare data. Model preflight requires
          DataZoneStandard availability and at least 50K TPM of free quota in the selected cardiology region.
        </Typography>
        {value.deploy_cardiology && (<div className={styles.options}>
            <FormControl><FormLabel id="field-addonfields-3-label" htmlFor="field-addonfields-3">{"Cardiology Azure location"}</FormLabel>
              <TextField value={value.cardiology_location ?? "eastus2"} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_location: data.value });
            }} disabled={cardiologyDisabled} fullWidth size="small" id="field-addonfields-3"/>
            <FormHelperText>{"Azure region name, such as eastus2."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-4-label" htmlFor="field-addonfields-4">{"Cardiology resource prefix"}</FormLabel>
              <TextField value={value.cardiology_prefix ?? ""} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_prefix: data.value });
            }} disabled={cardiologyDisabled} fullWidth size="small" id="field-addonfields-4"/>
            <FormHelperText>{"Leave blank to derive cardio<suffix> from this deployment."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-5-label" htmlFor="field-addonfields-5">{"Cardiology app users"}</FormLabel>
              <TextField value={(value.cardiology_app_users ?? []).join("\n")} rows={3} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_app_users: data.value.split("\n") });
            }} disabled={cardiologyDisabled} fullWidth size="small" multiline id="field-addonfields-5"/>
            <FormHelperText>{"One user principal name per line. Blank lines are ignored."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-6-label" htmlFor="field-addonfields-6">{"Cardiology reviewer users"}</FormLabel>
              <TextField value={(value.cardiology_reviewer_users ?? []).join("\n")} rows={3} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_reviewer_users: data.value.split("\n") });
            }} disabled={cardiologyDisabled} fullWidth size="small" multiline id="field-addonfields-6"/>
            <FormHelperText>{"One reviewer user principal name per line. Blank lines are ignored."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-7-label" htmlFor="field-addonfields-7">{"Cardiology chat model"}</FormLabel>
              <TextField value={value.cardiology_chat_model ?? ""} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_chat_model: data.value });
            }} disabled={cardiologyDisabled} fullWidth size="small" id="field-addonfields-7"/>
            <FormHelperText>{"Leave model and version blank to try gpt-5.6-luna (2026-07-09), then gpt-5.5 (2026-04-24)."}</FormHelperText></FormControl>
            <FormControl><FormLabel id="field-addonfields-8-label" htmlFor="field-addonfields-8">{"Cardiology chat model version"}</FormLabel>
              <TextField value={value.cardiology_chat_model_version ?? ""} onChange={(event) => {
                const data = { value: event.target.value };
                return onChange({ cardiology_chat_model_version: data.value });
            }} disabled={cardiologyDisabled} fullWidth size="small" id="field-addonfields-8"/>
            <FormHelperText>{"Set the model name and version together to override the built-in candidates."}</FormHelperText></FormControl>
          </div>)}
      </div>
    </div>);
}
