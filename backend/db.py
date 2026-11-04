"""
Database access: one PyMySQL connection per request, every query
parameterised, committed when the request succeeds and rolled back if not.
Swayam Shakya
"""

import json
import ssl
from pathlib import Path

import pymysql
from flask import current_app, g

from config import Config

JSON_COLUMNS = {"seasons", "occasions", "data", "breakdown"}


def make_ssl_context(ca_path=""):
    ctx = ssl.create_default_context(cafile=ca_path or None)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def connect(database=True):
    kwargs = dict(host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER, password=Config.DB_PASSWORD,
                  charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                  connect_timeout=10, read_timeout=60, write_timeout=60, init_command="SET time_zone = '+00:00'")
    if database:
        kwargs["database"] = Config.DB_NAME
    if Config.DB_SSL:
        kwargs["ssl"] = make_ssl_context(Config.DB_SSL_CA)
    return pymysql.connect(**kwargs)


def conn():
    if "db" not in g:
        g.db = connect()
    return g.db


def close(error=None):
    c = g.pop("db", None)
    if c is None:
        return
    try:
        if error is None and not getattr(g, "db_failed", False):
            c.commit()
        else:
            c.rollback()
    finally:
        c.close()


def _decode(row):
    if row is None:
        return None
    for k in JSON_COLUMNS & row.keys():
        if isinstance(row[k], str):          # JSON columns arrive as text; image blobs as bytes
            row[k] = json.loads(row[k])
    return row


def all_(sql, args=()):
    with conn().cursor() as cur:
        cur.execute(sql, args)
        return [_decode(r) for r in cur.fetchall()]


def one(sql, args=()):
    with conn().cursor() as cur:
        cur.execute(sql, args)
        return _decode(cur.fetchone())


def run(sql, args=()):
    """INSERT/UPDATE/DELETE. Returns lastrowid for inserts, else rowcount."""
    with conn().cursor() as cur:
        n = cur.execute(sql, args)
        return cur.lastrowid or n


def commit():
    conn().commit()


def as_json(v):
    return json.dumps(v, separators=(",", ":"))


def apply_schema(connection):
    sql = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
    # drop whole-line comments first, so a ";" or quote inside a comment can't split a statement
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    with connection.cursor() as cur:
        for s in sql.split(";"):
            body = s.strip()
            if body:
                cur.execute(body)
    connection.commit()
    return True
