import { Button, Card, CardHeader, Chip, Typography } from "@mui/material";
import { ExpandLess, ExpandMore, OpenInNew } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
/**
 * Deployed Resources Panel — collapsible tables showing Azure and Fabric resources
 * discovered in the deployed resource group / workspace.
 */

import { useState } from "react";


import type { DeployedResourcesResult } from "../api";

const useStyles = makeStyles({
    resources: {
        marginTop: "32px",
    },
    resourceSection: {
        marginBottom: "24px",
    },
    resourceSectionHeader: {
        display: "flex",
        alignItems: "center",
        gap: "12px",
        marginBottom: "12px",
    },
    resourceTable: {
        width: "100%",
        borderCollapse: "collapse" as const,
        fontSize: "12px",
    },
    resourceRow: {
        borderBottom: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        ":hover": {
            backgroundColor: "var(--m3-colorNeutralBackground1Hover)",
        },
    },
    resourceCell: {
        padding: `${"8px"} ${"12px"}`,
        verticalAlign: "middle" as const,
    },
    resourceType: {
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "11px",
    },
    resourceLoading: {
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "16px",
        color: "var(--m3-colorNeutralForeground3)",
    },
});

interface DeployedResourcesPanelProps {
  deployedResources: DeployedResourcesResult | null;
  resourcesLoading: boolean;
  resourceGroupName: string;
  azurePortalUrl?: string;
}

export function DeployedResourcesPanel({ deployedResources, resourcesLoading, resourceGroupName, azurePortalUrl, }: DeployedResourcesPanelProps) {
    const styles = useStyles();
    const [fabricExpanded, setFabricExpanded] = useState(false);
    const [azureExpanded, setAzureExpanded] = useState(false);
    return (<Card className={styles.resources}>
      <CardHeader title={<Typography component="div" variant="subtitle1">Deployed Resources</Typography>}/>

      {resourcesLoading && !deployedResources && (<div className={styles.resourceLoading}>
          <span style={{ display: "inline-block" }}>⟳</span>
          <Typography component="span" variant="caption">Scanning Azure &amp; Fabric APIs…</Typography>
        </div>)}

      {!resourcesLoading && !deployedResources && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)", padding: "12px", display: "block" }} component="span" variant="caption">
          Restart the backend server to enable live resource scanning.
        </Typography>)}

      {deployedResources && (<>
          {/* Fabric Workspace */}
          {deployedResources.workspace && (<div className={styles.resourceSection}>
              <div className={styles.resourceSectionHeader} onClick={() => setFabricExpanded((v) => !v)} style={{ cursor: "pointer", userSelect: "none" }}>
                <Chip component="span" size="small" variant="filled" color="primary" label={<>Fabric</>}/>
                <Typography component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                  Workspace: {deployedResources.workspace.name}
                </Typography>
                <Chip component="span" size="small" variant="filled" color="default" label={<>{deployedResources.fabric.length} items</>}/>
                <Button component={"a"} href={deployedResources.workspace.url} target="_blank" rel="noopener noreferrer" onClick={(e: React.MouseEvent) => e.stopPropagation()} variant="text" size="small" startIcon={<OpenInNew />}>
                  Open in Fabric
                </Button>
                <Button onClick={(e) => { e.stopPropagation(); setFabricExpanded((v) => !v); }} style={{ marginLeft: "auto" }} variant="text" size="small" startIcon={fabricExpanded ? <ExpandLess /> : <ExpandMore />}/>
              </div>
              {fabricExpanded && deployedResources.fabric.length > 0 && (<table className={styles.resourceTable}>
                  <thead>
                    <tr>
                      <th className={styles.resourceCell} style={{ textAlign: "left", color: "var(--m3-colorNeutralForeground3)" }}>Name</th>
                      <th className={styles.resourceCell} style={{ textAlign: "left", color: "var(--m3-colorNeutralForeground3)" }}>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deployedResources.fabric.map((item) => (<tr key={item.id} className={styles.resourceRow}>
                        <td className={styles.resourceCell}>
                          <Typography component="span" variant="caption">{item.name}</Typography>
                        </td>
                        <td className={styles.resourceCell}>
                          <span className={styles.resourceType}>{item.type}</span>
                        </td>
                      </tr>))}
                  </tbody>
                </table>)}
              {fabricExpanded && deployedResources.fabric.length === 0 && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)", padding: "12px" }} component="span" variant="caption">
                  No Fabric items found yet
                </Typography>)}
            </div>)}

          {/* Azure Resources */}
          {deployedResources.azure.length > 0 && (<div className={styles.resourceSection}>
              <div className={styles.resourceSectionHeader} onClick={() => setAzureExpanded((v) => !v)} style={{ cursor: "pointer", userSelect: "none" }}>
                <Chip component="span" size="small" variant="filled" color="default" label={<>Azure</>}/>
                <Typography component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                  Resource Group: {resourceGroupName}
                </Typography>
                <Chip component="span" size="small" variant="filled" color="default" label={<>{deployedResources.azure.length} resources</>}/>
                <Button component={"a"} href={azurePortalUrl || `https://portal.azure.com/#browse/resourcegroups/filterValue/${resourceGroupName}`} target="_blank" rel="noopener noreferrer" onClick={(e: React.MouseEvent) => e.stopPropagation()} variant="text" size="small" startIcon={<OpenInNew />}>
                  Open in Azure
                </Button>
                <Button onClick={(e) => { e.stopPropagation(); setAzureExpanded((v) => !v); }} style={{ marginLeft: "auto" }} variant="text" size="small" startIcon={azureExpanded ? <ExpandLess /> : <ExpandMore />}/>
              </div>
              {azureExpanded && (<table className={styles.resourceTable}>
                  <thead>
                    <tr>
                      <th className={styles.resourceCell} style={{ textAlign: "left", color: "var(--m3-colorNeutralForeground3)" }}>Name</th>
                      <th className={styles.resourceCell} style={{ textAlign: "left", color: "var(--m3-colorNeutralForeground3)" }}>Type</th>
                      <th className={styles.resourceCell} style={{ textAlign: "left", color: "var(--m3-colorNeutralForeground3)" }}>Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deployedResources.azure.map((r) => (<tr key={r.id} className={styles.resourceRow}>
                        <td className={styles.resourceCell}>
                          <Typography component="span" variant="caption">{r.name}</Typography>
                        </td>
                        <td className={styles.resourceCell}>
                          <span className={styles.resourceType}>{r.type}</span>
                        </td>
                        <td className={styles.resourceCell}>
                          <span className={styles.resourceType}>{r.location}</span>
                        </td>
                      </tr>))}
                  </tbody>
                </table>)}
            </div>)}

          {/* Nothing found at all */}
          {!deployedResources.workspace && deployedResources.azure.length === 0 && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)", padding: "12px" }} component="span" variant="caption">
              No deployed resources detected yet
            </Typography>)}
        </>)}
    </Card>);
}
