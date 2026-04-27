import uuid

import pytest
from fastapi import HTTPException

from app.models.room import Room
from app.models.task import Task
from app.models.user import User, UserRole
from app.services import task_script_service


@pytest.mark.asyncio
async def test_propose_facilitator_update_sets_pending_proposal(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name='R1', created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(id=room.task_id, title='T1', created_by=uuid.uuid4(), scripts='old status')
    user = User(
        id=uuid.uuid4(),
        username='s1',
        password_hash='x',
        display_name='Student 1',
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    async def _fake_generate(_room_id):
        return {
            'current_status': 'analyzed problem',
            'next_goal': 'compare options',
            'change_reason': 'move to solution stage',
        }

    monkeypatch.setattr(task_script_service.task_service, 'get_task', _fake_get_task)
    monkeypatch.setattr(task_script_service, '_generate_facilitator_proposal', _fake_generate)

    result = await task_script_service.propose_facilitator_update(fake_db, room, user)

    assert result['current_status'] == 'old status'
    assert result['next_goal'] == ''
    assert result['pending_proposal']['agent_role'] == 'facilitator'
    assert result['pending_proposal']['next_goal'] == 'compare options'
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_confirm_pending_proposal_applies_with_editor_lock(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name='R1', created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(
        id=room.task_id,
        title='T1',
        created_by=uuid.uuid4(),
        scripts={
            'current_status': 'status A',
            'next_goal': 'goal A',
            'history': [],
            'pending_proposal': {
                'id': 'p-1',
                'agent_role': 'facilitator',
                'current_status': 'status B',
                'next_goal': 'goal B',
                'change_reason': 'need push',
            },
        },
    )
    user = User(
        id=uuid.uuid4(),
        username='s1',
        password_hash='x',
        display_name='Student 1',
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    async def _fake_get_lock_raw(_room_id):
        return {'user_id': str(user.id), 'proposal_id': 'p-1', 'lease_id': 'lease-1'}

    async def _fake_release_lock(_room_id, _current_user, _lease_id):
        return {'released': True}

    monkeypatch.setattr(task_script_service.task_service, 'get_task', _fake_get_task)
    monkeypatch.setattr(task_script_service, '_get_lock_raw', _fake_get_lock_raw)
    monkeypatch.setattr(task_script_service, 'release_task_script_lock', _fake_release_lock)

    result = await task_script_service.confirm_pending_proposal(
        fake_db,
        room,
        user,
        overrides={
            'current_status': 'status B edited',
            'next_goal': 'goal B edited',
            'student_feedback': 'let us verify assumptions first',
        },
        proposal_id='p-1',
        lease_id='lease-1',
    )

    assert result['pending_proposal'] is None
    assert result['current_status'] == 'status B edited'
    assert result['next_goal'] == 'goal B edited'
    assert len(result['history']) == 1
    assert result['history'][0]['id'] == 'p-1'
    assert result['history'][0]['confirmed_by'] == [str(user.id)]
    assert result['history'][0]['student_adjusted'] is True
    assert result['history'][0]['facilitator_suggested_current_status'] == 'status B'
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_confirm_pending_proposal_raises_when_missing_pending(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name='R1', created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(
        id=room.task_id,
        title='T1',
        created_by=uuid.uuid4(),
        scripts={'current_status': 'A', 'next_goal': 'B', 'history': [], 'pending_proposal': None},
    )
    user = User(
        id=uuid.uuid4(),
        username='s1',
        password_hash='x',
        display_name='Student 1',
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    monkeypatch.setattr(task_script_service.task_service, 'get_task', _fake_get_task)

    with pytest.raises(HTTPException) as exc:
        await task_script_service.confirm_pending_proposal(fake_db, room, user)

    assert exc.value.status_code == 400
    assert 'No pending proposal' in exc.value.detail
