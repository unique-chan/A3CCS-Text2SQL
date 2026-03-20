#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gen_text2sql_diagrams.py

Purpose
-------
Generate two artifacts specialized for text2sql_langgraph.py-like files:
1) workflow diagram (Mermaid)
2) state field map (Markdown)

Target assumptions
------------------
- LangGraph state machine is declared via:
    g.add_node(...)
    g.add_edge(...)
    g.add_conditional_edges(...)
- State is a TypedDict named AgentState
- Route functions are named route_after_*
- Node functions are typically named node_*

Dependencies
------------
- Python standard library only
- No pip install required

Usage
-----
python gen_text2sql_diagrams.py text2sql_langgraph.py

Outputs
-------
- workflow.mmd
- state_field_map.md
- routes_debug.md
- nodes_debug.md
"""

from __future__ import annotations

import ast
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ----------------------------
# Data models
# ----------------------------

@dataclass
class RouteInfo:
    name: str
    source_text: str
    conditions: Dict[str, str] = field(default_factory=dict)   # dest -> readable label
    fallback: Dict[str, str] = field(default_factory=dict)     # dest -> readable label


@dataclass
class NodeUsage:
    node_func_name: str
    graph_node_name: str
    reads: Set[str] = field(default_factory=set)
    writes: Set[str] = field(default_factory=set)


@dataclass
class GraphData:
    agent_state_fields: List[str] = field(default_factory=list)
    graph_var_name: Optional[str] = None
    node_name_to_func: Dict[str, str] = field(default_factory=dict)   # graph node name -> python func name
    simple_edges: List[Tuple[str, str]] = field(default_factory=list)
    conditional_edges: List[Tuple[str, str, Dict[str, str]]] = field(default_factory=list)
    route_infos: Dict[str, RouteInfo] = field(default_factory=dict)
    node_usages: Dict[str, NodeUsage] = field(default_factory=dict)    # graph node name -> NodeUsage


# ----------------------------
# Helpers
# ----------------------------

START_NAMES = {"START"}
END_NAMES = {"END"}

SPECIAL_MERMAID_ESCAPES = {
    '"': '\\"',
}


def q(s: str) -> str:
    for k, v in SPECIAL_MERMAID_ESCAPES.items():
        s = s.replace(k, v)
    return s


def is_state_get_call(node: ast.AST) -> bool:
    # state.get("field")
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "state"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


def get_state_get_key(node: ast.Call) -> Optional[str]:
    if is_state_get_call(node):
        return str(node.args[0].value)
    return None


def is_state_subscript(node: ast.AST) -> bool:
    # state["field"]
    if not isinstance(node, ast.Subscript):
        return False
    if not isinstance(node.value, ast.Name) or node.value.id != "state":
        return False
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return True
    return False


def get_state_subscript_key(node: ast.Subscript) -> Optional[str]:
    if is_state_subscript(node):
        return str(node.slice.value)
    return None


def literal_string(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return repr(node)


def extract_string_list(node: ast.AST) -> List[str]:
    out: List[str] = []
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            s = literal_string(elt)
            if s is not None:
                out.append(s)
    return out


def extract_return_dest(node: ast.Return) -> Optional[str]:
    if node.value is None:
        return None
    if isinstance(node.value, ast.Constant):
        return str(node.value.value)
    if isinstance(node.value, ast.Name):
        return node.value.id
    return None


def get_func_source_segment(source: str, fn: ast.FunctionDef) -> str:
    seg = ast.get_source_segment(source, fn)
    if seg is None:
        return f"def {fn.name}(...):\n    <source unavailable>"
    return seg


def safe_id(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    if not out:
        return "node"
    s = "".join(out)
    if s[0].isdigit():
        s = "_" + s
    return s


def is_end_name(x: str) -> bool:
    return x in END_NAMES


def is_start_name(x: str) -> bool:
    return x in START_NAMES


# ----------------------------
# AgentState extraction
# ----------------------------

class AgentStateExtractor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.fields: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name != "AgentState":
            return

        # Expect TypedDict style:
        # class AgentState(TypedDict):
        #     field: type
        fields: List[str] = []
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields.append(stmt.target.id)

        self.fields = fields


# ----------------------------
# Route parsing
# ----------------------------

class ConditionToText:
    """
    Best-effort conversion from route_after_* condition AST to a readable label.

    This is intentionally heuristic and specialized for code like:
      if state.get("error") and "Step limit exceeded" in state["error"]:
      if state.get("error"):
      if state["attempts"] >= cfg.max_repair_attempts:
      if cfg.enable_semantic_check:
      if state.get("semantic_error"):
    """

    @staticmethod
    def expr(node: ast.AST) -> str:
        if isinstance(node, ast.BoolOp):
            op = " and " if isinstance(node.op, ast.And) else " or "
            return op.join(ConditionToText.expr(v) for v in node.values)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"not ({ConditionToText.expr(node.operand)})"

        if isinstance(node, ast.Call):
            key = get_state_get_key(node)
            if key is not None:
                return f'{key} exists'
            try:
                return ast.unparse(node)
            except Exception:
                return "call(...)"

        if isinstance(node, ast.Subscript):
            key = get_state_subscript_key(node)
            if key is not None:
                return key
            try:
                return ast.unparse(node)
            except Exception:
                return "subscript"

        if isinstance(node, ast.Compare):
            return ConditionToText.compare(node)

        if isinstance(node, ast.Attribute):
            try:
                return ast.unparse(node)
            except Exception:
                return f"{getattr(node.value, 'id', 'obj')}.{node.attr}"

        if isinstance(node, ast.Constant):
            return repr(node.value)

        if isinstance(node, ast.Name):
            return node.id

        try:
            return ast.unparse(node)
        except Exception:
            return ast.dump(node, annotate_fields=False)

    @staticmethod
    def compare(node: ast.Compare) -> str:
        left = ConditionToText.expr(node.left)
        parts: List[str] = []
        cur_left = left
        for op, comp in zip(node.ops, node.comparators):
            right = ConditionToText.expr(comp)
            parts.append(f"{cur_left} {ConditionToText.op(op)} {right}")
            cur_left = right
        return " and ".join(parts)

    @staticmethod
    def op(op: ast.AST) -> str:
        mapping = {
            ast.Eq: "==",
            ast.NotEq: "!=",
            ast.Gt: ">",
            ast.GtE: ">=",
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.In: "in",
            ast.NotIn: "not in",
            ast.Is: "is",
            ast.IsNot: "is not",
        }
        for k, v in mapping.items():
            if isinstance(op, k):
                return v
        return type(op).__name__

    @staticmethod
    def pretty(raw: str) -> str:
        # Tighten common patterns into concise labels.
        replacements = [
            ('error exists and \'Step limit exceeded\' in error', 'step limit exceeded'),
            ('error exists and "Step limit exceeded" in error', 'step limit exceeded'),
            ('error exists', 'error'),
            ('semantic_error exists', 'semantic_error'),
            ('cfg.enable_semantic_check', 'semantic check enabled'),
            ('attempts >= cfg.max_repair_attempts', 'attempts >= max_repair_attempts'),
        ]
        s = raw
        for a, b in replacements:
            s = s.replace(a, b)
        return s


class RouteAnalyzer:
    def __init__(self, source: str):
        self.source = source

    def analyze(self, fn: ast.FunctionDef) -> RouteInfo:
        info = RouteInfo(
            name=fn.name,
            source_text=get_func_source_segment(self.source, fn),
        )

        # Specialized route parser:
        # We inspect top-level if/return structure and derive labels.
        #
        # Strategy:
        # - For each top-level If:
        #     * collect direct returns in its body / nested ifs
        # - For final return:
        #     * fallback
        #
        # Output:
        #   dest -> label
        #
        # For nested structures, body labels accumulate parent conditions.

        def walk_stmts(stmts: List[ast.stmt], active_cond: Optional[str]) -> None:
            for stmt in stmts:
                if isinstance(stmt, ast.If):
                    cond_raw = ConditionToText.expr(stmt.test)
                    cond_txt = ConditionToText.pretty(cond_raw)
                    merged = cond_txt if not active_cond else f"{active_cond} and {cond_txt}"
                    walk_stmts(stmt.body, merged)

                    # else branch becomes "not cond" if it contains direct returns
                    if stmt.orelse:
                        neg = f"not ({cond_txt})"
                        merged_else = neg if not active_cond else f"{active_cond} and {neg}"
                        walk_stmts(stmt.orelse, merged_else)

                elif isinstance(stmt, ast.Return):
                    dest = extract_return_dest(stmt)
                    if dest is None:
                        continue
                    label = active_cond if active_cond else "otherwise"
                    # Preserve first discovered label per dest unless we need to append.
                    if label == "otherwise":
                        info.fallback[dest] = label
                    else:
                        if dest in info.conditions:
                            if label not in info.conditions[dest]:
                                info.conditions[dest] += f" OR {label}"
                        else:
                            info.conditions[dest] = label

        walk_stmts(fn.body, None)

        # Cleanup: if a destination appears in conditions and fallback, keep both logically,
        # but Mermaid will show each as separate edge label.
        return info


# ----------------------------
# Node read/write analysis
# ----------------------------

class StateFieldUsageExtractor(ast.NodeVisitor):
    def __init__(self, candidate_fields: Set[str]) -> None:
        self.candidate_fields = candidate_fields
        self.reads: Set[str] = set()
        self.writes: Set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        key = get_state_get_key(node)
        if key is not None and key in self.candidate_fields:
            self.reads.add(key)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = get_state_subscript_key(node)
        if key is not None and key in self.candidate_fields:
            self.reads.add(key)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        # Track keys written in returned dicts:
        # return {"sql": ..., "error": ...}
        if isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    key = k.value
                    if key in self.candidate_fields:
                        self.writes.add(key)
        self.generic_visit(node)


# ----------------------------
# Graph extraction
# ----------------------------

class GraphExtractor(ast.NodeVisitor):
    def __init__(self, source: str, state_fields: List[str]) -> None:
        self.source = source
        self.state_fields = set(state_fields)

        self.graph_data = GraphData(agent_state_fields=state_fields)

        self.function_defs: Dict[str, ast.FunctionDef] = {}
        self.route_defs: Dict[str, ast.FunctionDef] = {}
        self.node_defs: Dict[str, ast.FunctionDef] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_defs[node.name] = node
        if node.name.startswith("route_after_"):
            self.route_defs[node.name] = node
        if node.name.startswith("node_"):
            self.node_defs[node.name] = node
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # g = StateGraph(AgentState)
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name) and node.value.func.id == "StateGraph":
                if node.targets and isinstance(node.targets[0], ast.Name):
                    self.graph_data.graph_var_name = node.targets[0].id
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            self.generic_visit(node)
            return

        graph_var = self.graph_data.graph_var_name
        if graph_var is None:
            self.generic_visit(node)
            return

        if not isinstance(node.func.value, ast.Name) or node.func.value.id != graph_var:
            self.generic_visit(node)
            return

        method = node.func.attr

        if method == "add_node":
            self._extract_add_node(node)
        elif method == "add_edge":
            self._extract_add_edge(node)
        elif method == "add_conditional_edges":
            self._extract_add_conditional_edges(node)

        self.generic_visit(node)

    def _extract_add_node(self, node: ast.Call) -> None:
        if len(node.args) < 2:
            return
        graph_node_name = name_of(node.args[0])
        python_func_name = name_of(node.args[1])

        self.graph_data.node_name_to_func[graph_node_name] = python_func_name

    def _extract_add_edge(self, node: ast.Call) -> None:
        if len(node.args) < 2:
            return
        src = name_of(node.args[0])
        dst = name_of(node.args[1])
        self.graph_data.simple_edges.append((src, dst))

    def _extract_add_conditional_edges(self, node: ast.Call) -> None:
        if len(node.args) < 3:
            return
        src = name_of(node.args[0])
        route_fn = name_of(node.args[1])

        mapping: Dict[str, str] = {}
        if isinstance(node.args[2], ast.Dict):
            for k, v in zip(node.args[2].keys, node.args[2].values):
                mapping[name_of(k)] = name_of(v)

        self.graph_data.conditional_edges.append((src, route_fn, mapping))

    def finalize(self) -> GraphData:
        # Analyze routes
        route_analyzer = RouteAnalyzer(self.source)
        for _, route_fn, _ in self.graph_data.conditional_edges:
            fn = self.function_defs.get(route_fn)
            if fn is not None:
                self.graph_data.route_infos[route_fn] = route_analyzer.analyze(fn)

        # Analyze node read/write usage
        for graph_node_name, py_func_name in self.graph_data.node_name_to_func.items():
            fn = self.function_defs.get(py_func_name)
            if fn is None:
                continue
            usage_extractor = StateFieldUsageExtractor(self.state_fields)
            usage_extractor.visit(fn)
            self.graph_data.node_usages[graph_node_name] = NodeUsage(
                node_func_name=py_func_name,
                graph_node_name=graph_node_name,
                reads=usage_extractor.reads,
                writes=usage_extractor.writes,
            )

        return self.graph_data


# ----------------------------
# Rendering: workflow Mermaid
# ----------------------------

def route_mapping_to_labels(
    route_info: Optional[RouteInfo],
    mapping: Dict[str, str],
) -> List[Tuple[str, str]]:
    """
    Returns list of (dest, label).
    mapping is route_return_key -> graph_dest
    route_info.conditions / fallback are keyed by route return key
    """
    edges: List[Tuple[str, str]] = []

    if route_info is None:
        for route_key, graph_dest in mapping.items():
            edges.append((graph_dest, route_key))
        return edges

    # First, explicit conditions
    for route_key, graph_dest in mapping.items():
        if route_key in route_info.conditions:
            edges.append((graph_dest, route_info.conditions[route_key]))

    # Then fallback / otherwise
    for route_key, graph_dest in mapping.items():
        if route_key in route_info.fallback:
            edges.append((graph_dest, route_info.fallback[route_key]))

    # Any mapping entry still missing: use raw route key
    covered = {(d, l) for d, l in edges}
    used_dests = {d for d, _ in edges}
    for route_key, graph_dest in mapping.items():
        if graph_dest not in used_dests:
            edges.append((graph_dest, route_key))

    return edges


def render_mermaid_workflow(gd: GraphData) -> str:
    all_nodes: Set[str] = set()
    for name in gd.node_name_to_func.keys():
        all_nodes.add(name)
    for src, dst in gd.simple_edges:
        all_nodes.add(src)
        all_nodes.add(dst)
    for src, _, mapping in gd.conditional_edges:
        all_nodes.add(src)
        for dst in mapping.values():
            all_nodes.add(dst)

    lines: List[str] = []
    lines.append("flowchart TD")

    # Node declarations
    for n in sorted(all_nodes):
        nid = safe_id(n)
        if is_start_name(n):
            lines.append(f'    {nid}(["START"])')
        elif is_end_name(n):
            lines.append(f'    {nid}(["END"])')
        else:
            # Show graph node name, and optionally python node function as sublabel
            pyf = gd.node_name_to_func.get(n)
            if pyf and pyf != n:
                label = f"{n}\\n({pyf})"
            else:
                label = n
            lines.append(f'    {nid}["{q(label)}"]')

    lines.append("")

    # Simple edges
    for src, dst in gd.simple_edges:
        lines.append(f"    {safe_id(src)} --> {safe_id(dst)}")

    # Conditional edges with inferred labels
    for src, route_fn, mapping in gd.conditional_edges:
        route_info = gd.route_infos.get(route_fn)
        labeled_edges = route_mapping_to_labels(route_info, mapping)

        # Deduplicate while preserving order
        seen: Set[Tuple[str, str]] = set()
        for dst, label in labeled_edges:
            key = (dst, label)
            if key in seen:
                continue
            seen.add(key)
            label_one_line = " ".join(label.split())
            lines.append(
                f'    {safe_id(src)} -->|"{q(label_one_line)}"| {safe_id(dst)}'
            )

    return "\n".join(lines) + "\n"


# ----------------------------
# Rendering: state field map
# ----------------------------

def render_state_field_map(gd: GraphData) -> str:
    lines: List[str] = []
    lines.append("# State Field Map")
    lines.append("")
    lines.append("## AgentState fields")
    lines.append("")
    for f in gd.agent_state_fields:
        lines.append(f"- `{f}`")
    lines.append("")

    lines.append("## Node read/write map")
    lines.append("")
    lines.append("| Graph Node | Python Function | Reads | Writes |")
    lines.append("|---|---|---|---|")

    for graph_node_name in sorted(gd.node_name_to_func.keys()):
        usage = gd.node_usages.get(graph_node_name)
        pyf = gd.node_name_to_func.get(graph_node_name, "")
        if usage is None:
            reads = ""
            writes = ""
        else:
            reads = ", ".join(f"`{x}`" for x in sorted(usage.reads))
            writes = ", ".join(f"`{x}`" for x in sorted(usage.writes))
        lines.append(f"| `{graph_node_name}` | `{pyf}` | {reads} | {writes} |")

    lines.append("")
    lines.append("## Interpretation notes")
    lines.append("")
    lines.append("- `Reads`는 함수 본문에서 `state.get(...)` 또는 `state[...]`로 접근한 필드를 정적 분석한 결과입니다.")
    lines.append("- `Writes`는 함수의 `return { ... }` 딕셔너리 key를 기준으로 잡은 결과입니다.")
    lines.append("- 즉, 동적 업데이트나 간접 접근은 누락될 수 있습니다.")
    lines.append("")

    return "\n".join(lines) + "\n"


# ----------------------------
# Debug renderers
# ----------------------------

def render_routes_debug(gd: GraphData) -> str:
    lines: List[str] = []
    lines.append("# Route function analysis")
    lines.append("")
    for route_name in sorted(gd.route_infos.keys()):
        info = gd.route_infos[route_name]
        lines.append(f"## `{route_name}`")
        lines.append("")
        lines.append("### Inferred labels by destination")
        lines.append("")
        if not info.conditions and not info.fallback:
            lines.append("_No conditions inferred._")
        else:
            for dest, label in info.conditions.items():
                lines.append(f"- `{dest}` <= {label}")
            for dest, label in info.fallback.items():
                lines.append(f"- `{dest}` <= {label}")
        lines.append("")
        lines.append("### Source")
        lines.append("")
        lines.append("```python")
        lines.append(info.source_text.rstrip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_nodes_debug(gd: GraphData) -> str:
    lines: List[str] = []
    lines.append("# Node usage analysis")
    lines.append("")
    for graph_node_name in sorted(gd.node_name_to_func.keys()):
        pyf = gd.node_name_to_func[graph_node_name]
        usage = gd.node_usages.get(graph_node_name)
        lines.append(f"## `{graph_node_name}` / `{pyf}`")
        lines.append("")
        if usage is None:
            lines.append("_No analysis available._")
            lines.append("")
            continue
        lines.append(f"- Reads: {', '.join(sorted(usage.reads)) or '(none)'}")
        lines.append(f"- Writes: {', '.join(sorted(usage.writes)) or '(none)'}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python gen_text2sql_diagrams.py <path/to/text2sql_langgraph.py>",
            file=sys.stderr,
        )
        return 2

    src_path = Path(sys.argv[1])
    if not src_path.exists():
        print(f"File not found: {src_path}", file=sys.stderr)
        return 1

    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(src_path))

    # 1) Extract AgentState
    state_extractor = AgentStateExtractor()
    state_extractor.visit(tree)
    state_fields = state_extractor.fields
    if not state_fields:
        print(
            "Warning: AgentState fields were not found. "
            "State field map may be empty.",
            file=sys.stderr,
        )

    # 2) Extract graph / routes / node usage
    gx = GraphExtractor(source=source, state_fields=state_fields)
    gx.visit(tree)
    gd = gx.finalize()

    # 3) Render outputs
    workflow = render_mermaid_workflow(gd)
    state_map = render_state_field_map(gd)
    routes_dbg = render_routes_debug(gd)
    nodes_dbg = render_nodes_debug(gd)

    out_dir = src_path.parent
    (out_dir / "workflow.mmd").write_text(workflow, encoding="utf-8")
    (out_dir / "state_field_map.md").write_text(state_map, encoding="utf-8")
    (out_dir / "routes_debug.md").write_text(routes_dbg, encoding="utf-8")
    (out_dir / "nodes_debug.md").write_text(nodes_dbg, encoding="utf-8")

    print("Generated:")
    print(f"  - {out_dir / 'workflow.mmd'}")
    print(f"  - {out_dir / 'state_field_map.md'}")
    print(f"  - {out_dir / 'routes_debug.md'}")
    print(f"  - {out_dir / 'nodes_debug.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())