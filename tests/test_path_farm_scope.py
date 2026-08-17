"""Guard: the PATH farm is a session-level constant, built once per drop-set, in ONE place.

Business rule this protects: several suites need to prove a script behaves correctly when a
binary is ABSENT, without asserting anything about the host. They do it by building a "PATH
farm" - a directory of symlinks re-exposing the ambient PATH with a few names left out - and
running the script against that. A farm is a PURE FUNCTION of `(ambient PATH, drop-set)`: no
test-specific input enters it, and no test mutates it. It is therefore a SESSION-level constant.

It was not treated as one. Three suites each grew their own differently-named helper anchored to
the per-test `tmp_path` fixture, so a session rebuilt the same constant once per test that needed
it - tens of thousands of symlinks per run, and pytest's unset retention defaults then kept
several complete copies of the result. The size is host-dependent by construction (the helper
globs the ambient PATH), so this is not a fixed number of inodes; it is a multiplier on whatever
the host's PATH happens to be.

Four things must hold, and they are deliberately of different kinds - a cache regression, a
correctness regression, a config regression and a duplication regression each fail differently:

  1. the SAME drop-set yields the IDENTICAL directory, within a test and ACROSS tests, and the
     farm lives at session scope rather than inside a per-test `tmp_path`;
  2. DIFFERENT drop-sets yield DIFFERENT directories, each re-exposing everything except its own
     dropped names - the invariant all three original helpers self-validated locally;
  3. pytest's retention settings are effective (read through pytest's OWN config object, so a
     config file in a location pytest does not read cannot satisfy this);
  4. no file under `tests/` builds a farm inline any more - `tests/conftest.py` is the only place
     the loop may live, because THREE independent copies is how this defect arose in the first
     place.

The static half (4) is a pure function of source text, exercised below against a probe corpus of
alternate shapes, so it cannot pass by recognising only today's spelling.
"""
from __future__ import annotations

import ast
import os
import shutil
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
CONFTEST = TESTS_DIR / "conftest.py"

# Observations shared between the two identity tests below. A farm that is genuinely built once
# per session must look identical no matter which test asks for it - and asserting that ACROSS
# tests is what a single in-test comparison cannot show (a per-test rebuild would still return one
# consistent value inside one test).
_OBSERVED: dict[frozenset, tuple] = {}


def _pick_present_binaries(n: int) -> list[str]:
    """`n` binary names that really are on this host's PATH (and are not `bash`).

    Dropping a name the host does not have would make every "unreachable" assertion below
    vacuously true - the guard would go green on a farm that dropped nothing at all.
    """
    found = [
        name
        for name in ("ls", "cat", "env", "grep", "sed", "awk", "cut", "tr")
        if name != "bash" and shutil.which(name)
    ]
    if len(found) < n:
        pytest.skip(f"host PATH exposes fewer than {n} usable probe binaries: {found}")
    return found[:n]


def _record(drop: frozenset, farm: Path) -> None:
    entries = sorted(p.name for p in farm.iterdir())
    fact = (str(farm), farm.stat().st_ino, len(entries))
    previous = _OBSERVED.setdefault(drop, fact)
    assert previous == fact, (
        f"the farm for drop-set {sorted(drop)} changed between requests: first seen as "
        f"{previous}, now {fact}. It is a pure function of (PATH, drop-set), so it must be built "
        f"AT MOST ONCE per session - a second directory means the session-level constant is "
        f"being rebuilt per test again."
    )


# ---------------------------------------------------------------------------
# 1 - one farm per drop-set, at session scope
# ---------------------------------------------------------------------------


def test_same_drop_set_returns_the_identical_farm(path_farm, tmp_path, tmp_path_factory):
    drop = frozenset(_pick_present_binaries(1))
    first = path_farm(drop=drop)
    entries_after_first = sorted(p.name for p in first.iterdir())
    second = path_farm(drop=drop)
    entries_after_second = sorted(p.name for p in second.iterdir())

    assert first == second, (
        "two requests for the same drop-set must return the SAME directory - a second path means "
        f"a second full symlink tree was built. Got {first} then {second}."
    )
    assert entries_after_first == entries_after_second, (
        "the farm must not grow on a repeat request: the second call is meant to be a cache hit, "
        f"not a rebuild ({len(entries_after_first)} -> {len(entries_after_second)} entries)."
    )
    assert first.parent == tmp_path_factory.getbasetemp(), (
        "the farm must live at the SESSION temp root, not inside a per-test directory - anchoring "
        f"it to a per-test dir is exactly what made a session-level constant per-test state. "
        f"Farm parent: {first.parent}"
    )
    assert tmp_path not in first.parents and first.parent != tmp_path, (
        f"the farm must not live under this test's own tmp_path ({tmp_path})"
    )
    _record(drop, first)


def test_the_same_farm_is_reused_across_tests(path_farm):
    """The cross-test half: a farm rebuilt per test would still be self-consistent WITHIN a test.

    Written so it holds in either execution order and when run alone - the first test to arrive
    records, every later one compares.
    """
    drop = frozenset(_pick_present_binaries(1))
    _record(drop, path_farm(drop=drop))
    assert drop in _OBSERVED


def test_path_farm_factory_is_declared_session_scoped():
    """Defence in depth for (1): the memoisation and the scope must BOTH say session.

    The module-level cache currently makes the observable behaviour survive a scope regression,
    so a scope silently narrowed to `function` would go unnoticed until someone removed the cache
    - at which point the whole defect returns. Assert the declared scope too.
    """
    scope = _fixture_scope(CONFTEST.read_text(encoding="utf-8"), "path_farm")
    assert scope == "session", (
        f"the `path_farm` fixture must be declared scope='session'; found {scope!r}. Per-test "
        f"scope is what rebuilt this constant once per test."
    )


# ---------------------------------------------------------------------------
# 2 - distinct drop-sets, and the absence each one exists to create
# ---------------------------------------------------------------------------


def test_distinct_drop_sets_get_distinct_farms_with_the_right_absences(path_farm):
    """The correctness invariant every original helper self-validated, asserted once here.

    A cache keyed on anything less than the drop-set would hand one caller another caller's farm,
    and the "absent binary" a test depends on would silently be REACHABLE - the test would still
    pass while exercising a completely different code path.
    """
    first, second = _pick_present_binaries(2)
    drop_a = frozenset({first})
    drop_b = frozenset({first, second})
    farm_a = path_farm(drop=drop_a)
    farm_b = path_farm(drop=drop_b)

    assert farm_a != farm_b, (
        "two different drop-sets must get two different farms - sharing one directory makes a "
        f"dropped binary reachable for the caller that needed it gone. Both were {farm_a}."
    )
    assert shutil.which(first, path=str(farm_a)) is None
    assert shutil.which(first, path=str(farm_b)) is None
    assert shutil.which(second, path=str(farm_a)) is not None, (
        f"{second!r} was NOT dropped from farm A, so it must still be reachable through it - a "
        f"farm that drops more than it was asked to stops exercising the real code path"
    )
    assert shutil.which(second, path=str(farm_b)) is None, (
        f"{second!r} was dropped from farm B and must be unreachable through it"
    )
    for farm in (farm_a, farm_b):
        assert shutil.which("bash", path=str(farm)), (
            "every farm must keep the binaries a script legitimately needs (bash) - a farm that "
            "drops those makes the test fail for the wrong reason"
        )
    _record(drop_a, farm_a)
    _record(drop_b, farm_b)


def test_a_farm_exposes_only_executables(path_farm):
    """A farm stands in for a PATH, so everything reachable through it must be executable.

    Dropping the `os.access(..., X_OK)` filter would link every regular file on every PATH entry -
    both inflating the tree the fix exists to shrink and making a non-executable file look like an
    available binary to the code under test.
    """
    farm = path_farm(drop=frozenset(_pick_present_binaries(1)))
    non_executable = [
        p.name for p in farm.iterdir() if not os.access(p, os.X_OK) or p.is_dir()
    ]
    assert non_executable == [], (
        "a PATH farm must expose executables only (no directories, nothing without +x): "
        f"{non_executable[:10]}"
    )


# ---------------------------------------------------------------------------
# 3 - retention, read through pytest's own effective config
# ---------------------------------------------------------------------------


def test_tmp_path_retention_is_bounded(pytestconfig):
    """Read via `getini`, so the assertion is about the config pytest ACTUALLY applied.

    Grepping a `pytest.ini` would pass just as happily when the file sits somewhere pytest never
    reads it, or when a `[tool.pytest.ini_options]` table supersedes it. `getini` cannot be
    fooled either way: with no effective config it returns pytest's defaults (`all` / `3`), which
    fail here.
    """
    policy = pytestconfig.getini("tmp_path_retention_policy")
    count = int(pytestconfig.getini("tmp_path_retention_count"))
    assert policy != "all", (
        "tmp_path_retention_policy must not be `all` - retaining every passing test's tmp_path is "
        "how a single run's throwaway trees survive to multiply across runs (pytest's DEFAULT is "
        "`all`, so seeing it here usually means no config is in effect at all)"
    )
    assert count <= 1, (
        f"tmp_path_retention_count must be <= 1, found {count} - pytest's default of 3 keeps three "
        f"complete copies of whatever one run produced"
    )


# ---------------------------------------------------------------------------
# 4 - exactly one farm-building loop in the whole suite
# ---------------------------------------------------------------------------

_SYMLINK_ATTRS = {"symlink_to", "symlink", "hardlink_to", "link"}
_PATH_READERS = {"getenv", "get"}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _makes_a_link(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute) and func.attr in _SYMLINK_ATTRS:
                return True
            if isinstance(func, ast.Name) and func.id in _SYMLINK_ATTRS:
                return True
    return False


def _reads_the_ambient_path(node: ast.AST) -> bool:
    """True when `node` reads the ambient PATH, in any of its spellings."""
    for sub in ast.walk(node):
        # os.environ["PATH"] / environ["PATH"]
        if isinstance(sub, ast.Subscript):
            target = _dotted(sub.value)
            if target.endswith("environ") and isinstance(sub.slice, ast.Constant):
                if sub.slice.value == "PATH":
                    return True
        # os.environ.get("PATH") / os.getenv("PATH")
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in _PATH_READERS and sub.args:
                first = sub.args[0]
                if isinstance(first, ast.Constant) and first.value == "PATH":
                    return True
    return False


def _fixture_scope(source: str, name: str) -> str | None:
    """The declared scope of fixture `name` in `source`, or None when it is not a fixture."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != name:
            continue
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            target = _dotted(call.func) if call else _dotted(dec)
            if not target.endswith("fixture"):
                continue
            if call:
                for kw in call.keywords:
                    if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
            return "function"  # a bare @fixture defaults to function scope
    return None


def farm_builders_in_source(source: str, label: str = "<source>") -> list[str]:
    """Names of the functions in `source` that build a PATH farm inline. Empty == compliant.

    "Builds a farm" = creates links AND reads the ambient PATH in the same function. Either one
    alone is innocent (plenty of code stubs a PATH, plenty of code makes a symlink); together
    they are the loop that must exist in exactly one place.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - a broken test file fails elsewhere
        return [f"{label}: unparseable ({exc})"]
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _makes_a_link(node) and _reads_the_ambient_path(node):
                findings.append(f"{label}:{node.lineno}: {node.name}")
    return findings


def test_only_conftest_builds_a_path_farm():
    """The duplication guard - and it asserts conftest STILL builds one, not merely that others
    do not. Three independent copies of this loop is the defect; zero copies would mean the
    shared fixture was gutted and every consumer re-grew its own."""
    builders = {}
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(TESTS_DIR))
        found = farm_builders_in_source(path.read_text(encoding="utf-8"), rel)
        if found:
            builders[rel] = found
    assert list(builders) == ["conftest.py"], (
        "tests/conftest.py must be the ONLY place a PATH farm is constructed - three independent "
        "copies of this loop, one per suite, is exactly the state being fixed. Builders found: "
        f"{builders}"
    )


# ---------------------------------------------------------------------------
# Probe corpus for the static guard - the committed red-before-green proof.
# ---------------------------------------------------------------------------

_BUILDER_MUST_CATCH = [
    (
        "pathlib symlink_to over os.environ[PATH]",
        "import os\n"
        "def _shadowed_path(tmp_path, drop):\n"
        "    farm = tmp_path / 'path-shadowed'\n"
        "    farm.mkdir()\n"
        "    for entry in os.environ['PATH'].split(os.pathsep):\n"
        "        (farm / 'x').symlink_to(entry)\n"
        "    return farm\n",
    ),
    (
        "os.symlink over os.environ.get(PATH)",
        "import os\n"
        "def _hermetic_path(tmp_path, drop):\n"
        "    for entry in os.environ.get('PATH', '').split(os.pathsep):\n"
        "        os.symlink(entry, tmp_path / 'y')\n"
        "    return tmp_path\n",
    ),
    (
        "os.getenv(PATH) spelling",
        "import os\n"
        "def _client_free_path(tmp_path):\n"
        "    for entry in os.getenv('PATH').split(os.pathsep):\n"
        "        (tmp_path / 'z').symlink_to(entry)\n"
        "    return tmp_path\n",
    ),
    (
        "nested inside a harness class method",
        "import os\n"
        "class Harness:\n"
        "    def _farm(self, tmp_path):\n"
        "        for entry in os.environ['PATH'].split(os.pathsep):\n"
        "            (tmp_path / 'q').symlink_to(entry)\n"
        "        return tmp_path\n",
    ),
    (
        "hidden in a nested helper",
        "import os\n"
        "def outer(tmp_path):\n"
        "    def build():\n"
        "        for e in os.environ['PATH'].split(os.pathsep):\n"
        "            (tmp_path / 'n').symlink_to(e)\n"
        "    return build\n",
    ),
]

_BUILDER_MUST_NOT_CATCH = [
    (
        "a stub dir prepended to PATH, no links",
        "import os\n"
        "def _stub_path(tmp_path):\n"
        "    return os.pathsep.join([str(tmp_path), os.environ['PATH']])\n",
    ),
    (
        "a symlink that has nothing to do with PATH",
        "def test_symlinked_addons(tmp_path):\n"
        "    (tmp_path / 'link').symlink_to(tmp_path / 'real')\n",
    ),
    (
        "consuming the shared fixture",
        "def test_uses_the_fixture(path_farm):\n"
        "    farm = path_farm(drop=('psql',))\n"
        "    assert farm.is_dir()\n",
    ),
]


@pytest.mark.parametrize(
    "shape,source", _BUILDER_MUST_CATCH, ids=[s for s, _ in _BUILDER_MUST_CATCH]
)
def test_builder_guard_catches_every_inline_farm_shape(shape, source):
    assert farm_builders_in_source(source, "probe.py"), (
        f"the duplication guard let a {shape} through. The three helpers it replaced were all "
        f"named differently and spelled the PATH read differently - a guard keyed on one "
        f"spelling would have missed two of the three it exists to prevent."
    )


@pytest.mark.parametrize(
    "shape,source", _BUILDER_MUST_NOT_CATCH, ids=[s for s, _ in _BUILDER_MUST_NOT_CATCH]
)
def test_builder_guard_leaves_innocent_code_alone(shape, source):
    assert farm_builders_in_source(source, "probe.py") == [], (
        f"the duplication guard fired on innocent code ({shape}): "
        f"{farm_builders_in_source(source, 'probe.py')}. Stubbing a PATH and making a symlink are "
        f"both ordinary; only doing BOTH in one function is the farm loop."
    )


@pytest.mark.parametrize(
    "decorator,expected",
    [
        ("@pytest.fixture(scope='session')", "session"),
        ('@pytest.fixture(scope="module")', "module"),
        ("@pytest.fixture", "function"),
        ("@pytest.fixture()", "function"),
    ],
)
def test_fixture_scope_reader_sees_every_declaration_form(decorator, expected):
    """The scope reader must not report `session` for a narrowed or bare declaration."""
    source = f"import pytest\n{decorator}\ndef path_farm():\n    return 1\n"
    assert _fixture_scope(source, "path_farm") == expected
