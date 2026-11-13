"""标签组与作者的增删改，以及引用约束。"""

from __future__ import annotations

from app.ui.manager.api import ManagerApi


def make_api(tmp_path) -> ManagerApi:
    return ManagerApi(config_dir=tmp_path)


def group_uid(api, name: str) -> str:
    for group in api.library.tag_groups.values():
        if group.name == name:
            return group.uid
    raise AssertionError(f"没有找到标签组：{name}")


def author_uid(api, name: str) -> str:
    for author in api.library.authors.values():
        if author.name == name:
            return author.uid
    raise AssertionError(f"没有找到作者：{name}")


def test_create_tag_group_and_add_tags(tmp_path):
    api = make_api(tmp_path)

    state = api.create_tag_group("风格", compulsory=True, unique=True)
    uid = group_uid(api, "风格")

    assert state["selection"] == {"kind": "tag_group", "uid": uid}
    assert state["section"] == "tags"

    api.add_tag(uid, "古典")
    state = api.add_tag(uid, "民谣")

    payload = next(item for item in state["library"]["tag_groups"] if item["uid"] == uid)
    assert [tag["name"] for tag in payload["tags"]] == ["古典", "民谣"]
    assert payload["compulsory"] is True
    assert payload["unique"] is True


def test_duplicate_tag_group_is_rejected(tmp_path):
    api = make_api(tmp_path)
    api.create_tag_group("风格")

    state = api.create_tag_group("风格")

    assert state["ok"] is False
    assert "风格" in state["message"]


def test_duplicate_tag_name_in_group_is_rejected(tmp_path):
    api = make_api(tmp_path)
    api.create_tag_group("风格")
    uid = group_uid(api, "风格")
    api.add_tag(uid, "古典")

    state = api.add_tag(uid, "古典")

    assert state["ok"] is False


def test_rename_and_remove_tag_updates_songs(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.create_tag_group("风格")
    uid = group_uid(api, "风格")
    api.add_tag(uid, "古典")
    tag_uid = api.library.tag_groups[uid].tags[0].uid

    music = music_factory("a", tags=[tag_uid])
    api.library.upsert_music(music)
    api.library.save()

    api.rename_tag(uid, tag_uid, "Classical")
    assert api.library.all_tags()[tag_uid].name == "Classical"

    api.remove_tag(uid, tag_uid)
    assert api.library.musics[music.md5].tags == []
    assert api.library.all_tags() == {}


def test_delete_tag_group_is_blocked_when_used(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.create_tag_group("风格")
    uid = group_uid(api, "风格")
    api.add_tag(uid, "古典")
    tag_uid = api.library.tag_groups[uid].tags[0].uid
    api.library.upsert_music(music_factory("a", tags=[tag_uid]))
    api.library.save()

    blocked = api.delete_tag_group(uid)

    assert blocked["ok"] is False
    assert "Song a" in blocked["message"]
    assert uid in api.library.tag_groups

    forced = api.delete_tag_group(uid, force=True)

    assert forced["ok"] is True
    assert uid not in api.library.tag_groups
    assert api.library.musics["a" * 32].tags == []


def test_tag_group_payload_counts_usage(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.create_tag_group("风格")
    uid = group_uid(api, "风格")
    api.add_tag(uid, "古典")
    tag_uid = api.library.tag_groups[uid].tags[0].uid
    api.library.upsert_music(music_factory("a", tags=[tag_uid]))
    api.library.upsert_music(music_factory("b", tags=[tag_uid]))
    api.library.save()

    payload = next(item for item in api.get_state()["library"]["tag_groups"] if item["uid"] == uid)

    assert payload["count"] == 2
    assert payload["tags"][0]["count"] == 2


def test_author_update_and_delete(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.create_author("Einaudi")
    uid = author_uid(api, "Einaudi")
    api.library.upsert_music(music_factory("a", authors=[uid]))
    api.library.save()

    state = api.update_author(uid, {"name": "Ludovico Einaudi", "description": "意大利钢琴家"})
    assert state["ok"] is True
    assert api.library.authors[uid].name == "Ludovico Einaudi"
    assert api.library.authors[uid].description == "意大利钢琴家"

    blocked = api.delete_author(uid)
    assert blocked["ok"] is False
    assert uid in api.library.authors

    api.delete_author(uid, force=True)
    assert uid not in api.library.authors
    assert api.library.musics["a" * 32].authors == []


def test_author_duplicate_name_is_rejected(tmp_path):
    api = make_api(tmp_path)
    api.create_author("A")
    api.create_author("B")
    uid_b = author_uid(api, "B")

    state = api.update_author(uid_b, {"name": "A"})

    assert state["ok"] is False
    assert api.library.authors[uid_b].name == "B"


def test_author_order_can_be_reordered(tmp_path):
    api = make_api(tmp_path)
    for name in ("甲", "乙", "丙"):
        api.create_author(name)
    order = [author_uid(api, name) for name in ("甲", "乙", "丙")]

    api.reorder_authors([order[2], order[0], order[1]])

    assert list(api.library.authors) == [order[2], order[0], order[1]]

    api.move_author(order[1], -1)
    assert list(api.library.authors) == [order[2], order[1], order[0]]


def test_select_item_switches_section(tmp_path):
    api = make_api(tmp_path)
    api.create_tag_group("风格")
    api.create_author("某人")
    group = group_uid(api, "风格")
    author = author_uid(api, "某人")

    assert api.select_item("tag_group", group)["section"] == "tags"
    assert api.select_item("author", author)["section"] == "authors"


def test_unique_violation_is_reported(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.create_tag_group("风格", unique=True)
    uid = group_uid(api, "风格")
    api.add_tag(uid, "古典")
    api.add_tag(uid, "流行")
    tags = [tag.uid for tag in api.library.tag_groups[uid].tags]
    api.library.upsert_music(music_factory("a", tags=tags))
    api.library.save()

    assert api.library.tag_violations() == ["a" * 32]

    report = api.run_integrity()
    section = next(item for item in report["sections"] if item["key"] == "tag_issue")
    assert "只能选一个" in section["items"][0]
