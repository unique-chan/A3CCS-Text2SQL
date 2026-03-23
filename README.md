<h1 align="center">
💾 A3CCS-Text2SQL
</h1>

<h3 align="center">
🛠️ Text2SQL for handling metadata of Arma3
</h3>

<p align="center">
  <a href="#"><img alt="Python3.11" src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white"></a>
  <a href="#"><img alt="Arma 3" src="https://img.shields.io/badge/Game-Arma 3-green?logo=steam"></a>
</p>

### Note
- This code is originally designed for A3CCS (https://github.com/citizen135/A3CCS)

### Preliminaries 
- Local PC
  ~~~shell
  conda create -n text2sql python=3.11 -y
  conda activate text2sql
  pip install -r requirements.txt
  ~~~

- Remote PC for LLM
  ~~~shell
  conda create -n hugging python=3.11 -y
  conda activate hugging
  pip install -U huggingface_hub==1.6.0
  pip install -U vllm==0.17.0
  mkdirs mymodels
  huggingface-cli download openai/gpt-oss-20b --local-dir ./mymodels/gpt-oss-20b
  ~~~

- You may have to change `.env` or `prompts/*.md`


### Dump Arma3 metadata to SQLite3 (DB)
- In `outputs/`, we provide our toy examples.
  ~~~shell
  python test_dump_arma.py
  ~~~

### How to use? 
- Text2SQL

  ~~~python
  from text2sql_langgraph import run_text2sql_query
  resp = run_text2sql_query('현재 아군과 적군 사이 최단 거리 유닛 리스트 top-10을 열거해라!')
  if resp['ok']:
    print(resp['result'])
  else:
    print(resp['error'])
  ~~~

- [Tip] We provide wrapper functions around pre-written SQL queries for cases that are expected to be frequently requested. See `battle_query_api.ipynb` or (`.py`) for details.

  ~~~python
  from battle_query_api import *
  print(get_unit_count(side='b', damage_threshold=0.5))
  ~~~

  | alive_unit_count | initial_unit_count |
  |------------------|--------------------|
  | 83               | 88                 | 


### Test (Live demo)

- Remote LLM PC (Note: we use GPT OSS 20B)
  ~~~shell
  cd mymodels
  vllm serve ./gpt-oss-20b --host 0.0.0.0 --port 8000
  ~~~
  - Tip: The below commands should return "HTTP/1.1 200 OK" in your remote PC!
    ~~~shell
    curl -i http://127.0.0.1:8000/ping
    curl -i http://127.0.0.1:8000/v1/models
    ~~~

- Local PC (Just checking SQLite)

  ~~~shell
  sqlite3 outputs/arma_sql/state.db
  ~~~

  ~~~sql
  .header on
  .mode column  # Try .mode line
  
  select * from 'groups' limit 1;
  select * from 'units' limit 1;
  select * from 'vehicles' limit 1;
  select * from 'snapshots' limit 1;
  ~~~

- Local PC (Leveraging Text2SQL)
  ~~~shell
  python \text2sql_langgraph.py
  ~~~
