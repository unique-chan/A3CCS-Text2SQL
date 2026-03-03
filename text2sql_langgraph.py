import os
import re
import sqlite3
from dataclasses import dataclass
from operator import add
from pathlib import Path
from typing import Annotated, Any, Dict, List
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END


# =========================
# Utils: env parsing
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


# =========================
# DB helpers
# =========================
def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_sqlite(db_path: str) -> str:
    """Return schema text for prompting (tables, columns, create statements)."""
    conn = _connect_sqlite(db_path)
    try:
        cur = conn.cursor()
        tables = cur.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
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
    s = re.sub(r"^\s*(--.*\n|/\*.*?\*/\s*)*", "", s, flags=re.S)  # strip leading comments
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r";+$", "", s)
    return s.strip()


def is_safe_sql(sql: str) -> bool:
    """Allow only SELECT / WITH (read-only)."""
    s = normalize_sql(sql)
    return s.startswith("select") or s.startswith("with")


def run_sqlite(db_path: str, sql: str, max_rows: int = 50) -> str:
    """Execute SQL and return a pretty column-aligned text table (like .header on + .mode column)."""
    conn = _connect_sqlite(db_path)
    try:
        cur = conn.cursor()
        cur.execute(sql)

        if cur.description is not None:
            rows = cur.fetchmany(max_rows)
            cols = [d[0] for d in cur.description]

            if not rows:
                return "(0 rows)"

            # column widths
            widths = [len(c) for c in cols]
            for r in rows:
                for i in range(len(cols)):
                    widths[i] = max(widths[i], len(str(r[i])))

            def fmt(vals):
                return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(vals))

            out = []
            out.append(fmt(cols))
            out.append("-+-".join("-" * w for w in widths))
            for r in rows:
                out.append(fmt([r[i] for i in range(len(cols))]))
            if len(rows) == max_rows:
                out.append(f"... (showing first {max_rows} rows)")
            return "\n".join(out)

        conn.commit()
        return "(ok)"
    finally:
        conn.close()


def extract_sql(text: str) -> str:
    """Prefer ```sql ...``` blocks; fallback to whole text."""
    m = re.search(r"```sql\s*(.*?)\s*```", text, flags=re.S | re.I)
    if m:
        return m.group(1).strip().rstrip(";") + ";"
    t = text.strip()
    t = re.sub(r"^```.*?\n|\n```$", "", t, flags=re.S)
    return t.rstrip(";") + ";"


def looks_like_refusal_result(result_text: str) -> bool:
    """
    Heuristic: if the model produced a 'message' row claiming not possible/cannot.
    You can tune these keywords.
    """
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
# LangGraph state + config
# =========================
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add]
    question: str
    schema: str
    sql: str
    result: str
    error: str
    attempts: int
    steps: int
    seen_sql: List[str]
    instruction: str      #
    db_schema_doc: str    #


@dataclass
class Config:
    db_path: str
    instruction_path: str   #

    model: str
    temperature: float

    max_repair_attempts: int
    max_steps: int
    max_same_sql_repeats: int
    max_rows: int

    block_non_readonly_sql: bool
    treat_refusal_result_as_error: bool


# =========================
# Prompts
# =========================
SYSTEM_TEXT2SQL = """You are a Text-to-SQL assistant for a SQLite database.

Rules:
- Generate a SINGLE SQLite SQL query that answers the user's question.
- Use ONLY the provided schema. If a column/table does not exist, do not hallucinate it.
- Prefer simple, correct SQL.
- Default to LIMIT 50 for potentially large outputs unless the user explicitly asks otherwise.
- Output ONLY SQL inside a ```sql``` code block. No extra explanation.
- Read-only: produce SELECT/CTE (WITH) queries only.
- DO NOT use sqlite3 CLI meta-commands such as .header, .mode, .tables, .schema
- DO NOT return "not possible" / "cannot" / "insufficient schema" as a fake SELECT message.
- If the user asks for derived computation (e.g., speed), attempt best-effort using available time/position columns:
  - Use window functions LAG() OVER (PARTITION BY ... ORDER BY ...)
  - Use sqrt(dx*dx + dy*dy + dz*dz) / dt
  - If timestamp is ISO text, dt_seconds = (julianday(t)-julianday(t_prev))*86400.0
"""

SYSTEM_REPAIR = """You are a SQL repair assistant for SQLite.

You will be given:
- The database schema
- The user's question
- A previous SQL query
- The execution error (or a policy error)

Your job:
- Fix the SQL so it runs on SQLite AND matches the user intent.
- Use ONLY the provided schema.
- Output ONLY the corrected SQL inside a ```sql``` code block. No explanation.
- Read-only: SELECT/CTE only.
- Do NOT answer with a fake SELECT message like "Not possible".
"""


# =========================
# Graph builder
# =========================
def make_graph(cfg: Config):
    llm = ChatOpenAI(model=cfg.model, temperature=cfg.temperature)

    def node_tick(state: AgentState) -> Dict[str, Any]:
        steps = state.get("steps", 0) + 1
        if steps > cfg.max_steps:
            return {"steps": steps, "error": f"Step limit exceeded (MAX_STEPS={cfg.max_steps})."}
        return {"steps": steps}

    def node_load_schema(state: AgentState) -> Dict[str, Any]:
        schema = get_schema_sqlite(cfg.db_path)
        instruction = ""
        if Path(cfg.instruction_path).exists():
            instruction = Path(cfg.instruction_path).read_text(encoding="utf-8")
        else:
            print(f"📄 INSTRUCTION file does not exist: {cfg.instruction_path}")
        return {"schema": schema, "instruction": instruction}

    def _check_repeat_sql(state: AgentState, candidate_sql: str) -> str:
        seen = state.get("seen_sql", [])
        n = normalize_sql(candidate_sql)
        repeats = sum(1 for x in seen if normalize_sql(x) == n)
        if repeats > cfg.max_same_sql_repeats:
            return f"Repeated same SQL too many times (MAX_SAME_SQL_REPEATS={cfg.max_same_sql_repeats})."
        return ""

    def node_generate_sql(state: AgentState) -> Dict[str, Any]:
        msgs: List[AnyMessage] = [
            SystemMessage(SYSTEM_TEXT2SQL),
            SystemMessage(f"SCHEMA:\n{state['schema']}"),
            # HumanMessage(state["question"]),
        ]
        if state.get("instruction"):
            msgs.append(SystemMessage(f"INSTRUCTION:\n{state['instruction']}"))
        else:
            print(f"📄 INSTRUCTION file does not exist: {cfg.instruction_path}")
        msgs.append(HumanMessage(state["question"]))
        ## *** ##
        ai = llm.invoke(msgs)
        sql = extract_sql(ai.content)

        repeat_err = _check_repeat_sql(state, sql)
        if repeat_err:
            return {"messages": [ai], "sql": sql, "error": repeat_err}

        return {"messages": [ai], "sql": sql, "error": "", "seen_sql": state.get("seen_sql", []) + [sql]}

    def node_safety_check(state: AgentState) -> Dict[str, Any]:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return {}  # keep error, will route to END

        if cfg.block_non_readonly_sql and not is_safe_sql(state["sql"]):
            return {"error": "Blocked non-read-only SQL. Only SELECT/WITH are allowed."}

        return {"error": ""}  # clear safety error

    def node_execute_sql(state: AgentState) -> Dict[str, Any]:
        try:
            out = run_sqlite(cfg.db_path, state["sql"], max_rows=cfg.max_rows)

            if cfg.treat_refusal_result_as_error and looks_like_refusal_result(out):
                return {"result": out, "error": "Refusal-style result detected; must attempt a real computation/query."}

            return {"result": out, "error": ""}
        except Exception as e:
            return {"result": "", "error": f"{type(e).__name__}: {e}"}

    def node_repair_sql(state: AgentState) -> Dict[str, Any]:
        msgs: List[AnyMessage] = [
            SystemMessage(SYSTEM_REPAIR),
            SystemMessage(f"SCHEMA:\n{state['schema']}"),
            SystemMessage(f"USER_QUESTION:\n{state['question']}"),
            SystemMessage(f"PREVIOUS_SQL:\n{state['sql']}"),
            SystemMessage(f"ERROR:\n{state['error']}"),
        ]
        if state.get("instruction"):
            msgs.append(SystemMessage(f"INSTRUCTION:\n{state['instruction']}"))
        else:
            print(f"📄 INSTRUCTION file does not exist: {cfg.instruction_path}")
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
            "error": "",  # clear
            "seen_sql": state.get("seen_sql", []) + [fixed],
        }

    def route_after_tick(state: AgentState) -> str:
        if state.get("error") and "Step limit exceeded" in state["error"]:
            return END
        return "load_schema" if not state.get("schema") else "safety_check"

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
    g.add_node("load_schema", node_load_schema)
    g.add_node("generate_sql", node_generate_sql)
    g.add_node("safety_check", node_safety_check)
    g.add_node("execute_sql", node_execute_sql)
    g.add_node("repair_sql", node_repair_sql)

    # Start -> tick -> load_schema -> generate_sql -> tick -> safety_check -> ...
    g.add_edge(START, "tick")
    g.add_conditional_edges("tick", route_after_tick, {
        "load_schema": "load_schema",
        "safety_check": "safety_check",
        END: END,
    })

    g.add_edge("load_schema", "generate_sql")
    g.add_edge("generate_sql", "tick")  # each new SQL increments steps & enforces limit

    g.add_conditional_edges("safety_check", route_after_safety, {
        "execute_sql": "execute_sql",
        "repair_sql": "repair_sql",
        END: END,
    })

    # Repair -> tick -> safety_check (loop)
    g.add_edge("repair_sql", "tick")

    g.add_conditional_edges("execute_sql", route_after_execute, {
        "repair_sql": "repair_sql",
        END: END,
    })

    return g.compile()


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
        model=env_str("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=env_float("OPENAI_TEMPERATURE", 0.0),
        max_repair_attempts=env_int("MAX_REPAIR_ATTEMPTS", 3),
        max_steps=env_int("MAX_STEPS", 10),
        max_same_sql_repeats=env_int("MAX_SAME_SQL_REPEATS", 1),
        max_rows=env_int("MAX_ROWS", 50),
        block_non_readonly_sql=env_bool("BLOCK_NON_READONLY_SQL", True),
        treat_refusal_result_as_error=env_bool("TREAT_REFUSAL_RESULT_AS_ERROR", True),
        ## *** ##
        instruction_path=env_str("INSTRUCTION_PATH", "INSTRUCTION.md"),
        ## *** ##
    )

    graph = make_graph(cfg)

    print(f"💽 Connected to SQLite: {cfg.db_path}")
    #print(f"🤖 Model: {cfg.model} (temp={cfg.temperature})")
    print(f"🧯 Limits: MAX_REPAIR_ATTEMPTS={cfg.max_repair_attempts}, MAX_STEPS={cfg.max_steps}, MAX_SAME_SQL_REPEATS={cfg.max_same_sql_repeats}")
    print("Type 'exit' to quit.\n")

    while True:
        q = input("Question> ").strip()
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break

        init_state: AgentState = {
            "messages": [],
            "question": q,
            "schema": "",
            "sql": "",
            "result": "",
            "error": "",
            "attempts": 0,
            "steps": 0,
            "seen_sql": [],
        }

        final_state = graph.invoke(init_state)

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
            print(f"(attempts={final_state.get('attempts', 0)}, steps={final_state.get('steps', 0)})")

        print("\n")


if __name__ == "__main__":
    main()