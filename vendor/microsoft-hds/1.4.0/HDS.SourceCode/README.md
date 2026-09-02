---
ArtifactType: python package
Documentation: TBD
Language: python, powershell
Platform: windows, linux
Tags: spark,python,pyspark
---

# Healthcare Data Solutions (HDS)

Healthcare data solutions in Microsoft Fabric help you accelerate time to value by addressing the critical need to efficiently transform healthcare data into a suitable format for analysis. With these solutions, you can conduct exploratory analysis, run large-scale analytics, and power generative AI with your healthcare data. By using intuitive tools such as data pipelines and transformations, you can easily navigate and process complex datasets, overcoming the inherent challenges associated with unstructured data formats.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development purposes.

### A note on Python versions

Each Linux distribution usually comes pre-packaged with a Python version at the system level (known as the 'system level interpreter'). Ubuntu 20.04 comes with Python 3.8 and Ubuntu 22.04 comes with Python 3.10. It is recommended to use Python 3.10 for development.

### Installing

#### Prerequisites

1. [Install WSL on your Windows](https://learn.microsoft.com/en-us/windows/wsl/install)
2. Install Ubuntu using the wsl command in Powershell commandline: `wsl --install -d ubuntu-20.04`
3. In a powershell, run `wsl --setdefault ubuntu-20.04` to set default WSL version to ubuntu.

#### Configuring a dev environment in Visual Studio Code

1. Install [Visual Studio Code](https://code.visualstudio.com/).
2. Install the [Remote Development extension pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack).
3. Clone the git repo folder . If you are facing issues with git on WSL, please take a look at [Proper Git Config on WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-git).
4. Follow instructions listed [here](https://code.visualstudio.com/docs/remote/wsl#_open-a-remote-folder-or-workspace) to open the folder in a WSL window in Visual Studio code.
5. Install Python Extension Pack for Visual Studio Code.
6. Verify [Remote Development] and [Python Extension Pack] both the extensions are installed and enabled on 'WSL: Ubuntu-20.04'. (typically when plugin is installed on local and not on Linux, it will not be able locate the Python interpreter)
7. Open a bash terminal in Visual Studio Code and run the below commands. If you face any issues with install Azure CLI, please take a look [here](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt).

```bash
$ wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
$ sudo dpkg -i packages-microsoft-prod.deb
$ rm packages-microsoft-prod.deb
$ sudo add-apt-repository ppa:deadsnakes/ppa -y
$ sudo apt update
$ sudo apt upgrade
$ sudo apt install software-properties-common python3.10 python3.10-venv python3-pip openjdk-11-jdk make azure-cli dotnet-sdk-7.0 zip -y
# you should now have java 11 installed
$ java --version
 >> openjdk 11.0.16 2022-07-19
 >> ...
# observe that python3 is the system interpreter
$ python3 --version
 >>Python 3.8.10
# review that python3.10 is now additionally installed
$ python3.10 --version
 >>Python 3.10.13
```
7. Run `which python3.10` and make a note of the path. Use Ctrl+Shift+P and search for "Python: Create Environment". Click and choose Venv. For the interpreter choose the python version listed at the python3.10 path.
8. Open a new terminal. This should open a new WSL terminal window with (.venv) at the beginning
9. Configure [Git Credential Manager](https://learn.microsoft.com/windows/wsl/tutorials/wsl-git#git-credential-manager-setup) in order to share credentials & settings between WSL and the Windows host.
10. Run `git config --global core.autocrlf true` from the .venv WSL terminal, this will ensure that git will not change line endings when committing code (this will prevent a discrepancy between git on windows and git on wsl with showing deltas)
11. Run `make setup`

# Build

1. Run `make build` to build and package. You can use the `local-config.mk` to control build configuration.

**Note**: If you see the error `az: '<some_command>' is not in the 'az' command group` you might need to update your Azure CLI by running `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`

## Jupyter Notebooks

1. Install the Jupyter extension in Visual Studio Code
2. On first run or any change to the code, run `make build-install`. This will build and install your latest code into you virtual environment. This ensures that you are always working with the latest package.
3. On every new install of your package, it's best to **restart** the kernel to ensure Jupyter is using the latest install.
4. You can connect to an azure storage account from a local notebook via the following updates the `SparkContext`
5. Pull your azure storage account key and modify the below query. Reference on how to get the key: https://learn.microsoft.com/en-us/azure/storage/common/storage-account-keys-manage?tabs=azure-portal
6. Install ipykernel for using Jupyter extension using cmd /bin/python3.10 -m pip install ipykernel -U --user --force-reinstall

```python
from pyspark.sql import SparkSession
spark: SparkSession = SparkSession.builder.appName("HDP")\
    .config('spark.jars.packages', 'org.apache.hadoop:hadoop-azure:3.2.1,com.microsoft.azure:azure-storage:8.6.6')\
    .config("fs.azure.account.key.<your-storage-account>.dfs.core.windows.net", "<account key>")\
    .config("spark.sql.caseSensitive", "True").getOrCreate()
```

If you receive an auth error it's most likely the WSL clock is out of sync. Run `sudo hwclock -s` to sync to the hardware clock

TODO: explore other auth flows (would managed identity work?).
https://docs.databricks.com/storage/azure-storage.html
https://hadoop.apache.org/docs/stable/hadoop-azure/abfs.html
https://stackoverflow.com/questions/66484669/using-azure-identity-credentials-for-spark-access-to-blob-store

## Code reviews for Notebook

1. Once you have made a change to a notebook in your fabric workspace, clear all the outputs of the notebook by navigating to the notebook > Edit > Clear all output(s).
2. Export the notebook from fabric workspace into the `/notebooks` folder to either create new or replace the existing version of a notebook.
3. Notebooks are a great development tool, but we often want to apply some formatting before they are made public. As a result, during the CI build, a series of updates are performed on the notebooks to remove markdown content, freeze cells, and remove superfluous validation cells. Having these steps be applied in build allows us to keep the "dev" copy of notebooks and feel confident that the rules will provide guardrails around the content. Fabric supports additional Notebook features via metadata. For example, when assigning a Lakehouse to Notebook, that selection is stored as part of Notebook metadata. As part of the CI build, we augment the metadata to make room for a default environment and lakehouse. Please note, if the notebook does not require a default lakehouse or environment, please add the file name to the list in `excluded_files` of [format_notebooks.py](./format_notebooks.py) line 6.

## Deployment

Add additional notes about how to deploy this on a live system

## Built With

Documenting some of the main tools used to build this project, manage dependencies, etc will help users get more information if they are trying to understand or having difficulties getting the project up and running.

- Link to some dependency manager
- Link to some framework or build tool
- Link to some compiler, linting tool, bundler, etc


## Versioning and changelog

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](link-to-tags-or-other-release-location).

It is a good practice to keep `CHANGELOG.md` file in repository that can be updated as part of a pull request.

## Troubleshooting

### Command Line Error: `az: '<some_command>' is not in the 'az' command group` 

You might need to update your Azure CLI by running `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`

### Git Credential Manager (GCM) for WSL
Additional guidance for GCM configuration for WSL can be found [here](
https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/wsl.md#configuring-wsl-with-git-for-windows-recommended)


## License

Please refer to Microsoft license terms available here: https://go.microsoft.com/fwlink/?LinkId=2369925