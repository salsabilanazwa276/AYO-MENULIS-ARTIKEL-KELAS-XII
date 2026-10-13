"""Small DB-API bridge for the application's fixed SQL statements."""
import re
from functools import lru_cache
from psycopg_pool import ConnectionPool
import psycopg
from psycopg.rows import dict_row

class Row(dict):
    def __getitem__(self,key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Result:
    def __init__(self,cursor): self.cursor=cursor
    def fetchone(self):
        r=self.cursor.fetchone()
        return Row(r) if r is not None else None
    def __iter__(self):
        return (Row(r) for r in self.cursor)

def postgres_sql(sql):
    sql=sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
    if sql=='BEGIN IMMEDIATE': return 'SELECT 1' # psycopg manages the transaction.
    sql=sql.replace("julianday(created)<julianday('now')-10.0/1440", "created::timestamptz < CURRENT_TIMESTAMP - INTERVAL '10 minutes'")
    ignore='INSERT OR IGNORE INTO' in sql
    sql=sql.replace('INSERT OR IGNORE INTO','INSERT INTO')
    sql=sql.replace('?', '%s')
    if ignore: sql=sql.rstrip(';')+' ON CONFLICT DO NOTHING'
    return sql

@lru_cache(maxsize=2)
def connection_pool(url):
    return ConnectionPool(url, min_size=0, max_size=4, open=True, timeout=15,
        max_idle=60, max_lifetime=600, reconnect_timeout=15,
        check=ConnectionPool.check_connection,
        kwargs={'row_factory':dict_row,'connect_timeout':10,'sslmode':'require',
                'prepare_threshold':None})

class PostgresConnection:
    def __init__(self,url):
        self._context=connection_pool(url).connection()
        self.raw=None
    def execute(self,sql,params=()):
        return Result(self.raw.execute(postgres_sql(sql),params))
    def executescript(self,script):
        # Serialize first-run schema migration across simultaneous new sessions.
        self.raw.execute('SELECT pg_advisory_xact_lock(842197320)')
        for statement in script.split(';'):
            if statement.strip(): self.execute(statement.strip())
    def __enter__(self):
        self.raw=self._context.__enter__()
        return self
    def __exit__(self,typ,value,tb):
        return self._context.__exit__(typ,value,tb)
