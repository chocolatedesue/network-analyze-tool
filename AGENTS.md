# Repository Guidelines

This repository provides tools for generating network topologies and analyzing traffic. It mixes a Python 3.12 codebase (CLI + analysis utilities) with a small Go component for convergence analysis.

## Project Structure & Module Organization
- `topo_gen/`: Python package; `topo-gen` CLI for OSPFv6/ISIS/BGP config generation.
- `experiment_utils/`: Analysis utilities (e.g., `draw/draw_pcap.py`, plotting, batch runners).
- `packet-analyze/`: PCAP drawing and runnable examples.
- `converge_analyze/`: Go program (`main.go`) for convergence analysis.
- `data/`, `results/`, `build/`: Inputs, outputs, and generated assets.
- `isis_torus5x5/`, `ospf6_torus5x5/`: Sample containerlab outputs/configs.
- Tests: root-level tests (e.g., `test_protocol_detection.py`) and helpers under `test/`.

## Build, Test, and Development Commands
- Setup env: `uv sync` or `uv pip install -e .[dev]` (creates `.venv`).
- Run CLI: `uv run topo-gen generate torus 5 -y` (or `grid 5`).
- Python tests: `uv run pytest -q` (target a file: `uv run pytest -q test_protocol_detection.py`).
- Format/lint: `uv run black . && uv run isort . && uv run flake8`.
- Types: `uv run mypy topo_gen`.
- Go build: `cd converge_analyze && go build -o converge_analyze` (or `go run main.go`).

## Coding Style & Naming Conventions
- Python: 4-space indent; type hints for public functions; `snake_case` for functions/modules; `PascalCase` for classes; docstrings for CLI and library functions.
- Formatting: Black (default line length), import ordering via isort, flake8 with zero warnings.
- Go: follow `gofmt` and `go vet`; keep packages small and focused.

## Testing Guidelines
- Framework: pytest. Name tests `test_*.py`; keep near modules or under `test/`.
- Coverage: prioritize critical paths in `topo_gen` and `experiment_utils/draw`; include example-driven tests (protocol detection, filename parsing).
- Run locally before PR: `uv run pytest -q`.

## Commit & Pull Request Guidelines
- Commits: imperative mood and concise scope (e.g., `topo_gen: fix OSPF6 SPF delay parsing`). Conventional Commits welcome.
- PRs: include description, linked issues, repro steps, and artifacts (e.g., sample commands, generated config paths under `build/`, or plot screenshots). Ensure lint, type-check, and tests pass.

## Security & Configuration Tips
- Avoid committing large PCAPs; keep under `data/` and reference in docs/scripts.
- Validate generated configs before deploying to labs.

