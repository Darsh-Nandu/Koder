"""
kg_maker_agent.py

KG Maker Agent
==============

Scans a codebase, builds a detailed "Knowledge Graph" (KG.json) describing:
  - every source file (path, language, size, last_modified hash)
  - what each file imports (resolved to other files in the codebase
    where possible, plus external/3rd-party packages)
  - what each file is imported BY (reverse-dependency / "imported_by")
  - top-level symbols defined in each file (functions/classes, best-effort)

Runs as a background workflow:
  - on start, does a FULL scan and writes KG.json
  - then watches the workspace for file create/modify/delete/move events
    and incrementally updates KG.json (re-parsing only the changed file,
    and recomputing reverse "imported_by" edges that touch it)

Supported languages (import parsing):
  - Python (.py)            -> `import x`, `from x import y`, relative imports
  - JavaScript/TypeScript    -> `import ... from '...'`, `require('...')`,
    (.js, .jsx, .ts, .tsx)      `export ... from '...'`

Any other file types are still listed as nodes (for completeness) but
without import edges.

Usage
-----
CLI (background watcher):
    python kg_maker_agent.py /path/to/workspace [--out KG.json] [--once]

As a library / LangGraph tool:
    from kg_maker_agent import build_kg, start_kg_watcher

    kg = build_kg("/path/to/workspace")          # one-shot full build
    observer = start_kg_watcher("/path/to/workspace", "KG.json")  # background

Dependencies:
    pip install watchdog --break-system-packages
"""

import os
import re
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:  # watchdog optional unless using the watcher
    Observer = None
    FileSystemEventHandler = object



# Config

IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache",
    "site-packages", ".idea", ".vscode", "coverage",
}

CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

OTHER_TRACKED_EXTENSIONS = {
    ".json", ".md", ".yaml", ".yml", ".toml", ".html", ".css",
}

DEBOUNCE_SECONDS = 0.75


# Helpers: file discovery

def _should_ignore_dir(dirname: str) -> bool:
    return dirname in IGNORED_DIRS or dirname.startswith(".")


def _iter_source_files(root: str):
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_ignore_dir(d)]
        for fname in filenames:
            ext = os.path.splitext(fname)[1]
            if ext in CODE_EXTENSIONS or ext in OTHER_TRACKED_EXTENSIONS:
                yield os.path.join(dirpath, fname)


def _rel(root: str, path: str) -> str:
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace("\\", "/")


def _file_hash(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except (OSError, IOError):
        return None


# Import parsers

PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+(?:\s*,\s*[.\w]+)*))",
    re.MULTILINE,
)

PY_TOPLEVEL_DEF_RE = re.compile(r"^(?:async\s+def|def|class)\s+(\w+)", re.MULTILINE)

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|export\s+[\w*{}\s,]*from\s+|require\s*\(\s*)
        ['"]([^'"]+)['"]""",
    re.VERBOSE,
)

JS_TOPLEVEL_DEF_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+(\w+)"
    r"|^(?:export\s+)?const\s+(\w+)\s*=\s*(?:\(|async\s*\(|function)",
    re.MULTILINE,
)


def _parse_python_imports(content: str) -> List[Dict[str, Any]]:
    imports = []
    for match in PY_IMPORT_RE.finditer(content):
        from_module, plain_modules = match.groups()
        if from_module:
            imports.append({"module": from_module, "kind": "from"})
        elif plain_modules:
            for mod in plain_modules.split(","):
                mod = mod.strip()
                if mod:
                    imports.append({"module": mod, "kind": "import"})
    return imports


def _parse_js_imports(content: str) -> List[Dict[str, Any]]:
    imports = []
    for match in JS_IMPORT_RE.finditer(content):
        spec = match.group(1)
        kind = "require" if "require(" in match.group(0) else "import"
        imports.append({"module": spec, "kind": kind})
    return imports


def _extract_symbols(content: str, language: str) -> List[str]:
    symbols: Set[str] = set()
    if language == "python":
        for m in PY_TOPLEVEL_DEF_RE.finditer(content):
            symbols.add(m.group(1))
    elif language in ("javascript", "typescript"):
        for m in JS_TOPLEVEL_DEF_RE.finditer(content):
            name = m.group(1) or m.group(2)
            if name:
                symbols.add(name)
    return sorted(symbols)


# Resolve imports -> file paths within the project (where possible)

def _resolve_python_import(root: str, file_rel: str, module: str, all_files: Set[str]) -> Optional[str]:
    """Best-effort resolve a Python module string to a project-relative file path."""
    file_dir = os.path.dirname(file_rel)

    # Relative imports: leading dots
    if module.startswith("."):
        leading_dots = len(module) - len(module.lstrip("."))
        remainder = module[leading_dots:]
        base_dir = file_dir
        for _ in range(leading_dots - 1):
            base_dir = os.path.dirname(base_dir)
        parts = remainder.split(".") if remainder else []
        candidate_base = os.path.join(base_dir, *parts) if parts else base_dir
        candidates = [
            candidate_base + ".py",
            os.path.join(candidate_base, "__init__.py"),
        ]
    else:
        parts = module.split(".")
        # Try as path from project root
        candidate_base = os.path.join(*parts)
        candidates = [
            candidate_base + ".py",
            os.path.join(candidate_base, "__init__.py"),
        ]
        # Also try relative to the importing file's directory
        candidate_base2 = os.path.join(file_dir, *parts)
        candidates += [
            candidate_base2 + ".py",
            os.path.join(candidate_base2, "__init__.py"),
        ]

    for cand in candidates:
        cand_norm = cand.replace("\\", "/").lstrip("./")
        if cand_norm in all_files:
            return cand_norm
    return None


def _resolve_js_import(root: str, file_rel: str, module: str, all_files: Set[str]) -> Optional[str]:
    """Best-effort resolve a JS/TS import specifier to a project-relative file path."""
    if not (module.startswith(".") or module.startswith("/")):
        return None  # bare specifier -> npm package, not a local file

    file_dir = os.path.dirname(file_rel)
    candidate_base = os.path.normpath(os.path.join(file_dir, module)).replace("\\", "/")

    possible_exts = ["", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
    possible_index = [
        "/index.js", "/index.jsx", "/index.ts", "/index.tsx",
    ]

    for ext in possible_exts:
        cand = (candidate_base + ext).lstrip("./")
        if cand in all_files:
            return cand

    for idx in possible_index:
        cand = (candidate_base + idx).lstrip("./")
        if cand in all_files:
            return cand

    return None


# Per-file analysis

def _analyze_file(root: str, abs_path: str) -> Dict[str, Any]:
    rel_path = _rel(root, abs_path)
    ext = os.path.splitext(abs_path)[1]
    language = CODE_EXTENSIONS.get(ext, ext.lstrip(".") or "unknown")

    node: Dict[str, Any] = {
        "path": rel_path,
        "language": language,
        "size_bytes": None,
        "hash": _file_hash(abs_path),
        "imports": [],          # raw import specs
        "imports_resolved": [], # project-relative paths (subset of imports)
        "imports_external": [], # 3rd-party / unresolved
        "imported_by": [],      # filled in during graph-level pass
        "symbols": [],
    }

    try:
        node["size_bytes"] = os.path.getsize(abs_path)
    except OSError:
        pass

    if ext not in CODE_EXTENSIONS:
        return node  # non-code tracked file (json/md/etc) -> node only

    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except (OSError, IOError):
        return node

    if language == "python":
        node["imports"] = _parse_python_imports(content)
    elif language in ("javascript", "typescript"):
        node["imports"] = _parse_js_imports(content)

    node["symbols"] = _extract_symbols(content, language)
    return node


# Full KG build

def build_kg(root: str) -> Dict[str, Any]:
    """
    Perform a full scan of `root` and return the KG dict.
    Does NOT write to disk -- use `save_kg` or `build_and_save_kg`.
    """
    root = os.path.abspath(root)
    all_abs_files = list(_iter_source_files(root))
    all_rel_files: Set[str] = {_rel(root, p) for p in all_abs_files}

    files: Dict[str, Any] = {}
    for abs_path in all_abs_files:
        node = _analyze_file(root, abs_path)
        files[node["path"]] = node

    # Resolve imports -> local files or external, and build reverse edges
    for rel_path, node in files.items():
        ext = os.path.splitext(rel_path)[1]
        language = node["language"]
        resolved: List[str] = []
        external: List[str] = []

        for imp in node["imports"]:
            module = imp["module"]
            target: Optional[str] = None

            if language == "python":
                target = _resolve_python_import(root, rel_path, module, all_rel_files)
            elif language in ("javascript", "typescript"):
                target = _resolve_js_import(root, rel_path, module, all_rel_files)

            if target:
                resolved.append(target)
            else:
                external.append(module)

        node["imports_resolved"] = sorted(set(resolved))
        node["imports_external"] = sorted(set(external))

    # Reverse edges: imported_by
    for rel_path, node in files.items():
        for target in node["imports_resolved"]:
            target_node = files.get(target)
            if target_node is not None and rel_path not in target_node["imported_by"]:
                target_node["imported_by"].append(rel_path)

    for node in files.values():
        node["imported_by"] = sorted(node["imported_by"])

    kg = {
        "root": root,
        "generated_at": time.time(),
        "file_count": len(files),
        "files": files,
    }
    return kg


def save_kg(kg: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(kg, f, indent=2, sort_keys=True)


def build_and_save_kg(root: str, out_path: str = "KG.json") -> Dict[str, Any]:
    kg = build_kg(root)
    save_kg(kg, out_path)
    return kg


# Incremental update for a single file (used by the watcher)

def _full_rebuild_needed_for_reverse_edges() -> bool:
    # Reverse edges depend on every file, so for correctness on
    # add/delete/rename we recompute them across the whole graph.
    # This is still cheap for typical project sizes.
    return True


def update_kg_for_path(kg: Dict[str, Any], root: str, abs_path: str, deleted: bool = False) -> Dict[str, Any]:
    """
    Update `kg` in place for a single changed/added/deleted file, then
    recompute reverse "imported_by" edges across the graph.
    Returns the updated kg.
    """
    root = os.path.abspath(root)
    rel_path = _rel(root, abs_path)
    files = kg.setdefault("files", {})

    if deleted or not os.path.exists(abs_path):
        files.pop(rel_path, None)
    else:
        ext = os.path.splitext(abs_path)[1]
        if ext in CODE_EXTENSIONS or ext in OTHER_TRACKED_EXTENSIONS:
            files[rel_path] = _analyze_file(root, abs_path)

    all_rel_files: Set[str] = set(files.keys())

    # Re-resolve imports for the changed file (others' resolutions to/from
    # this file may now be valid/invalid too, so re-resolve everything --
    # cheap relative to a full re-parse, since content isn't re-read).
    for rp, node in files.items():
        ext = os.path.splitext(rp)[1]
        language = node.get("language")
        resolved: List[str] = []
        external: List[str] = []
        for imp in node.get("imports", []):
            module = imp["module"]
            target: Optional[str] = None
            if language == "python":
                target = _resolve_python_import(root, rp, module, all_rel_files)
            elif language in ("javascript", "typescript"):
                target = _resolve_js_import(root, rp, module, all_rel_files)
            if target:
                resolved.append(target)
            else:
                external.append(module)
        node["imports_resolved"] = sorted(set(resolved))
        node["imports_external"] = sorted(set(external))
        node["imported_by"] = []

    for rp, node in files.items():
        for target in node["imports_resolved"]:
            target_node = files.get(target)
            if target_node is not None and rp not in target_node["imported_by"]:
                target_node["imported_by"].append(rp)

    for node in files.values():
        node["imported_by"] = sorted(node["imported_by"])

    kg["file_count"] = len(files)
    kg["generated_at"] = time.time()
    return kg


# Background watcher

class _KGEventHandler(FileSystemEventHandler):
    def __init__(self, root: str, out_path: str, kg: Dict[str, Any]):
        self.root = root
        self.out_path = out_path
        self.kg = kg
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._pending: Set[str] = set()

    def _is_tracked(self, path: str) -> bool:
        ext = os.path.splitext(path)[1]
        if ext not in CODE_EXTENSIONS and ext not in OTHER_TRACKED_EXTENSIONS:
            return False
        for part in Path(path).parts:
            if _should_ignore_dir(part):
                return False
        return True

    def _schedule(self, path: str):
        if not self._is_tracked(path):
            return
        with self._lock:
            self._pending.add(path)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self):
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()

        for abs_path in pending:
            update_kg_for_path(self.kg, self.root, abs_path)

        save_kg(self.kg, self.out_path)
        print(f"[kg_maker_agent] KG updated ({self.kg['file_count']} files) -> {self.out_path}")

    # watchdog event hooks
    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            with self._lock:
                self._pending.add(event.src_path)
            update_kg_for_path(self.kg, self.root, event.src_path, deleted=True)
            save_kg(self.kg, self.out_path)
            print(f"[kg_maker_agent] KG updated (file removed) -> {self.out_path}")

    def on_moved(self, event):
        if not event.is_directory:
            update_kg_for_path(self.kg, self.root, event.src_path, deleted=True)
            self._schedule(event.dest_path)


def start_kg_watcher(root: str, out_path: str = "KG.json") -> "Observer":
    """
    Build an initial KG, write it to `out_path`, then start a background
    watchdog Observer that keeps it updated. Returns the Observer so the
    caller can `.stop()` it later (e.g. on app shutdown).
    """
    if Observer is None:
        raise RuntimeError(
            "watchdog is not installed. Run: pip install watchdog --break-system-packages"
        )

    root = os.path.abspath(root)
    kg = build_and_save_kg(root, out_path)
    print(f"[kg_maker_agent] Initial KG built ({kg['file_count']} files) -> {out_path}")

    handler = _KGEventHandler(root, out_path, kg)
    observer = Observer()
    observer.schedule(handler, root, recursive=True)
    observer.start()
    print(f"[kg_maker_agent] Watching {root} for changes...")
    return observer


# CLI

def _main():
    import argparse

    parser = argparse.ArgumentParser(description="KG Maker Agent")
    parser.add_argument("path", nargs="?", default=".", help="Workspace root to scan/watch")
    parser.add_argument("--out", default="KG.json", help="Output KG json path")
    parser.add_argument("--once", action="store_true", help="Build KG once and exit (no watcher)")
    args = parser.parse_args()

    if args.once:
        kg = build_and_save_kg(args.path, args.out)
        print(f"[kg_maker_agent] KG built ({kg['file_count']} files) -> {args.out}")
        return

    observer = start_kg_watcher(args.path, args.out)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        print("\n[kg_maker_agent] Stopped.")


if __name__ == "__main__":
    _main()