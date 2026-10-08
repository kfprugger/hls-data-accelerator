import {
  Checkbox,
  Field,
  Input,
  Text,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
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
    gap: tokens.spacingVerticalM,
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  options: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
    gap: tokens.spacingHorizontalM,
    paddingLeft: tokens.spacingHorizontalL,
  },
  help: {
    color: tokens.colorNeutralForeground2,
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

  return (
    <div className={styles.root}>
      <div className={styles.section}>
        <Checkbox
          label="Azure Databricks"
          checked={value.deploy_databricks ?? false}
          disabled={databricksDisabled}
          onChange={(_, data) => onChange({ deploy_databricks: !!data.checked })}
        />
        <Text size={200} className={styles.help}>
          Runs after the base deployment using an isolated FHIR export snapshot. Adding later creates a fresh export.
          Unity Catalog metastore assignment is automatic when permitted. If account-admin permission is needed,
          the run pauses for up to 24 hours: ask a Databricks account admin to assign the regional metastore,
          then select Continue in the deployment monitor.
        </Text>
        {value.deploy_databricks && (
          <div className={styles.options}>
            <Field label="Databricks environment" hint="Environment name used by the Databricks deployment scripts.">
              <Input
                value={value.databricks_environment ?? "dev"}
                disabled={databricksDisabled}
                onChange={(_, data) => onChange({ databricks_environment: data.value })}
              />
            </Field>
            <Field label="Databricks admin group" hint="Leave blank to use the deployment's admin security group.">
              <Input
                value={value.databricks_admin_group ?? ""}
                placeholder={adminGroup || "Use deployment admin security group"}
                disabled={databricksDisabled}
                onChange={(_, data) => onChange({ databricks_admin_group: data.value })}
              />
            </Field>
          </div>
        )}
      </div>
      <div className={styles.section}>
        <Checkbox
          label="Rayfin apps"
          checked={value.deploy_rayfin_apps ?? false}
          disabled={rayfinDisabled}
          onChange={(_, data) => onChange({ deploy_rayfin_apps: !!data.checked })}
        />
        <Text size={200} className={styles.help}>
          Deploys the Rayfin applications against this deployment's Fabric workspace after the base deployment finishes.
        </Text>
      </div>
      <div className={styles.section}>
        <Checkbox
          label="Cardiology app"
          checked={value.deploy_cardiology ?? false}
          disabled={cardiologyDisabled}
          onChange={(_, data) => onChange({ deploy_cardiology: !!data.checked })}
        />
        <Text size={200} className={styles.help}>
          Deploys the cardiology application against this deployment's healthcare data. Model preflight requires
          DataZoneStandard availability and at least 50K TPM of free quota in the selected cardiology region.
        </Text>
        {value.deploy_cardiology && (
          <div className={styles.options}>
            <Field label="Cardiology Azure location" hint="Azure region name, such as eastus2.">
              <Input
                value={value.cardiology_location ?? "eastus2"}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_location: data.value })}
              />
            </Field>
            <Field label="Cardiology resource prefix" hint="Leave blank to derive cardio<suffix> from this deployment.">
              <Input
                value={value.cardiology_prefix ?? ""}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_prefix: data.value })}
              />
            </Field>
            <Field label="Cardiology app users" hint="One user principal name per line. Blank lines are ignored.">
              <Textarea
                value={(value.cardiology_app_users ?? []).join("\n")}
                rows={3}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_app_users: data.value.split("\n") })}
              />
            </Field>
            <Field label="Cardiology reviewer users" hint="One reviewer user principal name per line. Blank lines are ignored.">
              <Textarea
                value={(value.cardiology_reviewer_users ?? []).join("\n")}
                rows={3}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_reviewer_users: data.value.split("\n") })}
              />
            </Field>
            <Field label="Cardiology chat model" hint="Leave model and version blank to try gpt-5.6-luna (2026-07-09), then gpt-5.5 (2026-04-24).">
              <Input
                value={value.cardiology_chat_model ?? ""}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_chat_model: data.value })}
              />
            </Field>
            <Field label="Cardiology chat model version" hint="Set the model name and version together to override the built-in candidates.">
              <Input
                value={value.cardiology_chat_model_version ?? ""}
                disabled={cardiologyDisabled}
                onChange={(_, data) => onChange({ cardiology_chat_model_version: data.value })}
              />
            </Field>
          </div>
        )}
      </div>
    </div>
  );
}
