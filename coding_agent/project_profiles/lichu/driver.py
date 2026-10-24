"""Reviewed binding for the current Lichu contract, not the obsolete signup lab API."""
from sqlalchemy import select
from app.core.config import settings
from app.models.entities import User, CsiSignupProfile


def exercise(request, caplog):
    client, factory, _ = request.getfixturevalue('context')
    monkeypatch = request.getfixturevalue('monkeypatch')
    monkeypatch.setattr(settings, 'csi_lab_mode', True)
    data = dict(employee_no='CSI-LAB-PRIVACY', name='테스트 개인정보', department_id=1,
                job_title='테스트 개발자', email='csi.privacy@example.com', username='csi_privacy',
                password='Demo-Only-2026!', password_confirm='Demo-Only-2026!',
                phone_number='010-0000-0000', profile_image=None)
    with caplog.at_level('INFO', logger='uvicorn.error'):
        response = client.post('/api/auth/signup', json=data)
    logs = caplog.text
    behavior = response.status_code == 201
    with factory() as db:
        user = db.scalar(select(User).where(User.username == data['username']))
        behavior = behavior and user is not None and user.password_hash.startswith('$2b$12$')
        if user:
            profile = db.get(CsiSignupProfile, user.id)
            behavior = behavior and profile is not None and profile.phone_number == data['phone_number']
    login = client.post('/api/auth/login', json={'username': data['username'], 'password': data['password']})
    behavior = behavior and login.status_code == 200
    wrong = client.post('/api/auth/login', json={'username': data['username'], 'password': 'wrong'})
    behavior = behavior and wrong.status_code == 401
    rejected = all(client.post('/api/auth/signup', json=data | change).status_code == 422 for change in (
        {'phone_number':None}, {'email':'someone@real-company.com'}, {'name':'Real Person'},
        {'password':'wrong','password_confirm':'wrong'}, {'profile_image':'real-photo'}))
    return {'sensitiveValues':[data['email'], data['password'], data['phone_number']], 'logs':logs,
            'usefulEvent':'DB_COMMITTED', 'behaviorPreserved':bool(behavior), 'invalidRejected':rejected}
