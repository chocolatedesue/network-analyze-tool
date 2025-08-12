# Repository Guidelines

This repository contains tools for generating network topologies and analyzing traffic. It mixes a Python 3.12 codebase (CLI + analysis utilities) with a small Go component for convergence analysis.

## Project Structure & Module Organization
- `topo_gen/`: Python package and `topo-gen` CLI for generating OSPFv6/ISIS/BGP topologies and configs.
- `experiment_utils/`: Analysis utilities (e.g., `draw/draw_pcap.py`, plotting, batch runners).
- `packet-analyze/`: PCAP drawing and examples.
- `converge_analyze/`: Go program and sources (`main.go`) for convergence analysis.
- `data/`, `results/`, `build/`: Input/output artifacts and generated assets.
- `isis_torus5x5/`, `ospf6_torus5x5/`: Sample containerlab outputs and configs.
- Tests live at the repo root (e.g., `test_protocol_detection.py`) and `test/` for helpers.

## Build, Test, and Development Commands
- Setup (recommended): `uv sync` or `uv pip install -e .[dev]` to install deps into `.venv`.
- Run CLI: `uv run topo-gen generate torus 5 -y` (or `grid 5`).
- Python tests: `uv run pytest -q` or `uv run pytest -q test_protocol_detection.py`.
- Lint/format: `uv run black . && uv run isort . && uv run flake8`.
- Types: `uv run mypy topo_gen`.
- Go build: `cd converge_analyze && go build -o converge_analyze` (or `go run main.go`).

## Coding Style & Naming Conventions
- Python: 4-space indent, type hints required for public functions, snake_case for functions/modules, PascalCase for classes. Prefer docstrings for CLI commands and library functions.
- Formatting: Black (default line length), import ordering via isort, basic linting via flake8; keep warnings at zero.
- Go: follow `gofmt`/`go vet` defaults; keep packages small and focused.

## Testing Guidelines
- Framework: pytest. Name tests `test_*.py`. Keep unit tests close to modules or under `tests/`.
- Coverage: target critical paths in `topo_gen` and `experiment_utils/draw`. Include example-driven tests for protocol detection and filename parsing.
- Run: `uv run pytest -q` locally before opening a PR.

## Commit & Pull Request Guidelines
- Commits: imperative mood and concise scope, e.g., `topo_gen: fix OSPF6 SPF delay parsing`. Current history is terse; adopting Conventional Commits is welcome.
- PRs: include a clear description, linked issues, reproduction steps, and relevant artifacts (e.g., sample commands, generated config paths under `build/`, or plot screenshots).
- CI (if added later): ensure lint, type-check, and tests pass before merge.

## Security & Configuration Tips
- Avoid committing large PCAPs; keep them under `data/` and reference in docs/scripts. Validate generated configs before deploying to labs.
