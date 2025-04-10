.PHONY: init
init:
	test -f .env || cp .env.template .env
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

.PHONY: run
run:
	python main.py

.PHONY: lint
lint:
	ruff --version
	ruff check
	ruff format --check
	mypy .

.PHONY: fmt
fmt:
	ruff --version
	ruff format
	ruff check --fix
