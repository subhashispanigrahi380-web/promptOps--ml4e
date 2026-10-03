import sqlite3
from typing import Dict, Any, Optional, List
import json
from pydantic import BaseModel

class PromptVersion(BaseModel):
    id: str
    name: str
    version: int
    template: str
    description: Optional[str] = None
    schema_def: Optional[Dict[str, Any]] = None

class PromptRegistry:
    def __init__(self, db_path: str = "registry.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT,
                    name TEXT,
                    version INTEGER,
                    template TEXT,
                    description TEXT,
                    schema_def TEXT,
                    PRIMARY KEY (name, version)
                )
            ''')
            conn.commit()

    def add_prompt(self, name: str, template: str, description: str = "", schema_def: Optional[Dict[str, Any]] = None) -> PromptVersion:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM prompts WHERE name = ?", (name,))
            row = cur.fetchone()
            version = (row[0] or 0) + 1
            
            prompt_id = f"{name}_v{version}"
            
            cur.execute('''
                INSERT INTO prompts (id, name, version, template, description, schema_def)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (prompt_id, name, version, template, description, json.dumps(schema_def) if schema_def else None))
            conn.commit()
            
            return PromptVersion(
                id=prompt_id,
                name=name,
                version=version,
                template=template,
                description=description,
                schema_def=schema_def
            )

    def get_prompt(self, name: str, version: Optional[int] = None) -> Optional[PromptVersion]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            if version is not None:
                cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts WHERE name = ? AND version = ?", (name, version))
            else:
                cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts WHERE name = ? ORDER BY version DESC LIMIT 1", (name,))
            
            row = cur.fetchone()
            if not row:
                return None
                
            return PromptVersion(
                id=row[0],
                name=row[1],
                version=row[2],
                template=row[3],
                description=row[4],
                schema_def=json.loads(row[5]) if row[5] else None
            )
