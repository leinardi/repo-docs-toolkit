#
# MIT License
#
# Copyright (c) 2026 Roberto Leinardi
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

ifndef MK_LOCAL_TEST_INCLUDED
MK_LOCAL_TEST_INCLUDED := 1

PYTHON ?= python3
CLAUDE ?= claude

# uv runs the tests when it is installed: it resolves requirements-dev.txt into a cached
# environment with no virtualenv to manage, and it works where pip refuses to touch the system
# interpreter (PEP 668). An explicit PYTHON= on the command line wins.
UV := $(shell command -v uv 2>/dev/null)
ifeq ($(origin PYTHON),command line)
UV :=
endif

UV_RUN = $(UV) run --no-project --with-requirements $(REPO_ROOT)/requirements-dev.txt python

.PHONY: dev-deps
dev-deps: ## Install the pinned Python development dependencies (pytest)
ifneq ($(strip $(UV)),)
	@$(UV_RUN) -c 'import pytest'
	@printf 'dev dependencies ready in uv'"'"'s cache; make test uses them automatically.\n'
else
	@$(PYTHON) -m pip install -r $(REPO_ROOT)/requirements-dev.txt
endif

.PHONY: test
test: test-unit ## Run the test suite

.PHONY: test-unit
test-unit: ## Run the Python unit tests (docstool, sync-vendored, skill lint, release bump)
ifneq ($(strip $(UV)),)
	@$(UV_RUN) -m pytest
else
	@$(PYTHON) -m pytest
endif

# The tests that need Zensical run in the docs uv environment (tools/docs/uv.lock, zensical.mk's
# DOCS_UV_RUN), with the test dependencies added on top; nothing is installed into the system Python.
DOCS_TEST_RUN = $(DOCS_UV_RUN) --with-requirements $(REPO_ROOT)/requirements-dev.txt
DOCS_A11Y_RUN = $(DOCS_TEST_RUN) --with-requirements $(REPO_ROOT)/requirements/a11y.txt

.PHONY: test-zensical
test-zensical: ## Run the tests that need the pinned Zensical (through uv, from tools/docs/uv.lock)
	@DOCSTOOL_REQUIRE_ZENSICAL=1 $(DOCS_TEST_RUN) python -m pytest -m zensical

.PHONY: test-landing
test-landing: ## Build the landing examples strict and check their HTML (through uv)
	@DOCSTOOL_REQUIRE_ZENSICAL=1 $(DOCS_TEST_RUN) python -m pytest -m zensical $(REPO_ROOT)/tests/test_landing_build.py

.PHONY: a11y-browser
a11y-browser: ## Download the Chromium the accessibility tests use (Playwright; CI adds --with-deps)
	@$(DOCS_A11Y_RUN) python -m playwright install $(A11Y_BROWSER_FLAGS) chromium

.PHONY: test-a11y
test-a11y: ## Run the landing page accessibility tests (through uv; run make a11y-browser once)
	@DOCSTOOL_REQUIRE_ZENSICAL=1 DOCSTOOL_REQUIRE_A11Y=1 $(DOCS_A11Y_RUN) python -m pytest -m a11y

DOCSTOOL := $(REPO_ROOT)/skills/repo-docs/scripts/docstool.py

# The plugin's own site, built strict by docstool into a fresh temporary directory (removed on
# exit) and checked the way the skills check a user's site. Any finding or incomplete coverage fails.
# docstool runs in the docs uv environment, so site-build finds that environment's zensical.
# (zensical.mk's docs-build is the plain build; docs-serve serves it with live reload.)
DOCSTOOL_RUN = $(DOCS_UV_RUN) python -I $(DOCSTOOL)

.PHONY: docs-verify
docs-verify: ## Build the plugin's own site strict and check it with docstool (through uv)
	@out="$$(mktemp -d)" && trap 'rm -rf "$$out"' EXIT && cd $(REPO_ROOT) && \
	$(DOCSTOOL_RUN) site-build --out "$$out" && \
	$(DOCSTOOL_RUN) check --scope docs --built "$$out" && \
	$(DOCSTOOL_RUN) check --scope repo && \
	$(DOCSTOOL_RUN) site-audit && \
	$(DOCSTOOL_RUN) drift --scope docs && \
	$(DOCSTOOL_RUN) drift --scope repo && \
	$(DOCSTOOL_RUN) readme --home docs/index.md

.PHONY: sync-vendored
sync-vendored: ## Copy skills/repo-docs/scripts/docstool.py into the other skills
	@$(PYTHON) -I $(REPO_ROOT)/scripts/sync-vendored.py

.PHONY: check-vendored
check-vendored: ## Fail if a vendored docstool.py differs from the canonical copy
	@$(PYTHON) -I $(REPO_ROOT)/scripts/sync-vendored.py --check

.PHONY: validate-plugin
validate-plugin: ## Validate the plugin and marketplace manifests (claude plugin validate --strict)
	@cd $(REPO_ROOT) && $(CLAUDE) plugin validate . --strict

endif  # MK_LOCAL_TEST_INCLUDED
