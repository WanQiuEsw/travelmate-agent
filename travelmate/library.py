"""Account-owned guide snapshots, independent of conversation checkpoints."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from uuid import uuid4

from fastapi import HTTPException

from travelmate.guide import get_version
from travelmate.preparation import overlay
from travelmate.public import public_data
from travelmate.budget import overlay as budget_overlay


def initialize(agent):
    with agent.checkpointer.cursor() as cur:
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS guide_library (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL,
                metadata TEXT NOT NULL, updated_at TEXT NOT NULL,
                latest INTEGER NOT NULL, favorite INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0, discarded_through INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS guide_library_user ON guide_library(user_id, deleted, updated_at);
            CREATE TABLE IF NOT EXISTS guide_versions (
                guide_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
                preparation TEXT, budget TEXT, PRIMARY KEY (guide_id, version)
            );
        ''')
        if 'budget' not in {row[1] for row in cur.execute('PRAGMA table_info(guide_versions)')}:
            cur.execute('ALTER TABLE guide_versions ADD COLUMN budget TEXT')


def sync_session(agent, session_id, user_id, state=None):
    if state is None:
        values = agent.get_state({'configurable': {'thread_id': session_id}}).values
        state = {**values.get('workflow', {}), 'evidence': values.get('evidence', {})}
    versions = state.get('versions', [])
    if not versions and state.get('plan') and state.get('status') in ('review', 'confirmed'):
        versions = [{'version': 1, 'plan': state['plan'],
                     'requirements': state.get('plan_requirements', state['requirements']),
                     'total': state.get('total')}]
    if not versions:
        return
    now = datetime.now(timezone.utc).isoformat()
    with agent.checkpointer.cursor() as cur, agent.checkpointer.conn:
        row = cur.execute('SELECT id, user_id, latest, deleted, discarded_through, metadata FROM guide_library WHERE session_id = ?',
                          (session_id,)).fetchone()
        if row and row[1] != user_id:
            return
        guide_id = row[0] if row else uuid4().hex
        latest = max(versions, key=lambda v: v['version'])
        if row and row[3] and latest['version'] <= row[2]:
            return
        req = latest['requirements']
        guide = latest.get('guide') or get_version({**state, 'versions': versions}, latest['version'])
        metadata = {key: req.get(key) for key in ('destination', 'days', 'travelers', 'start_date',
                                                 'budget', 'budget_scope', 'budget_currency')}
        metadata['title'] = guide['title']
        previous = json.loads(row[5]) if row else {}
        if previous.get('custom_title'):
            metadata.update(title=previous['custom_title'], custom_title=previous['custom_title'])
        updated = latest.get('saved_at') or (row and cur.execute(
            'SELECT updated_at FROM guide_library WHERE id = ?', (guide_id,)).fetchone()[0]) or now
        cur.execute('''INSERT INTO guide_library(id, session_id, user_id, metadata, updated_at, latest)
                       VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET
                       metadata=excluded.metadata, updated_at=excluded.updated_at,
                       latest=excluded.latest, deleted=0''',
                    (guide_id, session_id, user_id, json.dumps(public_data(metadata), ensure_ascii=False),
                     updated, latest['version']))
        for version in versions:
            number = version['version']
            if row and number <= row[4]:
                continue
            existing = cur.execute('SELECT 1 FROM guide_versions WHERE guide_id=? AND version=?',
                                   (guide_id, number)).fetchone()
            if not existing:
                snapshot = public_data(deepcopy(version))
                snapshot.setdefault('saved_at', now)
                snapshot.setdefault('evidence', {k: v for k, v in state.get('evidence', {}).items()
                                                if k in version.get('evidence_ids', [])})
                snapshot['guide'] = version.get('guide') or get_version(
                    {**state, 'versions': [snapshot]}, number)
                cur.execute('INSERT INTO guide_versions(guide_id, version, snapshot, preparation) VALUES (?, ?, ?, NULL)',
                            (guide_id, number, json.dumps(snapshot, ensure_ascii=False)))
            preparation = state.get('preparation_lists', {}).get(str(number))
            if preparation is not None:
                cur.execute('UPDATE guide_versions SET preparation=? WHERE guide_id=? AND version=?',
                            (json.dumps(preparation, ensure_ascii=False), guide_id, number))
            budget = state.get('budget_lists', {}).get(str(number))
            if budget is not None:
                cur.execute('UPDATE guide_versions SET budget=? WHERE guide_id=? AND version=?',
                            (json.dumps(budget, ensure_ascii=False), guide_id, number))


def migrate(agent, owners=None):
    seen = set()
    pending = []
    # shortcut: startup scans checkpoint history once; add a migration cursor if startup becomes slow.
    with closing(agent.checkpointer.list(None)) as checkpoints:
        for checkpoint in checkpoints:
            session_id = checkpoint.config['configurable']['thread_id']
            if session_id in seen:
                continue
            seen.add(session_id)
            if owners is not None and session_id not in owners:
                continue
            values = checkpoint.checkpoint.get('channel_values', {})
            state = {**values.get('workflow', {}), 'evidence': values.get('evidence', {})}
            pending.append((session_id, owners[session_id] if owners is not None else 'local', state))
    for session_id, user_id, state in pending:
        try:
            sync_session(agent, session_id, user_id, state)
        except (KeyError, TypeError, ValueError):
            logging.getLogger(__name__).warning('Skipped an incompatible historical guide during migration')


def owned(agent, guide_id, user_id):
    with agent.checkpointer.cursor() as cur:
        row = cur.execute('SELECT session_id, metadata, updated_at, latest, favorite FROM guide_library '
                          'WHERE id=? AND user_id=? AND deleted=0', (guide_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, '攻略不存在或已删除')
    return {**json.loads(row[1]), 'id': guide_id, 'session_id': row[0], 'updated_at': row[2],
            'latest': row[3], 'favorite': bool(row[4])}


def listing(agent, user_id):
    with agent.checkpointer.cursor() as cur:
        rows = cur.execute('SELECT id, metadata, updated_at, latest, favorite FROM guide_library '
                           'WHERE user_id=? AND deleted=0 ORDER BY updated_at DESC, id', (user_id,)).fetchall()
    return [{**json.loads(meta), 'id': key, 'updated_at': updated, 'latest': latest, 'favorite': bool(favorite)}
            for key, meta, updated, latest, favorite in rows]


def versions(agent, guide_id):
    with agent.checkpointer.cursor() as cur:
        rows = cur.execute('SELECT version, snapshot FROM guide_versions WHERE guide_id=? ORDER BY version DESC',
                           (guide_id,)).fetchall()
    return [{'version': number, 'saved_at': json.loads(snapshot).get('saved_at', '')} for number, snapshot in rows]


def load(agent, guide_id, number):
    with agent.checkpointer.cursor() as cur:
        row = cur.execute('SELECT snapshot, preparation, budget FROM guide_versions WHERE guide_id=? AND version=?',
                          (guide_id, number)).fetchone()
    if not row:
        raise HTTPException(404, '攻略版本不存在')
    snapshot = json.loads(row[0])
    guide = overlay(deepcopy(snapshot['guide']), json.loads(row[1]) if row[1] else None)
    return snapshot, budget_overlay(guide, json.loads(row[2]) if row[2] else None)


def remove(agent, guide_id):
    with agent.checkpointer.cursor() as cur, agent.checkpointer.conn:
        cur.execute('DELETE FROM guide_versions WHERE guide_id=?', (guide_id,))
        # Keep only a version watermark so historical checkpoints cannot resurrect a deleted guide.
        cur.execute("UPDATE guide_library SET deleted=1, discarded_through=latest, metadata='{}', favorite=0 WHERE id=?", (guide_id,))
