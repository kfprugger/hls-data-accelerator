SHELL := /bin/bash
EXPORT_ALL_VARIABLES:
include local-config.mk

# Adds to shell to python code can also access all the make file variables
export $(shell sed 's/=.*//' local-config.mk)

TEMP_DIR = $(DIST_DIR)/temp
WHEEL_NAME_FULL = $(WHEEL_NAME)-$(WHEEL_VERSION)-py3-none-any.whl
VENV = .venv
VENV_BIN=$(VENV)/bin/


define copy-notebooks =
	$(1) folder_structure.py "notebooks" $(2)
endef

define copy-pipelines =
	$(1) folder_structure.py "pipelines" $(2)
endef

define build =
	$(call copy-pipelines, $(1), "datapipelines/");
	$(call copy-notebooks, $(1), "notebooks/");
	$(call format-notebooks, $(1), $(3));
	$(call build-dm4h-python-package, $(1))
	mkdir -p $(MARKETPLACE_OFFER_DIR) && az bicep build --file 'src/infra/main.bicep' --outfile '$(MARKETPLACE_OFFER_DIR)/mainTemplate.json'
	mkdir -p $(DM_CONFIG_INTERNAL_DIR) && cp -R 'src/config/'* $(DM_CONFIG_INTERNAL_DIR)
	mkdir -p $(DM_SYSTEM_CONFIGURATIONS_DIR) && cp -R 'src/system_configurations/'* $(DM_SYSTEM_CONFIGURATIONS_DIR)
	mkdir -p $(DM_WORKLOAD_MANIFEST_DIR)
	mkdir -p $(DM_CONFIG_INTERNAL_DIR)/$(FILE_ORCHESTRATION_FOLDER) && cp -R 'src/system_configurations/fileOrchestrationConfig.json' $(DM_CONFIG_INTERNAL_DIR)/$(FILE_ORCHESTRATION_FOLDER)
	mkdir -p $(DM_OMOP_DIR) && cp -R 'src/omop/'* $(DM_OMOP_DIR)
	mkdir -p $(DM_FABRIC_TABLESCHEMAS_DIR) && cp -R 'src/table_schemas/'* $(DM_FABRIC_TABLESCHEMAS_DIR)
	find $(DM_FABRIC_TABLESCHEMAS_DIR) -mindepth 2 -maxdepth 2 -type d -exec sh -c 'mv "{}"/* "$$(dirname "{}")"' \; -exec rm -r "{}" \;
	mkdir -p $(DM_FABRIC_PBI_POA_REPORTS_DIR) && cp 'powerbi/Patient Outreach Analytics BI Report.Report/report.json' 'powerbi/Patient Outreach Analytics BI Report.Report/definition.pbir' 'powerbi/Patient Outreach Analytics BI Report.Report/StaticResources/SharedResources/BaseThemes/CY24SU02.json' $(DM_FABRIC_PBI_POA_REPORTS_DIR)
	mkdir -p $(DM_FABRIC_PBI_POA_DATASETS_DIR) && cp 'powerbi/Patient Outreach Analytics Semantic Model.Dataset/model.bim' 'powerbi/Patient Outreach Analytics Semantic Model.Dataset/definition.pbidataset' $(DM_FABRIC_PBI_POA_DATASETS_DIR)
	mkdir -p $(DM_FABRIC_PBI_CMA_DATASETS_DIR) && cp 'powerbi/Care Management Analytics Semantic Model.Dataset/model.bim' 'powerbi/Care Management Analytics Semantic Model.Dataset/definition.pbism' $(DM_FABRIC_PBI_CMA_DATASETS_DIR)
	mkdir -p $(DM_FABRIC_PBI_CMA_REPORTS_DIR) && cp 'powerbi/Care Management Analytics BI Report.Report/report.json' 'powerbi/Care Management Analytics BI Report.Report/definition.pbir' 'powerbi/Care Management Analytics BI Report.Report/StaticResources/SharedResources/BaseThemes/CY24SU08.json' $(DM_FABRIC_PBI_CMA_REPORTS_DIR)
	rm -rf $(MARKETPLACE_OFFER_DIR)/.build-tmp
	dotnet publish ./src/export/ExportProcessor/ExportProcessor.csproj -c Release -o $(MARKETPLACE_OFFER_DIR)/.build-tmp --nologo
	mkdir -p $(FUNCTIONAPPS_TARGET_DIR)
	rm -f $(FUNCTIONAPPS_TARGET_DIR)/exportprocessor.zip
	cd $(MARKETPLACE_OFFER_DIR)/.build-tmp && zip -r ../functionapps/exportprocessor.zip .
	rm -rf $(MARKETPLACE_OFFER_DIR)/.build-tmp
	mkdir -p $(MARKETPLACE_OFFER_DIR)/standalone-deployment && cp src/infra/standalone-deployment/Deploy-FhirExportFunctionApp.ps1 $(MARKETPLACE_OFFER_DIR)/standalone-deployment/
	cp 'requirements/spark/environment.yml' '$(DM_PACKAGES_DIR)/environment.yml'
	# Include build artifacts validator config in distribution
	mkdir -p $(DIST_DIR)/healthcare-artifacts-validator-config && cp 'src/tools/fabric_depolyment_notebooks/validation_notebooks/build_artifacts_validator_config.json' $(DIST_DIR)/healthcare-artifacts-validator-config/
endef

define build-dm4h-python-package =
	$(1) setup.py bdist_wheel -d $(DM_PACKAGES_DIR) --wheelname $(WHEEL_NAME) --wheelversion $(WHEEL_VERSION)
endef

define format-notebooks =
	$(1) format_notebooks.py "$(DM_HEALTHCARE_ARTIFACTS_DIR)/**/$(DM_NOTEBOOKS_DIR)/*.ipynb" $(2)
endef

pip:
	pip install --upgrade pip

ci-venv-create-setup:
	python3.12 -m venv $(VENV)
	source $(VENV_BIN)activate
	$(VENV_BIN)pip install -r requirements/dev-requirements.txt

verifyvirtualenv:
	@if [ ! -d $(VENV) ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV); \
	fi

build: verifyvirtualenv
	@echo "Build environment installation is user-managed; install requirements/dev-requirements.txt first."
	@echo "Proceeding with build..."
	$(call build, $(VENV_BIN)python3, powershell.exe, dev)

build-prod: verifyvirtualenv
	@echo "Build-prod environment installation is user-managed; install requirements/dev-requirements.txt first."
	@echo "Proceeding with build-prod..."
	$(call build, $(VENV_BIN)python3, powershell.exe, prod)

ci-build: verifyvirtualenv
	$(call build, $(VENV_BIN)python3, pwsh, prod)

install:
	$(VENV_BIN)pip install $(DM_PACKAGES_DIR)/$(WHEEL_NAME_FULL) --force-reinstall

build-install: clean build install

dev-install:
	python3 -m pip install -e .

setup: verifyvirtualenv
	$(VENV_BIN)pip install keyring artifacts-keyring
	$(VENV_BIN)pip install -r requirements/dev-requirements.txt
	$(VENV_BIN)pre-commit install
clean:
	for dir in build dist .coverage coverage.xml htmlcov ; do \
		rm -rf $$dir ; \
	done
	find -iname "*.pyc" -delete

delete-venv:
	for dir in $(VENV) ; do \
		rm -rf $$dir ; \
	done
	find -iname "*.pyc" -delete

integration-tests: verifyvirtualenv
	$(VENV_BIN)pip install -r requirements/dev-requirements.txt
	$(VENV_BIN)pip list
	$(VENV_BIN)python3 src/tools/automation/automation_framework.py --api_token=$(api_token)

lint: verifyvirtualenv
	$(VENV_BIN)pylint src/microsoft/fabric/hls/hds --score y --exit-zero --disable=all --enable=E

security: verifyvirtualenv
	safety check

all: setup build lint

.PHONY: security lint clean setup build venv