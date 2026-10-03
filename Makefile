### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-xeu -o pipefail -O inherit_errexit -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules

# We like colors
# From: https://coderwall.com/p/izxssa/colored-makefile-for-golang-projects
RED=`tput setaf 1`
GREEN=`tput setaf 2`
RESET=`tput sgr0`
YELLOW=`tput setaf 3`

# Python checks
UV?=uv

# installed?
ifeq (, $(shell which $(UV) ))
  $(error "UV=$(UV) not found in $(PATH)")
endif

BACKEND_FOLDER=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

ifdef PLONE_VERSION
PLONE_VERSION := $(PLONE_VERSION)
else
PLONE_VERSION := 6.2.2
endif

ifdef CI
UV_VENV_ARGS :=
else
UV_VENV_ARGS := --python=3.14
endif

VENV_FOLDER=$(BACKEND_FOLDER)/.venv
export VIRTUAL_ENV=$(VENV_FOLDER)
BIN_FOLDER=$(VENV_FOLDER)/bin

# Environment variables to be exported
export PYTHONWARNINGS := ignore
export DOCKER_BUILDKIT := 1

all: build

# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
.PHONY: help
help: ## This help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

requirements-mxdev.txt: pyproject.toml mx.ini ## Generate constraints file
	@echo "$(GREEN)==> Generate constraints file$(RESET)"
	@echo '-c https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt' > requirements.txt
	@uvx 'mxdev[uv]' -c mx.ini

$(VENV_FOLDER): requirements-mxdev.txt ## Install dependencies
	@echo "$(GREEN)==> Install environment$(RESET)"
	@if [[ -d "$(VENV_FOLDER)" ]]; then echo "$(YELLOW)==> Environment already exists at $(VENV_FOLDER)$(RESET)"; else uv venv $(UV_VENV_ARGS) $(VENV_FOLDER); fi
	@uv pip install -r requirements-mxdev.txt

.PHONY: sync
sync: $(VENV_FOLDER) ## Sync project dependencies
	@echo "$(GREEN)==> Sync project dependencies$(RESET)"
	@uv pip install -r requirements-mxdev.txt

instance/etc/zope.ini instance/etc/zope.conf: instance.yaml ## Create instance configuration
	@echo "$(GREEN)==> Create instance configuration$(RESET)"
	@uvx cookiecutter -f --no-input -c 3.1.0 --config-file instance.yaml gh:plone/cookiecutter-zope-instance

.PHONY: config
config: instance/etc/zope.ini

.PHONY: install
install: $(VENV_FOLDER) config stack-build ## Install Plone and dependencies, and build the Docker stack

# Docker stack: Varnish (8001) -> Nginx VirtualHostMonster (8002) -> Plone (8003)
.PHONY: stack-build
stack-build: ## Build the Varnish, Nginx and Plone Docker images
	@echo "$(GREEN)==> Build Docker stack$(RESET)"
	@docker compose build

.PHONY: stack-start
stack-start: ## Start the Docker stack, Varnish on localhost:8001
	@echo "$(GREEN)==> Start Docker stack$(RESET)"
	@docker compose up -d

.PHONY: stack-stop
stack-stop: ## Stop the Docker stack
	@echo "$(GREEN)==> Stop Docker stack$(RESET)"
	@docker compose down

.PHONY: stack-test
stack-test: ## Test the Varnish VCL against the running Docker stack
	@./scripts/test-vcl.sh

.PHONY: stack-logs
stack-logs: ## Follow the logs of the Docker stack
	@docker compose logs -f

.PHONY: stack-remove-data
stack-remove-data: ## Stop the Docker stack and remove its Plone data
	@echo "$(RED)==> Removing Docker stack data$(RESET)"
	@docker compose down -v


.PHONY: clean
clean: ## Clean installation and instance (data left intact)
	@echo "$(RED)==> Cleaning environment and build$(RESET)"
	@rm -rf $(VENV_FOLDER) pyvenv.cfg .installed.cfg instance/etc .venv .pytest_cache .ruff_cache constraints* requirements*

.PHONY: remove-data
remove-data: ## Remove all content
	@echo "$(RED)==> Removing all content$(RESET)"
	rm -rf $(VENV_FOLDER) instance/var

.PHONY: start
start: $(VENV_FOLDER) instance/etc/zope.ini ## Start a Plone instance on localhost:8080
	@$(BIN_FOLDER)/runwsgi instance/etc/zope.ini

.PHONY: console
console: $(VENV_FOLDER) instance/etc/zope.ini ## Start a console into a Plone instance
	@$(BIN_FOLDER)/zconsole debug instance/etc/zope.conf

.PHONY: create-site
create-site: $(VENV_FOLDER) instance/etc/zope.ini ## Create a new site from scratch
	@$(BIN_FOLDER)/zconsole run instance/etc/zope.conf ./scripts/create_site.py

# QA
.PHONY: lint
lint: ## Check and fix code base according to Plone standards
	@echo "$(GREEN)==> Lint codebase$(RESET)"
	@uvx ruff@latest check --fix --config $(BACKEND_FOLDER)/pyproject.toml
	@uvx pyroma@latest -d .
	@uvx check-python-versions@latest .
	@uvx zpretty@latest --check src

.PHONY: format
format: ## Check and fix code base according to Plone standards
	@echo "$(GREEN)==> Format codebase$(RESET)"
	@uvx ruff@latest check --select I --fix --config $(BACKEND_FOLDER)/pyproject.toml
	@uvx ruff@latest format --config $(BACKEND_FOLDER)/pyproject.toml
	@uvx zpretty@latest -i src

.PHONY: check
check: format lint ## Check and fix code base according to Plone standards

# i18n
.PHONY: i18n
i18n: $(VENV_FOLDER) ## Update locales
	@echo "$(GREEN)==> Updating locales$(RESET)"
	@$(BIN_FOLDER)/python -m collective.matomoaitracker.locales

# Tests
.PHONY: test
test: $(VENV_FOLDER) ## run tests
	@$(BIN_FOLDER)/pytest

.PHONY: test-coverage
test-coverage: $(VENV_FOLDER) ## run tests with coverage
	@$(BIN_FOLDER)/pytest --cov=collective.matomoaitracker --cov-report term-missing

## Add bobtemplates features (check bobtemplates.plone's documentation to get the list of available features)
add: $(VENV_FOLDER)
	@uvx plonecli add $(filter-out $@,$(MAKECMDGOALS))

.PHONY: release
release: $(VENV_FOLDER) ## Create a release
	@echo "$(GREEN)==> Create a release$(RESET)"
	@uv pip install -e ".[release]"
	@uv run fullrelease
