import json
import sys
import types
import datetime as dt
import pytest
import exam_pdf as E
import mooc as M


def test_pdf_exact_class_and_columns():
    headers=['Mã lớp thi','Mã HP','Tên học phần','Nhóm','Ngày thi','Kíp thi','Phòng thi']
    rows=[headers,['12','MI1111','Giải tích I','Kỹ thuật máy tính 04-K71','08.11.2026','8h10-8h50','D5-101'],
          ['13','IT1108','Lập trình','Kỹ thuật máy tính 03-K71','08.11.2026','Kíp 1','D5-102']]
    result=E.parse_tables([rows],'Kỹ Thuật Máy Tính 04 - K71',11)
    assert len(result)==1
    assert result[0]['ngay']=='2026-11-08' and result[0]['phong']=='D5-101'
    assert result[0]['source_page']==11


def test_pdf_invalid_matching_date_fails_closed():
    h=['Mã lớp thi','Mã HP','Tên học phần','Nhóm','Ngày thi','Kíp thi','Phòng thi']
    with pytest.raises(ValueError):
        E.parse_tables([[h,['12','MI1111','Toán','Class A','31.02.2026','Kíp 1','A']]],'Class A')


def test_pdf_dedup_and_fami_priority(tmp_path, monkeypatch):
    out=tmp_path/'pdf.json'; monkeypatch.setattr(E,'OUT',out)
    out.write_text(json.dumps({'exams':[dict(ma_hp='MI1111',ngay='2026-11-08',phong='B',kip='8h10',source_page=11)]}))
    rows=E.merge([dict(ma_hp='MI1111',ngay='2026-11-08',phong='A',kip='8h10')])
    assert len(rows)==1 and rows[0]['phong']=='A' and rows[0]['source_warning']


def test_pdf_failed_new_parse_retains_prior_schedule(tmp_path,monkeypatch):
    config=tmp_path/'cfg.json'; out=tmp_path/'out.json'; pdf=tmp_path/'LTGK.pdf'; pdf.write_bytes(b'bad')
    config.write_text(json.dumps(dict(class_name='A',sources=[dict(directory=str(tmp_path))])))
    out.write_text(json.dumps(dict(exams=[{'ma_hp':'MI1111'}])))
    monkeypatch.setattr(E,'CONFIG',config); monkeypatch.setattr(E,'OUT',out)
    monkeypatch.setattr(E,'extract',lambda *a: [])
    assert E.refresh()['ok'] is False
    assert json.loads(out.read_text())['exams']==[{'ma_hp':'MI1111'}]


class Request:
    def __init__(self, progress): self.progress=progress; self.paths=[]
    def get(self,url,timeout):
        self.paths.append(url)
        value=([dict(is_active=True,course_details=dict(course_id='course-v1:Org+IT2000+2026'))]
               if 'enrollment' in url else self.progress)
        return types.SimpleNamespace(ok=True,status=200,json=lambda: value)


def test_mooc_reads_assignments_without_teams():
    r=Request(dict(courseware_summary=[dict(display_name='Week',subsections=[dict(graded=True,
        display_name='Homework',due='2026-11-01T00:00:00Z',problem_scores=[dict(earned=1,possible=5)])])]))
    data=M.collect_api(r)
    assert data['ok'] and len(r.paths)==2
    item=next(iter(data['courses'].values()))['items'][0]
    assert item['earned']==1 and item.get('submitted') is not True


def test_mooc_partial_api_failure_never_overwrites(tmp_path,monkeypatch):
    p=tmp_path/'mooc.json'; p.write_text('{"courses":{"old":{}}}')
    monkeypatch.setattr(M,'OUT',p)
    data=M.collect_api(Request({'error':'403'}))
    assert not M.save_snapshot(data)['ok']
    assert json.loads(p.read_text())=={'courses':{'old':{}}}


def test_mooc_does_not_conflate_same_due_or_close_partial_score(tmp_path,monkeypatch):
    import deadlines as D, academic, mail_events
    due=(dt.datetime.now(M.TZ)+dt.timedelta(days=2)).isoformat()
    item=dict(name='Homework B',due=due,earned=1,possible=10,url=M.BASE+'/item-b')
    snap=dict(courses={'course-v1:Org+IT2000+2026':dict(items=[item])})
    p=tmp_path/'mooc.json'; p.write_text(json.dumps(snap)); monkeypatch.setattr(M,'OUT',p)
    monkeypatch.setattr(D,'_fetch',lambda post:[dict(course='IT2000',name='Homework A',due=due,status='Not started',id='a')])
    monkeypatch.setattr(D,'refresh',lambda post:None)
    created=[]; patched=[]
    fake=types.SimpleNamespace(courses=lambda:[{'code':'IT2000','id':'course'}], create=lambda db,props:created.append(props),patch=lambda *a:patched.append(a))
    monkeypatch.setattr(academic,'Notion',lambda post:fake)
    monkeypatch.setattr(mail_events,'load',lambda:{'events':{}})
    monkeypatch.setattr(mail_events,'save',lambda data:None)
    result=M.sync(None)
    assert len(created)==1 and not patched
    assert created[0]['Status']['status']['name']=='Not started'
    assert created[0]['Submission/Repo']['url']==M.BASE+'/item-b'


def test_mooc_url_cannot_leave_school():
    assert M.work_url({'url':'https://evil.invalid/'},'cid')==M.BASE+'/courses/cid/course/'
