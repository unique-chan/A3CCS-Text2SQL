from __future__ import annotations

import os
import re
import csv
import json
import math
import sqlite3
import requests
import time

from dataclasses import dataclass
from datetime import datetime
from operator import add
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Tuple
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
import sqlglot
from sqlglot import exp
from langgraph.graph import StateGraph, START, END


# =========================
# Utils: env parsing / text loading
# =========================
def env_str(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default


def env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    try:
        return int(v) if v is not None and v != "" else default
    except ValueError:
        return default


def env_float(key: str, default: float) -> float:
    v = os.getenv(key)
    try:
        return float(v) if v is not None and v != "" else default
    except ValueError:
        return default


def env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_required_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Required text file not found: {path}")
    return p.read_text(encoding="utf-8").strip()


def load_optional_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


# =========================
# DB helpers
# =========================
def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.create_function("sqrt", 1, math.sqrt)
    conn.create_function("pow", 2, math.pow)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_sqlite(db_path: str) -> str:
    conn = _connect_sqlite(db_path)
    try:
        cur = conn.cursor()
        tables = cur.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

        lines: List[str] = []
        for t in tables:
            name = t["name"]
            create_sql = t["sql"] or ""
            cols = cur.execute(f"PRAGMA table_info({name})").fetchall()
            col_desc = ", ".join(
                [f'{c["name"]} {c["type"]}' + (" PK" if c["pk"] else "") for c in cols]
            )
            lines.append(f"TABLE {name} ({col_desc})")
            lines.append(f"CREATE_SQL: {create_sql}")
            lines.append("")
        return "\n".join(lines).strip()
    finally:
        conn.close()


def get_schema_sqlite_cached(db_path: str, resources: "RuntimeResources") -> str:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    db_mtime = db_file.stat().st_mtime
    if resources.cached_schema and resources.cached_schema_mtime == db_mtime:
        return resources.cached_schema

    schema = get_schema_sqlite(str(db_file))
    resources.cached_schema = schema
    resources.cached_schema_mtime = db_mtime
    return schema


def parse_bool_text(value: str) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def split_sql_statements(sql: str) -> List[str]:
    parts = [x.strip() for x in sqlglot.parse(sql, read="sqlite")]
    return [str(x).strip() for x in parts if str(x).strip()]


def validate_view_registration_sql(sql: str) -> Tuple[bool, str]:
    try:
        parsed = sqlglot.parse(sql, read="sqlite")
    except Exception as e:
        return False, f"SQL parse error: {e}"

    if len(parsed) != 1:
        return False, "Only one CREATE VIEW statement is allowed per row."

    stmt = parsed[0]
    if not isinstance(stmt, exp.Create):
        return False, f"Only CREATE VIEW is allowed. Got: {type(stmt).__name__}"

    kind = str(stmt.args.get("kind") or "").upper()
    if kind != "VIEW":
        return False, f"Only CREATE VIEW is allowed. Got CREATE {kind or '(unknown)'}"

    return True, ""


def register_views_from_catalog_csv(db_path: str, csv_path: str) -> str:
    csv_file = Path(csv_path)
    if not csv_file.exists():
        return f"View registration skipped: catalog CSV not found ({csv_path})"

    with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        required = {"view_name", "create_sql"}
        missing = sorted(required - set(fieldnames))
        if missing:
            raise ValueError(
                f"View catalog CSV is missing required columns: {', '.join(missing)}"
            )

        rows = list(reader)

    applied: List[str] = []
    skipped: List[str] = []

    conn = _connect_sqlite(db_path)
    try:
        cur = conn.cursor()

        # CSV 데이터 행 순서 그대로 등록
        # data_row_idx=1 이 CSV 첫 번째 데이터 행
        for data_row_idx, row in enumerate(rows, start=1):
            csv_line_no = data_row_idx + 1  # 헤더 포함 실제 줄 번호 느낌으로 쓰기 위함

            view_name = (row.get("view_name") or "").strip()
            create_sql = (row.get("create_sql") or "").strip()
            enabled_raw = (row.get("enabled") or "1").strip()
            drop_if_exists = parse_bool_text((row.get("drop_if_exists") or "1").strip())

            if not view_name and not create_sql:
                continue
            if not view_name:
                raise ValueError(f"CSV line {csv_line_no}: view_name is empty.")
            if not create_sql:
                raise ValueError(
                    f"CSV line {csv_line_no}: create_sql is empty for view '{view_name}'."
                )

            if enabled_raw and not parse_bool_text(enabled_raw):
                skipped.append(f"{view_name} (disabled)")
                continue

            ok, reason = validate_view_registration_sql(create_sql)
            if not ok:
                raise ValueError(f"CSV line {csv_line_no} ({view_name}): {reason}")

            if drop_if_exists:
                cur.execute(f'DROP VIEW IF EXISTS "{view_name}"')

            cur.execute(create_sql)
            applied.append(view_name)

        conn.commit()
    finally:
        conn.close()

    if applied:
        return f"View registration completed! registered={len(applied)}"
    if skipped:
        return f"View registration completed! registered=0 skipped={len(skipped)}"
    return "View registration completed! registered=0"


def normalize_sql(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"^\s*(--.*\n|/\*.*?\*/\s*)*", "", s, flags=re.S)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r";+$", "", s)
    return s.strip()


def validate_safe_sql(sql: str, db_language: str = "sqlite") -> Tuple[bool, str]:
    sql = normalize_sql(sql)
    try:
        parsed = sqlglot.parse(sql, read=db_language)
    except Exception as e:
        return False, f"SQL parse error: {e}"

    if len(parsed) != 1:
        return False, "Multiple SQL statements are not allowed."

    stmt = parsed[0]
    allowed = (
        exp.Select,
        exp.Union,
        exp.Except,
        exp.Intersect,
    )
    if not isinstance(stmt, allowed):
        return False, f"Only read-only query expressions are allowed. Got: {type(stmt).__name__}"

    dangerous_nodes = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
        exp.Transaction,
        exp.Merge,
    )
    for node in stmt.walk():
        if isinstance(node, dangerous_nodes):
            return False, f"Dangerous SQL node detected: {type(node).__name__}"

    return True, ""


def is_safe_sql(sql: str, db_language: str = "sqlite") -> bool:
    ok, _ = validate_safe_sql(sql, db_language=db_language)
    return ok


def run_and_save_sqlite(
    db_path: str,
    sql: str,
    csv_path: Path,
    max_rows: int = 50,
    save_csv: bool = True,
) -> str:
    conn = _connect_sqlite(db_path)
    try:
        cur = conn.cursor()
        cur.execute(sql)

        if cur.description is not None:
            cols = [d[0] for d in cur.description]
            terminal_rows = []

            count = 0
            if save_csv:
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(cols)

                    while True:
                        batch = cur.fetchmany(1000)
                        if not batch:
                            break
                        writer.writerows(batch)
                        for row in batch:
                            if count < max_rows:
                                terminal_rows.append(row)
                            count += 1
            else:
                while True:
                    batch = cur.fetchmany(1000)
                    if not batch:
                        break
                    for row in batch:
                        if count < max_rows:
                            terminal_rows.append(row)
                        count += 1

            if not terminal_rows:
                return "(0 rows)"

            widths = [len(c) for c in cols]
            for r in terminal_rows:
                for i in range(len(cols)):
                    widths[i] = max(widths[i], len(str(r[i])))

            def fmt(vals):
                return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(vals))

            out = []
            out.append(fmt(cols))
            out.append("-+-".join("-" * w for w in widths))
            for r in terminal_rows:
                out.append(fmt(r))

            if count > max_rows:
                out.append(f"... (showing the first {max_rows} rows of {count} rows.)")

            return "\n".join(out)

        conn.commit()
        return "(ok)"
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


def extract_sql(text: str) -> str:
    m = re.search(r"```sql\s*(.*?)\s*```", text, flags=re.S | re.I)
    if m:
        return m.group(1).strip().rstrip(";") + ";"
    t = text.strip()
    t = re.sub(r"^```.*?\n|\n```$", "", t, flags=re.S)
    return t.rstrip(";") + ";"


def extract_json_block(text: str) -> str:
    raw = text.strip()
    m = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.S | re.I)
    if m:
        return m.group(1).strip()
    return raw


def parse_rewrite_intent_payload(text: str) -> Tuple[str, str]:
    raw = extract_json_block(text)
    data = json.loads(raw)

    rewrite_mode = str(data.get("rewrite_mode", "")).strip().lower()
    rewrite_guidance = str(data.get("rewrite_guidance", "")).strip()

    if rewrite_mode not in {"guided", "autonomous"}:
        raise ValueError(f"Invalid rewrite_mode: {rewrite_mode}")

    if rewrite_mode == "autonomous":
        rewrite_guidance = ""

    return rewrite_mode, rewrite_guidance


def parse_semantic_verdict_payload(text: str) -> Tuple[str, str]:
    raw = extract_json_block(text)
    data = json.loads(raw)
    verdict = str(data.get("verdict", "")).strip().upper()
    reason = str(data.get("reason", "")).strip()
    if verdict not in {"PASS", "FAIL"}:
        raise ValueError(f"Invalid verdict: {verdict}")
    return verdict, reason


def is_rewrite_request(text: str) -> bool:
    return text.strip().startswith("[재작성]") or text.strip().startswith("[Rewrite]")


def detect_result_quality_issue(question: str, sql: str, result: str) -> str:
    q = question.lower()
    s = sql.lower()
    r = result.lower()

    if r.startswith("error:"):
        return ""

    if "(0 rows)" in result and any(k in q for k in ["latest", "recent", "최신", "최근", "현재"]):
        return "The query returned 0 rows for a latest/current request. Re-check time anchoring or filtering."

    if any(k in q for k in ["count", "개수", "몇 개", "총 수", "합계", "total number"]) and "count(" not in s:
        return "The question appears to require counting or aggregation, but the SQL does not use COUNT()."

    if any(k in q for k in ["평균", "average", "avg"]) and "avg(" not in s:
        return "The question appears to require an average, but the SQL does not use AVG()."

    if any(k in q for k in ["최대", "가장 큰", "max", "top", "상위"]) and "max(" not in s and "order by" not in s:
        return "The question appears to require top/max logic, but the SQL lacks MAX() or ORDER BY ranking logic."

    return ""


# =========================
# State / config / resources
# =========================
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add]
    question: str
    schema: str
    schema_instruction: str
    sql: str
    result: str
    error: str
    semantic_error: str
    attempts: int
    steps: int
    seen_sql: List[str]
    csv_path: Path
    llm_generate_time: float
    llm_repair_time: float
    sql_execute_time: float
    semantic_check_time: float
    llm_semantic_repair_time: float

    rewrite_mode: str
    rewrite_request: str
    rewrite_guidance: str
    previous_question: str
    previous_sql: str
    previous_result: str
    reflection: str
    rewrite_attempts: int
    rewrite_reflection_time: float
    llm_rewrite_time: float
    rewrite_intent_time: float
    cheat_sheet_general: str


@dataclass
class Config:
    db_path: str
    schema_instruction_path: str

    llm_backend: str

    model: str
    temperature: float

    openai_api_key: str
    openai_base_url: str

    text2sql_prompt_path: str
    repair_prompt_path: str
    semantic_check_prompt_path: str
    semantic_repair_prompt_path: str
    rewrite_intent_prompt_path: str
    rewrite_reflect_prompt_path: str
    rewrite_sql_prompt_path: str
    sql_cheat_general_path: str
    view_catalog_path: str
    view_catalog_csv_path: str

    max_repair_attempts: int
    max_steps: int
    max_same_sql_repeats: int
    max_rows: int

    block_non_readonly_sql: bool
    enable_semantic_check: bool

    output_dir: str


@dataclass
class RuntimeResources:
    schema_instruction: str
    system_text2sql: str
    system_repair: str
    system_semantic_check: str
    system_semantic_repair: str
    system_rewrite_intent: str
    system_rewrite_reflect: str
    system_rewrite_sql: str
    cheat_sheet_general: str
    view_catalog: str
    view_registration_summary: str = ""
    cached_schema: str = ""
    cached_schema_mtime: float = -1.0


@dataclass
class Text2SQLRuntime:
    cfg: Config
    resources: RuntimeResources
    graph: Any


# =========================
# Prompt / message helpers
# =========================
def load_runtime_resources(cfg: Config) -> RuntimeResources:
    return RuntimeResources(
        schema_instruction=load_optional_text(cfg.schema_instruction_path),
        system_text2sql=load_required_text(cfg.text2sql_prompt_path),
        system_repair=load_required_text(cfg.repair_prompt_path),
        system_semantic_check=load_required_text(cfg.semantic_check_prompt_path),
        system_semantic_repair=load_required_text(cfg.semantic_repair_prompt_path),
        system_rewrite_intent=load_required_text(cfg.rewrite_intent_prompt_path),
        system_rewrite_reflect=load_required_text(cfg.rewrite_reflect_prompt_path),
        system_rewrite_sql=load_required_text(cfg.rewrite_sql_prompt_path),
        cheat_sheet_general=load_optional_text(cfg.sql_cheat_general_path),
        view_catalog=load_optional_text(cfg.view_catalog_path),
    )


def schema_instruction_message(schema_instruction: str) -> List[AnyMessage]:
    if not schema_instruction:
        return []
    return [SystemMessage(f"SCHEMA_INSTRUCTION:\n{schema_instruction}")]


def view_catalog_message(view_catalog: str) -> List[AnyMessage]:
    if not view_catalog:
        return []
    return [SystemMessage(f"VIEW_CATALOG:\n{view_catalog}")]


def build_generate_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_text2sql),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    msgs.extend(view_catalog_message(resources.view_catalog))
    msgs.append(HumanMessage(state["question"]))
    return msgs


def build_repair_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_repair),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"USER_QUESTION:\n{state['question']}"),
        SystemMessage(f"PREVIOUS_SQL:\n{state['sql']}"),
        SystemMessage(f"ERROR:\n{state['error']}"),
        SystemMessage(
            "SQL_CHEAT_SHEET_EXAMPLES:\n"
            + (state.get("cheat_sheet_general", "") or resources.cheat_sheet_general or "(empty)")
        ),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    msgs.extend(view_catalog_message(resources.view_catalog))
    return msgs


def build_semantic_check_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_semantic_check),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"USER_QUESTION:\n{state['previous_question'] or state['question']}"),
        SystemMessage(f"SQL:\n{state['sql']}"),
        SystemMessage(f"RESULT:\n{state['result']}"),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    return msgs


def build_semantic_repair_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_semantic_repair),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"USER_QUESTION:\n{state['previous_question'] or state['question']}"),
        SystemMessage(f"PREVIOUS_SQL:\n{state['sql']}"),
        SystemMessage(f"PREVIOUS_RESULT:\n{state['result']}"),
        SystemMessage(f"SEMANTIC_ERROR:\n{state.get('semantic_error', '')}"),
        SystemMessage(
            "SQL_CHEAT_SHEET_EXAMPLES:\n"
            + (state.get("cheat_sheet_general", "") or resources.cheat_sheet_general or "(empty)")
        ),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    return msgs


def build_rewrite_intent_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    return [
        SystemMessage(resources.system_rewrite_intent),
        HumanMessage(state.get("rewrite_request", "")),
    ]


def build_rewrite_reflection_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_rewrite_reflect),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"ORIGINAL_USER_QUESTION:\n{state['previous_question'] or state['question']}"),
        SystemMessage(f"PREVIOUS_SQL:\n{state.get('previous_sql', '')}"),
        SystemMessage(f"PREVIOUS_RESULT:\n{state.get('previous_result', '')}"),
        SystemMessage(f"REWRITE_MODE:\n{state.get('rewrite_mode', '')}"),
        SystemMessage(f"OPTIONAL_USER_GUIDANCE:\n{state.get('rewrite_guidance', '') or '(none)'}"),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    msgs.append(HumanMessage(state.get("rewrite_request", "[재작성]")))
    return msgs


def build_rewrite_sql_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_rewrite_sql),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"ORIGINAL_USER_QUESTION:\n{state['previous_question'] or state['question']}"),
        SystemMessage(f"PREVIOUS_SQL:\n{state.get('previous_sql', '')}"),
        SystemMessage(f"PREVIOUS_RESULT:\n{state.get('previous_result', '')}"),
        SystemMessage(f"REWRITE_MODE:\n{state.get('rewrite_mode', '')}"),
        SystemMessage(f"OPTIONAL_USER_GUIDANCE:\n{state.get('rewrite_guidance', '') or '(none)'}"),
        SystemMessage(f"REFLECTION:\n{state.get('reflection', '')}"),
        SystemMessage(
            "SQL_CHEAT_SHEET_EXAMPLES:\n"
            + (state.get("cheat_sheet_general", "") or resources.cheat_sheet_general or "(empty)")
        ),
    ]
    msgs.extend(schema_instruction_message(state.get("schema_instruction", "")))
    msgs.extend(view_catalog_message(resources.view_catalog))
    msgs.append(HumanMessage("Rewrite the SQL now."))
    return msgs


# =========================
# LLM builder / validation
# =========================
def build_llm(cfg: Config):
    if cfg.llm_backend == "openai":
        kwargs = {
            "model": cfg.model,
            "temperature": cfg.temperature,
        }
        if cfg.openai_api_key:
            kwargs["api_key"] = cfg.openai_api_key
        if cfg.openai_base_url:
            kwargs["base_url"] = cfg.openai_base_url
        return ChatOpenAI(**kwargs)

    raise ValueError(f"Unsupported LLM_BACKEND: {cfg.llm_backend}")


def validate_text_resources(cfg: Config):
    load_required_text(cfg.text2sql_prompt_path)
    load_required_text(cfg.repair_prompt_path)
    load_required_text(cfg.semantic_check_prompt_path)
    load_required_text(cfg.semantic_repair_prompt_path)
    load_required_text(cfg.rewrite_intent_prompt_path)
    load_required_text(cfg.rewrite_reflect_prompt_path)
    load_required_text(cfg.rewrite_sql_prompt_path)
    load_optional_text(cfg.schema_instruction_path)
    load_optional_text(cfg.sql_cheat_general_path)
    load_optional_text(cfg.view_catalog_path)
    load_optional_text(cfg.view_catalog_csv_path)


def validate_llm_ready(cfg: Config):
    if cfg.llm_backend == "openai":
        if not cfg.openai_base_url:
            raise RuntimeError("OPENAI_BASE_URL is empty.")

        base_url = cfg.openai_base_url.rstrip("/")
        try:
            resp = requests.get(f"{base_url}/models", timeout=10)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to LLM server: {e}")

        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Failed to parse /models response as JSON: {e}")

        model_ids = [x.get("id") for x in data.get("data", []) if isinstance(x, dict)]
        if cfg.model not in model_ids:
            raise RuntimeError(
                f"Configured model '{cfg.model}' not found on server. "
                f"Available models: {model_ids}"
            )
        return

    raise RuntimeError(f"Unsupported LLM_BACKEND: {cfg.llm_backend}")


# =========================
# Graph builder
# =========================
def make_graph(cfg: Config, resources: RuntimeResources):
    llm = build_llm(cfg)

    def node_tick(state: AgentState) -> Dict[str, Any]:
        steps = state.get("steps", 0) + 1
        if steps > cfg.max_steps:
            return {"steps": steps, "error": f"Step limit exceeded (MAX_STEPS={cfg.max_steps})."}
        return {"steps": steps}

    def node_prepare_context(state: AgentState) -> Dict[str, Any]:
        schema = state.get("schema") or get_schema_sqlite_cached(cfg.db_path, resources)
        return {
            "schema": schema,
            "schema_instruction": resources.schema_instruction,
            "cheat_sheet_general": resources.cheat_sheet_general,
        }

    def _check_repeat_sql(state: AgentState, candidate_sql: str) -> str:
        seen = state.get("seen_sql", [])
        n = normalize_sql(candidate_sql)
        repeats = sum(1 for x in seen if normalize_sql(x) == n)
        if repeats > cfg.max_same_sql_repeats:
            return f"Repeated same SQL too many times (MAX_SAME_SQL_REPEATS={cfg.max_same_sql_repeats})."
        return ""

    def node_generate_sql(state: AgentState) -> Dict[str, Any]:
        msgs = build_generate_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        sql = extract_sql(ai.content)
        llm_time = time.perf_counter() - t0

        repeat_err = _check_repeat_sql(state, sql)
        if repeat_err:
            return {
                "messages": [ai],
                "sql": sql,
                "error": repeat_err,
                "semantic_error": "",
                "llm_generate_time": llm_time,
            }

        return {
            "messages": [ai],
            "sql": sql,
            "error": "",
            "semantic_error": "",
            "seen_sql": state.get("seen_sql", []) + [sql],
            "llm_generate_time": llm_time,
        }

    def node_classify_rewrite_intent(state: AgentState) -> Dict[str, Any]:
        msgs = build_rewrite_intent_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        intent_time = time.perf_counter() - t0

        try:
            rewrite_mode, rewrite_guidance = parse_rewrite_intent_payload(ai.content)
        except Exception:
            rewrite_mode = "autonomous"
            rewrite_guidance = ""

        return {
            "messages": [ai],
            "rewrite_mode": rewrite_mode,
            "rewrite_guidance": rewrite_guidance,
            "rewrite_intent_time": intent_time,
            "error": "",
            "semantic_error": "",
        }

    def node_rewrite_reflect(state: AgentState) -> Dict[str, Any]:
        msgs = build_rewrite_reflection_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        reflection = ai.content.strip()
        reflection_time = time.perf_counter() - t0

        return {
            "messages": [ai],
            "reflection": reflection,
            "rewrite_attempts": state.get("rewrite_attempts", 0) + 1,
            "rewrite_reflection_time": state.get("rewrite_reflection_time", 0.0) + reflection_time,
            "error": "",
            "semantic_error": "",
        }

    def node_rewrite_sql(state: AgentState) -> Dict[str, Any]:
        msgs = build_rewrite_sql_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        sql = extract_sql(ai.content)
        rewrite_time = time.perf_counter() - t0

        repeat_err = _check_repeat_sql(state, sql)
        total_rewrite_time = state.get("llm_rewrite_time", 0.0) + rewrite_time
        if repeat_err:
            return {
                "messages": [ai],
                "sql": sql,
                "error": repeat_err,
                "semantic_error": "",
                "llm_rewrite_time": total_rewrite_time,
            }

        return {
            "messages": [ai],
            "sql": sql,
            "error": "",
            "semantic_error": "",
            "seen_sql": state.get("seen_sql", []) + [sql],
            "llm_rewrite_time": total_rewrite_time,
        }

    def node_safety_check(state: AgentState) -> Dict[str, Any]:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return {}

        if cfg.block_non_readonly_sql:
            ok, reason = validate_safe_sql(state["sql"])
            if not ok:
                return {"error": f"Blocked unsafe SQL: {reason}", "semantic_error": ""}

        return {"error": "", "semantic_error": ""}

    def node_execute_sql(state: AgentState) -> Dict[str, Any]:
        csv_path = state["csv_path"]
        try:
            t0 = time.perf_counter()
            out = run_and_save_sqlite(
                cfg.db_path,
                state["sql"],
                csv_path=csv_path,
                max_rows=cfg.max_rows,
            )
            exec_time = time.perf_counter() - t0

            if out.startswith("Error:"):
                return {"result": "", "error": out, "semantic_error": "", "sql_execute_time": exec_time}

            return {"result": out, "error": "", "semantic_error": "", "sql_execute_time": exec_time}
        except Exception as e:
            return {"result": "", "error": f"{type(e).__name__}: {e}", "semantic_error": "", "sql_execute_time": 0.0}

    def node_semantic_check(state: AgentState) -> Dict[str, Any]:
        heuristic_reason = detect_result_quality_issue(
            state.get("previous_question") or state["question"],
            state["sql"],
            state.get("result", ""),
        )
        if heuristic_reason:
            return {
                "semantic_error": heuristic_reason,
                "semantic_check_time": state.get("semantic_check_time", 0.0),
            }

        msgs = build_semantic_check_messages(state, resources)
        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        dt = time.perf_counter() - t0

        try:
            verdict, reason = parse_semantic_verdict_payload(ai.content)
        except Exception:
            return {
                "messages": [ai],
                "semantic_error": "",
                "semantic_check_time": state.get("semantic_check_time", 0.0) + dt,
            }

        return {
            "messages": [ai],
            "semantic_error": "" if verdict == "PASS" else (reason or "Semantic mismatch detected."),
            "semantic_check_time": state.get("semantic_check_time", 0.0) + dt,
        }

    def node_semantic_repair_sql(state: AgentState) -> Dict[str, Any]:
        msgs = build_semantic_repair_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        fixed = extract_sql(ai.content)
        repair_time = time.perf_counter() - t0

        total_repair_time = state.get("llm_semantic_repair_time", 0.0) + repair_time
        repeat_err = _check_repeat_sql(state, fixed)
        if repeat_err:
            return {
                "messages": [ai],
                "sql": fixed,
                "attempts": state["attempts"] + 1,
                "error": repeat_err,
                "llm_semantic_repair_time": total_repair_time,
            }

        return {
            "messages": [ai],
            "sql": fixed,
            "attempts": state["attempts"] + 1,
            "error": "",
            "semantic_error": "",
            "seen_sql": state.get("seen_sql", []) + [fixed],
            "llm_semantic_repair_time": total_repair_time,
        }

    def node_repair_sql(state: AgentState) -> Dict[str, Any]:
        msgs = build_repair_messages(state, resources)

        t0 = time.perf_counter()
        ai = llm.invoke(msgs)
        fixed = extract_sql(ai.content)
        repair_time = time.perf_counter() - t0

        total_repair_time = state.get("llm_repair_time", 0.0) + repair_time

        repeat_err = _check_repeat_sql(state, fixed)
        if repeat_err:
            return {
                "messages": [ai],
                "sql": fixed,
                "attempts": state["attempts"] + 1,
                "error": repeat_err,
                "semantic_error": "",
                "llm_repair_time": total_repair_time,
            }

        return {
            "messages": [ai],
            "sql": fixed,
            "attempts": state["attempts"] + 1,
            "error": "",
            "semantic_error": "",
            "seen_sql": state.get("seen_sql", []) + [fixed],
            "llm_repair_time": total_repair_time,
        }

    def route_after_tick(state: AgentState) -> str:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return END
        return "prepare_context" if not state.get("schema") else "safety_check"

    def route_after_prepare_context(state: AgentState) -> str:
        return "classify_rewrite_intent" if state.get("rewrite_request") else "generate_sql"

    def route_after_safety(state: AgentState) -> str:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return END
        return "repair_sql" if state.get("error") else "execute_sql"

    def route_after_execute(state: AgentState) -> str:
        if state.get("error"):
            if state["attempts"] >= cfg.max_repair_attempts:
                return END
            return "repair_sql"
        if cfg.enable_semantic_check:
            return "semantic_check"
        return END

    def route_after_semantic_check(state: AgentState) -> str:
        if state.get("error"):
            if state["attempts"] >= cfg.max_repair_attempts:
                return END
            return "repair_sql"

        if state.get("semantic_error"):
            if state["attempts"] >= cfg.max_repair_attempts:
                return END
            return "semantic_repair_sql"

        return END

    g = StateGraph(AgentState)

    g.add_node("tick", node_tick)
    g.add_node("prepare_context", node_prepare_context)
    g.add_node("generate_sql", node_generate_sql)
    g.add_node("classify_rewrite_intent", node_classify_rewrite_intent)
    g.add_node("rewrite_reflect", node_rewrite_reflect)
    g.add_node("rewrite_sql", node_rewrite_sql)
    g.add_node("safety_check", node_safety_check)
    g.add_node("execute_sql", node_execute_sql)
    g.add_node("semantic_check", node_semantic_check)
    g.add_node("semantic_repair_sql", node_semantic_repair_sql)
    g.add_node("repair_sql", node_repair_sql)

    g.add_edge(START, "tick")
    g.add_conditional_edges(
        "tick",
        route_after_tick,
        {
            "prepare_context": "prepare_context",
            "safety_check": "safety_check",
            END: END,
        },
    )

    g.add_conditional_edges(
        "prepare_context",
        route_after_prepare_context,
        {
            "generate_sql": "generate_sql",
            "classify_rewrite_intent": "classify_rewrite_intent",
        },
    )
    g.add_edge("generate_sql", "tick")
    g.add_edge("classify_rewrite_intent", "rewrite_reflect")
    g.add_edge("rewrite_reflect", "rewrite_sql")
    g.add_edge("rewrite_sql", "tick")

    g.add_conditional_edges(
        "safety_check",
        route_after_safety,
        {
            "execute_sql": "execute_sql",
            "repair_sql": "repair_sql",
            END: END,
        },
    )

    g.add_edge("repair_sql", "tick")
    g.add_edge("semantic_repair_sql", "tick")

    g.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "repair_sql": "repair_sql",
            "semantic_check": "semantic_check",
            END: END,
        },
    )

    g.add_conditional_edges(
        "semantic_check",
        route_after_semantic_check,
        {
            "repair_sql": "repair_sql",
            "semantic_repair_sql": "semantic_repair_sql",
            END: END,
        },
    )

    return g.compile()


# =========================
# Misc
# =========================
def get_time() -> str:
    return datetime.now().strftime("%y%m%d%H%M%S")


def save_sql_txt(question: str, sql: str, out_path: Path, meta: Optional[Dict[str, str]] = None):
    lines = [f"Question: {question}", "", "SQL:", sql.strip(), ""]
    if meta:
        lines.append("META:")
        for k, v in meta.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def make_empty_state(question: str, csv_path: Path) -> AgentState:
    return {
        "messages": [],
        "question": question,
        "schema": "",
        "schema_instruction": "",
        "sql": "",
        "result": "",
        "error": "",
        "semantic_error": "",
        "attempts": 0,
        "steps": 0,
        "seen_sql": [],
        "csv_path": csv_path,
        "llm_generate_time": 0.0,
        "llm_repair_time": 0.0,
        "sql_execute_time": 0.0,
        "semantic_check_time": 0.0,
        "llm_semantic_repair_time": 0.0,
        "rewrite_mode": "",
        "rewrite_request": "",
        "rewrite_guidance": "",
        "previous_question": "",
        "previous_sql": "",
        "previous_result": "",
        "reflection": "",
        "rewrite_attempts": 0,
        "rewrite_reflection_time": 0.0,
        "llm_rewrite_time": 0.0,
        "rewrite_intent_time": 0.0,
        "cheat_sheet_general": "",
    }




def build_config_from_env() -> Config:
    load_dotenv()

    db_url = env_str("DB_URL", "sqlite:///outputs/arma_sql/state.db")
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Only sqlite DB_URL supported. Got: {db_url}")

    db_path = db_url.replace("sqlite:///", "")
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB not found: {db_path}\nRun: python test_dump_arma.py")

    return Config(
        db_path=db_path,
        schema_instruction_path=env_str("SCHEMA_INSTRUCTION_PATH", "text2sql_prompts/schema_instruction_main.md"),
        llm_backend=env_str("LLM_BACKEND", "openai"),
        model=env_str("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=env_float("OPENAI_TEMPERATURE", 0.0),
        openai_api_key=env_str("OPENAI_API_KEY", ""),
        openai_base_url=env_str("OPENAI_BASE_URL", ""),
        text2sql_prompt_path=env_str("TEXT2SQL_PROMPT_PATH", "text2sql_prompts/system_text2sql.md"),
        repair_prompt_path=env_str("REPAIR_PROMPT_PATH", "text2sql_prompts/system_repair.md"),
        semantic_check_prompt_path=env_str(
            "SEMANTIC_CHECK_PROMPT_PATH", "text2sql_prompts/system_semantic_check.md"
        ),
        semantic_repair_prompt_path=env_str(
            "SEMANTIC_REPAIR_PROMPT_PATH", "text2sql_prompts/system_semantic_repair.md"
        ),
        rewrite_intent_prompt_path=env_str(
            "REWRITE_INTENT_PROMPT_PATH", "text2sql_prompts/system_rewrite_intent.md"
        ),
        rewrite_reflect_prompt_path=env_str(
            "REWRITE_REFLECT_PROMPT_PATH", "text2sql_prompts/system_rewrite_reflect.md"
        ),
        rewrite_sql_prompt_path=env_str(
            "REWRITE_SQL_PROMPT_PATH", "text2sql_prompts/system_rewrite_sql.md"
        ),
        sql_cheat_general_path=env_str(
            "SQL_CHEAT_GENERAL_PATH", "text2sql_prompts/SQL_cheating_sheets/general.md"
        ),
        view_catalog_path=env_str(
            "VIEW_CATALOG_PATH", "text2sql_prompts/SQL_cheating_sheets/view_catalog.md"
        ),
        view_catalog_csv_path=env_str(
            "VIEW_CATALOG_CSV_PATH", "text2sql_prompts/SQL_cheating_sheets/view_catalog.csv"
        ),
        max_repair_attempts=env_int("MAX_REPAIR_ATTEMPTS", 3),
        max_steps=env_int("MAX_STEPS", 12),
        max_same_sql_repeats=env_int("MAX_SAME_SQL_REPEATS", 1),
        max_rows=env_int("MAX_ROWS", 50),
        block_non_readonly_sql=env_bool("BLOCK_NON_READONLY_SQL", True),
        enable_semantic_check=env_bool("ENABLE_SEMANTIC_CHECK", True),
        output_dir=env_str("OUT_DIR", "results"),
    )


_RUNTIME_CACHE: Optional[Text2SQLRuntime] = None


def get_runtime(force_reload: bool = False) -> Text2SQLRuntime:
    global _RUNTIME_CACHE

    if _RUNTIME_CACHE is not None and not force_reload:
        return _RUNTIME_CACHE

    cfg = build_config_from_env()
    validate_text_resources(cfg)
    validate_llm_ready(cfg)
    resources = load_runtime_resources(cfg)
    registration_summary = register_views_from_catalog_csv(cfg.db_path, cfg.view_catalog_csv_path)
    resources.view_registration_summary = registration_summary
    print(f"⚡{registration_summary}")
    graph = make_graph(cfg, resources)

    _RUNTIME_CACHE = Text2SQLRuntime(cfg=cfg, resources=resources, graph=graph)
    return _RUNTIME_CACHE


def run_text2sql_query(question: str, runtime: Optional[Text2SQLRuntime] = None) -> Dict[str, Any]:
    question = (question or "").strip()
    if not question:
        return {
            "ok": False,
            "question": question,
            "sql": "",
            "result": "",
            "error": "Empty question.",
            "semantic_error": "",
            "rewrite_mode": "",
            "rewrite_guidance": "",
            "reflection": "",
            "attempts": 0,
            "rewrite_attempts": 0,
            "steps": 0,
            "timing": {},
            "artifacts": {
                "sql_path": "",
                "csv_path": "",
            },
        }

    try:
        runtime = runtime or get_runtime()
        out_dir = Path(runtime.cfg.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        run_id = get_time()
        sql_path = out_dir / f"{run_id}_sql.txt"
        csv_path = out_dir / f"{run_id}_result.csv"

        init_state = make_empty_state(question, csv_path)
        final_state = runtime.graph.invoke(init_state)

        sql_text = (final_state.get("sql") or "").strip()
        semantic_error = (final_state.get("semantic_error") or "").strip()
        error = (final_state.get("error") or "").strip()
        result = (final_state.get("result") or "").strip()

        save_sql_txt(
            final_state.get("question", question),
            sql_text,
            sql_path,
            meta={
                "rewrite_mode": final_state.get("rewrite_mode", "") or "normal",
                "rewrite_guidance": final_state.get("rewrite_guidance", ""),
                "reflection": final_state.get("reflection", ""),
                "semantic_error": semantic_error,
            },
        )

        return {
            "ok": not bool(error),
            "question": final_state.get("question", question),
            "sql": sql_text,
            "result": result if result else "(no result)",
            "error": error,
            "semantic_error": semantic_error,
            "rewrite_mode": final_state.get("rewrite_mode", "") or "normal",
            "rewrite_guidance": final_state.get("rewrite_guidance", ""),
            "reflection": final_state.get("reflection", ""),
            "attempts": final_state.get("attempts", 0),
            "rewrite_attempts": final_state.get("rewrite_attempts", 0),
            "steps": final_state.get("steps", 0),
            "timing": {
                "llm_generate_time": final_state.get("llm_generate_time", 0.0),
                "rewrite_intent_time": final_state.get("rewrite_intent_time", 0.0),
                "rewrite_reflection_time": final_state.get("rewrite_reflection_time", 0.0),
                "llm_rewrite_time": final_state.get("llm_rewrite_time", 0.0),
                "llm_repair_time": final_state.get("llm_repair_time", 0.0),
                "semantic_check_time": final_state.get("semantic_check_time", 0.0),
                "llm_semantic_repair_time": final_state.get("llm_semantic_repair_time", 0.0),
                "sql_execute_time": final_state.get("sql_execute_time", 0.0),
            },
            "artifacts": {
                "sql_path": str(sql_path),
                "csv_path": str(csv_path),
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "question": question,
            "sql": "",
            "result": "",
            "error": f"{type(e).__name__}: {e}",
            "semantic_error": "",
            "rewrite_mode": "",
            "rewrite_guidance": "",
            "reflection": "",
            "attempts": 0,
            "rewrite_attempts": 0,
            "steps": 0,
            "timing": {},
            "artifacts": {
                "sql_path": "",
                "csv_path": "",
            },
        }


# =========================
# Main (CLI)
# =========================
def main():
    print("⚡Checking prompt files...")
    print("⚡Checking LLM connectivity/model availability...")

    runtime = get_runtime(force_reload=True)
    cfg = runtime.cfg
    graph = runtime.graph

    print(f"⚡Connected to SQLite: {cfg.db_path}")
    print(f"⚡LLM backend: {cfg.llm_backend}")
    print(f"⚡Model: {cfg.model}")
    print(
        f"⚡Limits: MAX_REPAIR_ATTEMPTS={cfg.max_repair_attempts}, "
        f"MAX_STEPS={cfg.max_steps}, "
        f"MAX_SAME_SQL_REPEATS={cfg.max_same_sql_repeats}, "
        f"Semantic-check-before-answering enabled: {cfg.enable_semantic_check}"
    )
    print("⚡Type 'exit' to quit.")
    print("⚡Rewrite commands:")
    print("  e.g. (1) '[재작성]' -> autonomous rewrite")
    print("           '[Rewrite]' -> autonomous rewrite")
    print("  e.g. (2) '[재작성] 최신 1건만 보여줘!' -> guided rewrite")
    print("           '[Rewrite] Show the recent 1 case only!' -> guided rewrite")
    print()

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    last_run: Optional[Dict[str, str]] = None

    while True:
        run_id = get_time()
        sql_path = out_dir / f"{run_id}_sql.txt"
        csv_path = out_dir / f"{run_id}_result.csv"

        q = input("Question> ").strip()
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            print('➜] Terminated. Have a nice day!')
            break

        init_state = make_empty_state(q, csv_path)

        if is_rewrite_request(q):
            if not last_run:
                print("\n[ERROR] There are no previous execution results to rewrite. Please input the general query text first.\n")
                continue

            init_state["question"] = last_run.get("question", "")
            init_state["rewrite_request"] = q
            init_state["previous_question"] = last_run.get("question", "")
            init_state["previous_sql"] = last_run.get("sql", "")
            init_state["previous_result"] = last_run.get("result", "")
            init_state["seen_sql"] = [last_run.get("sql", "")] if last_run.get("sql") else []
        else:
            init_state["question"] = q

        final_state = graph.invoke(init_state)

        sql_text = final_state.get("sql", "").strip()
        save_sql_txt(
            final_state.get("question", q),
            sql_text,
            sql_path,
            meta={
                "rewrite_mode": final_state.get("rewrite_mode", "") or "normal",
                "rewrite_guidance": final_state.get("rewrite_guidance", ""),
                "reflection": final_state.get("reflection", ""),
                "semantic_error": final_state.get("semantic_error", ""),
            },
        )

        last_run = {
            "question": final_state.get("question", q),
            "sql": final_state.get("sql", ""),
            "result": final_state.get("result", ""),
            "error": final_state.get("error", ""),
        }

        if final_state.get("rewrite_mode"):
            print("\n--- REWRITE ---")
            print(f"mode: {final_state.get('rewrite_mode', '')}")
            if final_state.get("rewrite_guidance"):
                print(f"guidance: {final_state.get('rewrite_guidance', '')}")
            print("reflection:")
            print(final_state.get("reflection", "(no reflection)"))

        print("\n--- SQL ---")
        print(final_state.get("sql", "").strip())

        print("\n--- RESULT ---")
        if final_state.get("result"):
            print(final_state["result"])
        else:
            print("(no result)")

        if final_state.get("semantic_error"):
            print("\n--- SEMANTIC ERROR ---")
            print(final_state["semantic_error"])

        if final_state.get("error"):
            print("\n--- ERROR ---")
            print(final_state["error"])
            print(
                f"(attempts={final_state.get('attempts', 0)}, "
                f"rewrite_attempts={final_state.get('rewrite_attempts', 0)}, "
                f"steps={final_state.get('steps', 0)})"
            )

        print("\n--- TIMING ---")
        print(f"LLM generate:                           {final_state.get('llm_generate_time', 0.0):.4f} sec")
        print(f"LLM repair to handle SQL-runtime error: {final_state.get('llm_repair_time', 0.0):.4f} sec")
        if final_state.get('semantic_check_time'):
            print("*** Before providing final answer ->")
            print(f"LLM semantic check:                 {final_state.get('semantic_check_time', 0.0):.4f} sec")
            print(f"LLM semantic repair:                {final_state.get('llm_semantic_repair_time', 0.0):.4f} sec")
        if final_state.get('rewrite_intent_time'):
            print("*** For handling user's rewriting request ->")
            print(f"LLM rewrite:                        {final_state.get('llm_rewrite_time', 0.0):.4f} sec")
            print(f"LLM reflection intent analysis:     {final_state.get('rewrite_intent_time', 0.0):.4f} sec")
            print(f"LLM reflection:                     {final_state.get('rewrite_reflection_time', 0.0):.4f} sec")
        print(f"SQL execute time:                       {final_state.get('sql_execute_time', 0.0):.4f} sec")
        print()


if __name__ == "__main__":
    main()
