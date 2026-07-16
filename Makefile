# Toroid — one-command entry points. `make demo` is the cold-clone showcase: it needs
# no API key and no OSS CAD Suite (Yosys arrives via the `yowasp-yosys` dev extra).
#
# Note: the buggy-FIFO and impostor-equivalence targets are EXPECTED to exit non-zero —
# a FALSIFIED verdict is a real failure signal, and catching it is the whole point. The
# `-` prefix lets the demo continue so you see every artifact.
.PHONY: help install demo test integration lint typecheck check chart screenshot clean

help:
	@echo "make install     - pip install -e .[dev]  (includes yowasp-yosys)"
	@echo "make demo        - the flagship: prove, catch a real bug, check equivalence"
	@echo "make test        - unit tests (fast, offline)"
	@echo "make integration - live end-to-end (real proofs via Yosys; sby if present)"
	@echo "make check       - lint + typecheck + unit tests"
	@echo "make chart       - regenerate the README's bug-catch chart (needs .[bench])"
	@echo "make screenshot  - regenerate the README's demo screenshot (needs .[bench])"
	@echo "make clean       - remove build/solver artifacts"

install:
	pip install -e ".[dev]"

# Run from the repo root: yowasp-yosys is sandboxed to the CWD.
demo:
	@echo "== 1. Clean FIFO — the flag/occupancy invariants hold =="
	toroid verify designs/fifo.v --top fifo --no-llm --props designs/fifo.props.json
	@echo ""
	@echo "== 2. Buggy FIFO — off-by-one 'full' caught with a counterexample (exit 1 expected) =="
	-toroid verify designs/fifo_buggy.v --top fifo --no-llm --props designs/fifo.props.json
	@echo ""
	@echo "== 3. RTL-to-RTL equivalence — proven, then a distinguishing input (exit 1 expected) =="
	toroid equiv designs/max2.v designs/max2_alt.v --top-a max2 --top-b max2_alt
	-toroid equiv designs/max2.v designs/max2_min_bug.v --top-a max2 --top-b max2_min_bug

test:
	pytest

integration:
	pytest -m integration

lint:
	ruff check .

typecheck:
	mypy

check: lint typecheck test

# The README embeds docs/img/bugcatch.png, but the generator writes to the gitignored
# benchmarks/out/. Without this target the committed image silently drifts from the code
# that makes it (it did: it kept the pre-rename title). Regenerate AND install it here.
chart:
	pip install -e ".[bench]"
	python -m benchmarks.bugcatch
	cp benchmarks/out/bugcatch.png docs/img/bugcatch.png
	@echo "installed docs/img/bugcatch.png (commit it if it changed)"

# Renders docs/img/demo.png by RUNNING the demo and painting its real stdout — so the
# README's hero image can't drift from what the tool actually prints.
screenshot:
	pip install -e ".[bench]"
	python -m benchmarks.screenshot
	@echo "installed docs/img/demo.png (commit it if it changed)"

clean:
	rm -rf designs/_build benchmarks/out .pytest_cache .mypy_cache .hypothesis
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
