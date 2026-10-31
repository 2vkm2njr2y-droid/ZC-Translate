
from app.backend.storage.db import Database


def test_settings_roundtrip(db: Database):
    db.set_settings({"theme": "dark", "target_lang": "ja"})
    stored = db.stored_settings()
    assert stored["theme"] == "dark"
    assert stored["target_lang"] == "ja"


def test_glossary_and_terms(db: Database):
    glossary = db.create_glossary("产品", "en", "zh", True)
    assert glossary["id"]
    term = db.upsert_term(glossary["id"], "cache", "缓存", False, "技术术语")
    assert term["target"] == "缓存"
    updated = db.upsert_term(glossary["id"], "cache", "高速缓存", True, "覆盖")
    assert updated["target"] == "高速缓存"
    assert len(db.list_terms(glossary["id"])) == 1
    assert db.list_glossaries()[0]["term_count"] == 1
    db.delete_glossary(glossary["id"])
    assert db.list_terms(glossary["id"]) == []


def test_csv_import_export(db: Database):
    glossary = db.create_glossary("test", "en", "zh")
    csv_text = "\ufeffsource,target,case_sensitive,note\ncache,缓存,0,技术\nAPI,接口,1,缩写\n"
    result = db.import_terms(glossary["id"], csv_text)
    assert result == {"added": 2, "updated": 0, "skipped": 0}
    exported = db.export_terms_csv(glossary["id"])
    assert "cache" in exported and "缓存" in exported


def test_tm(db: Database):
    db.put_tm("en", "zh", "balanced", "v1", "h", "key", "缓存")
    hit = db.get_tm("en", "zh", "balanced", "v1", "h", "key")
    assert hit["target_text"] == "缓存"
    assert db.tm_stats()["hits"] == 1
    assert db.get_tm("en", "zh", "balanced", "v1", "other", "key") is None
    db.clear_tm()
    assert db.tm_stats()["entries"] == 0


def test_history(db: Database):
    history_id = db.add_history(
        kind="text", src_lang="en", detected_lang="en", tgt_lang="zh",
        profile="balanced", device="NPU", source_text="hello", result_text="你好",
        status="completed", duration_ms=100, warnings=["test"],
    )
    item = db.get_history(history_id)
    assert item["result_text"] == "你好"
    listing = db.list_history("hello")
    assert listing["total"] == 1
    assert listing["items"][0]["warning_count"] == 1
    db.delete_history(history_id)
    assert db.get_history(history_id) is None
