# -*- coding: utf-8 -*-
"""(v1.00.24, D-1) uc_state: ghi nguyên tử + .bak; file trạng thái bị cụt (tắt máy giữa lúc ghi) -> đọc .bak, không lặng lẽ về rỗng."""
import uc_state


def test_truncated_file_falls_back_to_bak(tmp_path, monkeypatch):
    monkeypatch.setattr(uc_state, 'ERRLOG', tmp_path / 'state_errors.log')
    f = tmp_path / 'events.json'
    uc_state.save_json(f, {'processed': ['a']})
    uc_state.save_json(f, {'processed': ['a', 'b']})
    f.write_text('{"processed": ["a", "b"], "eve', encoding='utf-8')   # cụt giữa chừng
    assert uc_state.load_json(f, {'processed': []}) == {'processed': ['a']}
    assert 'events.json' in (tmp_path / 'state_errors.log').read_text(encoding='utf-8')
    assert not list(tmp_path.glob('*.tmp'))


def test_missing_file_returns_default(tmp_path):
    assert uc_state.load_json(tmp_path / 'none.json', {'x': 1}) == {'x': 1}
