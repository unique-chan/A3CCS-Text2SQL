import os
from pathlib import Path
from dotenv import load_dotenv

import shutil

from dump_arma.db_ingest import dump_arma_into_sql


if __name__ == "__main__":
    load_dotenv()
    db_url = os.getenv("DB_URL", "sqlite:///outputs/arma_sql/state.db")
    json_dir = Path(os.getenv("JSON_DIR", "outputs/arma_json")).resolve()

    try:
        db_url_ = db_url.replace("sqlite:///", "").rsplit("/", 1)[0]
        os.makedirs(db_url_)
    except Exception as e:
        print(f'💽 {e}')
        answer = input(f'An existing Arma 3 metadata database already exists. Delete it and proceed? (Y/N)> ').strip()
        if answer.lower() == 'y':
            shutil.rmtree(db_url_)
            os.makedirs(db_url_)
        else:
            print(f'💽 Migrating Arma 3 metadata into SQLite3 database: Cancelled ❌')
            exit(0)

    dump_arma_into_sql(db_url, json_dir)