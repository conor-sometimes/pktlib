"""The Python in README.md and docs/ runs. Blocks that leave something out ("...") are skipped;
each block runs after the ones before it in the same file, in a scratch directory."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
BLOCK = re.compile(r"```python\n(.*?)```", re.S)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_python_in_docs_runs(doc, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scope: dict = {}
    blocks = [b for b in BLOCK.findall(doc.read_text()) if "..." not in b]
    for code in blocks:
        exec(compile("import pktlib\n" + code, f"{doc.name} block", "exec"), scope)


def test_docs_link_to_files_that_exist():
    for doc in DOCS:
        for target in re.findall(r"\]\(([^)#:]+)(?:#[^)]*)?\)", doc.read_text()):
            assert (doc.parent / target).exists(), f"{doc.name} links to {target}"


def test_the_readme_links_work_on_pypi_too():
    """PyPI shows the README with nothing to resolve relative links against: they must be
    full GitHub links, to files that exist."""
    text = (ROOT / "README.md").read_text()
    assert not re.findall(r"\]\((?!https?://)[^)]+\)", text)
    for path in re.findall(r"github\.com/conor-sometimes/pktlib/blob/main/([^)#\s]+)", text):
        assert (ROOT / path).exists(), f"README links to {path}"


def test_the_examples_index_is_up_to_date():
    import runpy

    mod = runpy.run_path(str(ROOT / "scripts" / "examples.py"))
    assert (ROOT / "examples" / "README.md").read_text() == mod["index"](), (
        "run: uv run python scripts/examples.py index"
    )
