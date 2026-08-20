"""NFR-8 / FR-4.1: the value-semantics module contains no model call and no network call.

This is the test that makes the architecture claim true rather than aspirational. §3.4's whole
argument is that anything with a knowable right answer belongs in deterministic code, because a
model that converts inches to millimetres incorrectly is wrong *plausibly*, and plausible-wrong is
unfalsifiable at review time.

Enforcement is in two layers, because either alone is escapable:

  * a static scan of every source file in the package for imports that could reach a network or a
    model, and
  * a runtime test that severs the socket layer entirely and then exercises the full API.
"""

from __future__ import annotations

import ast
import socket
import textwrap
from pathlib import Path

import pytest

import errata_valuesem
from errata_valuesem import Kind, compare, normalize

PACKAGE_ROOT = Path(errata_valuesem.__file__).parent

#: Import roots that would put a network hop or an inference call in the hot path.
FORBIDDEN_ROOTS = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "httpx",
        "requests",
        "urllib",
        "urllib3",
        "aiohttp",
        "websockets",
        "ftplib",
        "smtplib",
        "telnetlib",
        "xmlrpc",
        "openai",
        "anthropic",
        "cohere",
        "google",
        "boto3",
        "botocore",
        "transformers",
        "torch",
        "tensorflow",
        "sentence_transformers",
        "litellm",
        "langchain",
        "llama_index",
        "ollama",
        "subprocess",
        # -- added by the R0 determinism audit ------------------------------------------------
        # The C accelerator modules. Banning "socket" while leaving "_socket" reachable was the
        # hole: `import _socket` passed this scan AND survived the severing test below, because
        # monkeypatching the socket module's attributes leaves _socket.socket untouched.
        "_socket",
        "_ssl",
        # ctypes can dlopen a network library and call it, entirely outside Python's import graph.
        "ctypes",
        # Process and event-loop surfaces that reach a network or a shell without `subprocess`.
        "asyncio",
        "multiprocessing",
        "socketserver",
        "selectors",
        "pty",
        # Remaining stdlib/third-party network clients not already listed.
        "imaplib",
        "poplib",
        "nntplib",
        "paramiko",
        "pycurl",
        "grpc",
        "zmq",
    }
)

#: Dotted call targets that reach a network, a shell, or a model *without* an import statement the
#: AST scan above can see. `from importlib import resources` is legitimate and stays legal --
#: packaged grammars and ontologies are read that way -- but `importlib.import_module` is not.
FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "importlib.import_module",
        "importlib.__import__",
        "exec",
        "eval",
        "compile",
        "os.system",
        "os.popen",
        "os.execv",
        "os.execve",
        "os.execl",
        "os.execlp",
        "os.execvp",
        "os.spawnv",
        "os.spawnl",
        "os.fork",
        "os.forkpty",
        "ctypes.CDLL",
        "ctypes.WinDLL",
        "ctypes.windll",
    }
)


def _dotted_name(node: ast.AST) -> str:
    """Render ``os.popen`` / ``importlib.import_module`` from a call's func expression."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _source_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_there_are_source_files_to_scan() -> None:
    # A scan that silently finds nothing would pass forever.
    assert len(_source_files()) >= 8


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_forbidden_imports(path: Path) -> None:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                alias.name for alias in node.names if alias.name.split(".")[0] in FORBIDDEN_ROOTS
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and node.module.split(".")[0] in FORBIDDEN_ROOTS
        ):
            offenders.append(node.module)
    assert not offenders, (
        f"{path.relative_to(PACKAGE_ROOT)} imports {offenders}. The value-semantics library is the "
        "deterministic half of the architecture (§3.4); a network or model dependency here "
        "silently converts a lookup table into a guess."
    )


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_forbidden_calls(path: Path) -> None:
    """The import scan alone is not enough, and this test was missing.

    `FORBIDDEN_CALLS` and `_dotted_name` were added by the R0 determinism audit and then never
    wired to an assertion -- the audit agent hit its session limit mid-run. So the module listed
    `__import__`, `eval`, `os.popen` and `ctypes.CDLL` as forbidden while nothing checked for any
    of them, and the whole dynamic-dispatch half of the boundary was unenforced.

    That is the same defect as R0 finding 4, where `CaseResult.accusatory` was the one instrument
    built to catch false accusations and fired zero times across 624 cases. A guard nobody runs
    reads exactly like a guard that passes.

    `__import__("socket")` defeats an AST import scan completely: there is no `ast.Import` node to
    find. So does `getattr(__import__("o" + "s"), "popen")`. This closes that.
    """
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name in FORBIDDEN_CALLS:
                offenders.append(f"{name}() at line {node.lineno}")
    assert not offenders, (
        f"{path.relative_to(PACKAGE_ROOT)} calls {offenders}. These reach a network, a shell or "
        "arbitrary code without an import statement the AST scan can see, which is precisely why "
        "they are listed separately."
    )


def test_the_call_scan_actually_catches_something() -> None:
    """Negative control for the test above -- ground rule 7.

    A scan whose pattern never matches anything is indistinguishable from a scan that passes.
    This feeds it source that IS forbidden and requires it to object, so the guard is known to
    have teeth rather than assumed to.
    """
    hostile = textwrap.dedent(
        """
        def sneaky():
            mod = __import__('socket')
            os.popen('curl example.com')
            ctypes.CDLL('libc.so.6')
            return mod
        """
    )
    tree = ast.parse(hostile)
    found = {
        _dotted_name(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _dotted_name(node.func) in FORBIDDEN_CALLS
    }
    assert found == {"__import__", "os.popen", "ctypes.CDLL"}


def test_the_import_scan_sees_lazy_imports_inside_functions() -> None:
    """The open question the interrupted audit left: can a lazy import defeat the boundary?

    Answer, established here rather than assumed: no. `ast.walk` is a full recursive traversal,
    so an `import socket` nested inside a function body, a class body, a conditional or a `try`
    is an `ast.Import` node like any other and the scan reaches it.

    Worth pinning, because the obvious way to "optimise" that scan -- iterating `tree.body`
    instead of walking it -- would look tidier and would silently only check module-level
    imports, which is exactly where a hostile import would not be.
    """
    hostile = textwrap.dedent(
        """
        def lazy():
            import socket
            return socket

        class C:
            if True:
                try:
                    from requests import get
                except ImportError:
                    get = None
        """
    )
    tree = ast.parse(hostile)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_ROOTS
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and node.module.split(".")[0] in FORBIDDEN_ROOTS
        ):
            offenders.append(node.module)
    assert sorted(offenders) == ["requests", "socket"], (
        "a lazy import nested in a function, class, conditional or try-block must still be seen"
    )


def test_full_api_runs_with_the_network_severed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt and braces: no import can reach a socket if creating one raises."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("errata-valuesem attempted a network connection")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)

    samples = [
        ("M8", None),
        ("3/8-16 UNC", None),
        ("63 A", None),
        ("10 +/- 0.2 mm", None),
        ("0.5 in", None),
        ("-25 .. 70 degC", None),
        ("230/400 V", None),
        ("IP67", None),
        ("316 SS", Kind.MATERIAL),
        ("Box of 10", Kind.PACKAGING),
        ("Threaded", None),
        ("total nonsense here", None),
    ]
    for text, expect in samples:
        result = normalize(text, expect=expect)
        assert result is not None

    assert compare(normalize("316 SS"), normalize("1.4401")).is_equivalent


def test_normalization_is_reproducible() -> None:
    """NFR-1: identical inputs and identical versions produce identical output."""
    first = normalize("10 +/- 0.2 mm")
    second = normalize("10 +/- 0.2 mm")
    assert first == second
    assert first.grammar_version == second.grammar_version
