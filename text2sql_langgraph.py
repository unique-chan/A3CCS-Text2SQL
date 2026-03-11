import os
import re
import csv
import sqlite3
import requests

from dataclasses import dataclass
from datetime import datetime
from operator import add
from pathlib import Path
from typing import Annotated, Any, Dict, List
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from langchain_huggingface import HuggingFacePipeline
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

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


def normalize_sql(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"^\s*(--.*\n|/\*.*?\*/\s*)*", "", s, flags=re.S)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r";+$", "", s)
    return s.strip()


def is_safe_sql(sql: str) -> bool:
    s = normalize_sql(sql)
    return s.startswith("select") or s.startswith("with")


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


def looks_like_refusal_result(result_text: str) -> bool:
    s = result_text.lower()
    keywords = [
        "not possible",
        "cannot",
        "insufficient",
        "schema does not",
        "not provided",
        "unable to",
        "can't",
        "no information",
    ]
    return any(k in s for k in keywords)


# =========================
# State / config / resources
# =========================
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add]
    question: str
    schema: str
    instruction: str
    sql: str
    result: str
    error: str
    attempts: int
    steps: int
    seen_sql: List[str]
    csv_path: Path


@dataclass
class Config:
    db_path: str
    instruction_path: str

    llm_backend: str  # "openai" or "local"

    model: str
    temperature: float

    openai_api_key: str
    openai_base_url: str

    local_model_path: str
    local_max_new_tokens: int

    text2sql_prompt_path: str
    repair_prompt_path: str

    max_repair_attempts: int
    max_steps: int
    max_same_sql_repeats: int
    max_rows: int

    block_non_readonly_sql: bool
    treat_refusal_result_as_error: bool

    output_dir: str


@dataclass
class RuntimeResources:
    instruction: str
    system_text2sql: str
    system_repair: str


# =========================
# Prompt / message helpers
# =========================
def load_runtime_resources(cfg: Config) -> RuntimeResources:
    return RuntimeResources(
        instruction=load_optional_text(cfg.instruction_path),
        system_text2sql=load_required_text(cfg.text2sql_prompt_path),
        system_repair=load_required_text(cfg.repair_prompt_path),
    )


def maybe_instruction_messages(instruction: str) -> List[AnyMessage]:
    if not instruction:
        return []
    return [SystemMessage(f"INSTRUCTION:\n{instruction}")]


def build_generate_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_text2sql),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
    ]
    msgs.extend(maybe_instruction_messages(state.get("instruction", "")))
    msgs.append(HumanMessage(state["question"]))
    return msgs


def build_repair_messages(state: AgentState, resources: RuntimeResources) -> List[AnyMessage]:
    msgs: List[AnyMessage] = [
        SystemMessage(resources.system_repair),
        SystemMessage(f"SCHEMA:\n{state['schema']}"),
        SystemMessage(f"USER_QUESTION:\n{state['question']}"),
        SystemMessage(f"PREVIOUS_SQL:\n{state['sql']}"),
        SystemMessage(f"ERROR:\n{state['error']}"),
    ]
    msgs.extend(maybe_instruction_messages(state.get("instruction", "")))
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

    if cfg.llm_backend == "local":
        model_name_or_path = cfg.local_model_path if cfg.local_model_path else cfg.model

        tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            torch_dtype="auto",
            device_map="auto",
        )

        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=cfg.local_max_new_tokens,
        )
        return HuggingFacePipeline(pipeline=pipe)

    raise ValueError(f"Unsupported LLM_BACKEND: {cfg.llm_backend}")


def validate_text_resources(cfg: Config):
    load_required_text(cfg.text2sql_prompt_path)
    load_required_text(cfg.repair_prompt_path)
    load_optional_text(cfg.instruction_path)


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

    if cfg.llm_backend == "local":
        model_name_or_path = cfg.local_model_path if cfg.local_model_path else cfg.model

        # local path explicitly given -> must exist
        if cfg.local_model_path:
            if not Path(cfg.local_model_path).exists():
                raise RuntimeError(f"Local model path not found: {cfg.local_model_path}")
            return

        # otherwise cfg.model may be HF repo id or a local relative path
        if Path(model_name_or_path).exists():
            return

        # HF repo id case: existence check skipped here
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
        schema = get_schema_sqlite(cfg.db_path)
        return {
            "schema": schema,
            "instruction": resources.instruction,
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
        ai = llm.invoke(msgs)
        sql = extract_sql(ai.content)

        repeat_err = _check_repeat_sql(state, sql)
        if repeat_err:
            return {"messages": [ai], "sql": sql, "error": repeat_err}

        return {
            "messages": [ai],
            "sql": sql,
            "error": "",
            "seen_sql": state.get("seen_sql", []) + [sql],
        }

    def node_safety_check(state: AgentState) -> Dict[str, Any]:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return {}

        if cfg.block_non_readonly_sql and not is_safe_sql(state["sql"]):
            return {"error": "Blocked non-read-only SQL. Only SELECT/WITH are allowed."}

        return {"error": ""}

    def node_execute_sql(state: AgentState) -> Dict[str, Any]:
        csv_path = state["csv_path"]
        try:
            out = run_and_save_sqlite(
                cfg.db_path,
                state["sql"],
                csv_path=csv_path,
                max_rows=cfg.max_rows,
            )

            if cfg.treat_refusal_result_as_error and looks_like_refusal_result(out):
                return {
                    "result": out,
                    "error": "Refusal-style result detected; must attempt a real computation/query."
                }

            return {"result": out, "error": ""}
        except Exception as e:
            return {"result": "", "error": f"{type(e).__name__}: {e}"}

    def node_repair_sql(state: AgentState) -> Dict[str, Any]:
        msgs = build_repair_messages(state, resources)
        ai = llm.invoke(msgs)
        fixed = extract_sql(ai.content)

        repeat_err = _check_repeat_sql(state, fixed)
        if repeat_err:
            return {
                "messages": [ai],
                "sql": fixed,
                "attempts": state["attempts"] + 1,
                "error": repeat_err,
            }

        return {
            "messages": [ai],
            "sql": fixed,
            "attempts": state["attempts"] + 1,
            "error": "",
            "seen_sql": state.get("seen_sql", []) + [fixed],
        }

    def route_after_tick(state: AgentState) -> str:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return END
        return "prepare_context" if not state.get("schema") else "safety_check"

    def route_after_safety(state: AgentState) -> str:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return END
        return "repair_sql" if state.get("error") else "execute_sql"

    def route_after_execute(state: AgentState) -> str:
        if not state.get("error"):
            return END
        if state["attempts"] >= cfg.max_repair_attempts:
            return END
        return "repair_sql"

    g = StateGraph(AgentState)

    g.add_node("tick", node_tick)
    g.add_node("prepare_context", node_prepare_context)
    g.add_node("generate_sql", node_generate_sql)
    g.add_node("safety_check", node_safety_check)
    g.add_node("execute_sql", node_execute_sql)
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

    g.add_edge("prepare_context", "generate_sql")
    g.add_edge("generate_sql", "tick")

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

    g.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "repair_sql": "repair_sql",
            END: END,
        },
    )

    return g.compile()


# =========================
# Misc
# =========================
def get_time() -> str:
    return datetime.now().strftime("%y%m%d%H%M%S")


def save_sql_txt(question: str, sql: str, out_path: Path):
    content = f"Question: {question}\n\nSQL:\n{sql.strip()}\n"
    out_path.write_text(content, encoding="utf-8")


# =========================
# Main (CLI)
# =========================
def main():
    load_dotenv()

    db_url = env_str("DB_URL", "sqlite:///outputs/arma_sql/state.db")
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Only sqlite DB_URL supported. Got: {db_url}")

    db_path = db_url.replace("sqlite:///", "")
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB not found: {db_path}\nRun: python test_dump_arma.py")

    cfg = Config(
        db_path=db_path,
        instruction_path=env_str("INSTRUCTION_PATH", "INSTRUCTION.md"),

        llm_backend=env_str("LLM_BACKEND", "openai"),

        model=env_str("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=env_float("OPENAI_TEMPERATURE", 0.0),

        openai_api_key=env_str("OPENAI_API_KEY", ""),
        openai_base_url=env_str("OPENAI_BASE_URL", ""),

        local_model_path=env_str("LOCAL_MODEL_PATH", ""),
        local_max_new_tokens=env_int("LOCAL_MAX_NEW_TOKENS", 512),

        text2sql_prompt_path=env_str("TEXT2SQL_PROMPT_PATH", "prompts/system_text2sql.md"),
        repair_prompt_path=env_str("REPAIR_PROMPT_PATH", "prompts/system_repair.md"),

        max_repair_attempts=env_int("MAX_REPAIR_ATTEMPTS", 3),
        max_steps=env_int("MAX_STEPS", 10),
        max_same_sql_repeats=env_int("MAX_SAME_SQL_REPEATS", 1),
        max_rows=env_int("MAX_ROWS", 50),

        block_non_readonly_sql=env_bool("BLOCK_NON_READONLY_SQL", True),
        treat_refusal_result_as_error=env_bool("TREAT_REFUSAL_RESULT_AS_ERROR", True),

        output_dir=env_str("OUT_DIR", "results"),
    )

    print("🔌 Checking prompt files...")
    validate_text_resources(cfg)

    print("🔌 Checking LLM connectivity/model availability...")
    validate_llm_ready(cfg)

    resources = load_runtime_resources(cfg)
    graph = make_graph(cfg, resources)

    print(f"🔌 Connected to SQLite: {cfg.db_path}")
    print(f"🔌 LLM backend: {cfg.llm_backend}")
    print(f"🔌 Model: {cfg.model}")
    print(
        f"🔌 Limits: MAX_REPAIR_ATTEMPTS={cfg.max_repair_attempts}, "
        f"MAX_STEPS={cfg.max_steps}, "
        f"MAX_SAME_SQL_REPEATS={cfg.max_same_sql_repeats}"
    )
    print("🔌 Type 'exit' to quit.\n")

    out_dir = Path(cfg.output_dir)  # Path(env_str("OUT_DIR", "results"))
    out_dir.mkdir(parents=True, exist_ok=True)

    while True:
        run_id = get_time()
        sql_path = out_dir / f"{run_id}_sql.txt"
        csv_path = out_dir / f"{run_id}_result.csv"

        q = input("Question> ").strip()
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break

        init_state: AgentState = {
            "messages": [],
            "question": q,
            "schema": "",
            "instruction": "",
            "sql": "",
            "result": "",
            "error": "",
            "attempts": 0,
            "steps": 0,
            "seen_sql": [],
            "csv_path": csv_path,
        }

        final_state = graph.invoke(init_state)

        sql_text = final_state.get("sql", "").strip()
        save_sql_txt(q, sql_text, sql_path)

        if sql_text:
            try:
                run_and_save_sqlite(
                    cfg.db_path,
                    sql_text,
                    csv_path,
                    max_rows=cfg.max_rows,
                )
            except Exception as e:
                final_state["error"] = (
                    final_state.get("error", "") + f"\n[csv save error] {e}"
                ).strip()

        print("\n--- SQL ---")
        print(final_state.get("sql", "").strip())

        print("\n--- RESULT ---")
        if final_state.get("result"):
            print(final_state["result"])
        else:
            print("(no result)")

        if final_state.get("error"):
            print("\n--- ERROR ---")
            print(final_state["error"])
            print(
                f"(attempts={final_state.get('attempts', 0)}, "
                f"steps={final_state.get('steps', 0)})"
            )

        print("\n")


if __name__ == "__main__":
    main()