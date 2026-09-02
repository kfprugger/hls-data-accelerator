# setup-devbox.ps1
# Run this from a MWC-WT terminal with appropriate permissions

# ======================
# Configurable Variables
# ======================
$CapacityName = "hdspremiumcapacity"

# Function to log output with timestamp
function Log {
    param (
        [string]$Message,
        [ConsoleColor]$Color = "Yellow"  # Default to Yellow if not specified
    )

    Write-Host "$(Get-Date -Format "yyyy-MM-dd HH:mm:ss") - $Message" -ForegroundColor $Color
}

try {
    clear
    Log "****************************************Starting setup-devbox.ps1*********************************************************!"
    # Step 1: Clone workload-dmh repo
    Set-Location "Q:\Repos\"
    if (-Not (Test-Path "Q:\Repos\workload-dmh")) {
        Log "Cloning workload-dmh repo..."
        git clone https://powerbi@dev.azure.com/powerbi/MWC/_git/workload-dmh
    }

    # Step 2: Pull latest changes and build
    Set-Location "Q:\Repos\workload-dmh\"
    Log "Pulling latest changes in workload-dmh..."
    git pull

    # Step 3: Pull Mwc and aspaas repos
    Set-Location "Q:\Repos\Mwc\"
    Log "Pulling latest changes in Mwc..."
    git pull

    Set-Location "Q:\Repos\Mwc\administrative-tools"
    Log "Pulling latest changes in administrative-tools..."
    git config --global --add safe.directory Q:/Repos/Mwc/administrative-tools
    git pull

    Set-Location "Q:\Repos\Mwc\fabric-libraries"
    Log "Pulling latest changes in fabric-libraries..."
    git config --global --add safe.directory Q:/Repos/Mwc/fabric-libraries
    git pull

    Set-Location "Q:\Repos\Mwc\aspaas\"
    Log "Pulling latest changes in aspaas..."
    git config --global --add safe.directory Q:/Repos/Mwc/aspaas
    git pull

    # Step 4: Set local workloads env
    Log "Setting local workloads environment..."
    ..\SetLocalWorkloadsEnv.ps1 -Workloads @("DMH")

    # Step 5: Build solution
    Log "Running Build.ps1..."
    ..\Build.ps1

    # Step 6: Deploy Onebox
    Log "Deploying Onebox with SQLServer and PreRequisites..."
    .\deploy-onebox.ps1 -Include SQLServer, PreRequisites

    # Step 7: Provision Onebox
    Log "Provisioning Onebox Capacity..."
    .\onebox-provision-basic.ps1 `
        -CapacityName $CapacityName `
        -SkuName P1 `
        -CapacityMode AutoPremium `
        -SkuCapacity 1 `
        -Admin AdminUser01@ppeEdogTenant.ccsctp.net `
        -TenantId da809b57-5842-4362-8d55-032ca0f968bc

    # Step 8: Activate workloads
    Log "Activating workload: DMH"
    .\activate-workload.ps1 -Workload DMH -WorkloadRepoRoot "Q:\Repos\workload-dmh\"

    Log "Activating workloads: Lake, LH, CDSA, DMS"
    .\activate-workload.ps1 -Workloads "Lake", "LH", "CDSA", "DMS"

    Log "Activating workloads: Dataflows, NB, SC, AS, RS, DI, TIPS"
    .\activate-workload.ps1 -Workloads "Dataflows", "NB", "SC", "AS", "RS", "DI", "TIPS"

    # Step 9: Launch monitoring tabs
    Log "Opening Service Fabric Explorer..."
    Start-Process "msedge.exe" "http://localhost:19080/Explorer/index.html#/apps"

    Log "****************************************All steps completed successfully*********************************************************!" -Color Green
}
catch {
    Write-Error "An error occurred: $_"
    exit 1
}
