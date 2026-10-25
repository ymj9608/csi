import json

import pytest

from coding_agent import private_files
from test_coding_worker import assert_private


def test_unicode_receipt_is_private_and_round_trips(tmp_path):
    target = tmp_path / 'receipt.json'
    value = {'summary': '\uc544\ud0a4\ud14d\ucc98 \ubd84\uc11d', 'source': 'print("\uc548\ub155")'}
    private_files.write_private(target, value)
    assert json.loads(target.read_text(encoding='utf-8')) == value
    assert_private(target)


def test_permission_failure_preserves_old_receipt_without_writing_secrets(tmp_path, monkeypatch):
    target = tmp_path / 'receipt.json'
    private_files.write_private(target, {'status': 'old'})
    def deny(path):
        assert path.read_bytes() == b''
        raise PermissionError('ACL setup failed')
    monkeypatch.setattr(private_files, 'restrict_private', deny)
    with pytest.raises(PermissionError):
        private_files.write_private(target, {'token': 'new-secret'})
    assert json.loads(target.read_text(encoding='utf-8')) == {'status': 'old'}
    assert list(tmp_path.iterdir()) == [target]
