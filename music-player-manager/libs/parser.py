import hashlib
import json
import pathlib
import random
import shutil
import time

from libs import config
from libs import log
from libs import music_process
from libs import utils

# 全局数据容器
music_files = {}  # uid -> MusicFile
authors = {}  # uid -> Author
tag_groups = {}  # uid -> TagGroup
tags = {}  # uid -> Tag
musics = {}  # uid -> Music
playlists = {}  # uid -> Playlist

# 已分配的随机 UID 集合，避免碰撞（不包含音乐 MD5）
used_uids = set()


# 配置文件蓝图
def uid_validator(uid):
    if len(uid) != 32:
        raise Exception("uid 不符合 md5 规范")
    hex_chars = set("0123456789abcdef")
    for char in uid:
        if char not in hex_chars:
            raise Exception("uid 不符合 md5 规范")


def music_file_validator(item):
    uid = item["uid"]
    path = item["path"]

    extensions = ['m4a', 'mp3']
    valid_path = [f"assets\\music\\{uid}.{extension}" for extension in extensions]
    if not path in valid_path:
        raise Exception("uid 和 path 不符")


def playlist_validator(item):
    mode = item["mode"]
    if mode == "simple" and not ("list" in item):
        raise Exception("simple 播放列表中必须含有 list 字段")
    if mode == "conditions" and not ("conditions" in item):
        raise Exception("conditions 播放列表中必须含有 conditions 字段")


author_schema = {
    "type": list,
    "items": {
        "type": dict,
        "required": ["uid", "name"],
        "properties": {
            "uid": {"type": str, "validator": uid_validator},
            "name": {"type": str, "min_length": 1},
            "description": {"type": str}
        }
    }
}

tag_group_schema = {
    "type": list,
    "items": {
        "type": dict,
        "required": ["uid", "name", "compulsory", "unique", "tags"],
        "properties": {
            "uid": {"type": str, "validator": uid_validator},
            "name": {"type": str, "min_length": 1},
            "compulsory": {"type": bool},
            "unique": {"type": bool},
            "tags": {
                "type": list,
                "min_length": 1,
                "items": {
                    "type": dict,
                    "required": ["uid", "name"],
                    "properties": {
                        "uid": {"type": str, "validator": uid_validator},
                        "name": {"type": str, "min_length": 1}
                    }
                }
            }
        }
    }
}

music_file_schema = {
    "type": list,
    "items": {
        "type": dict,
        "required": ["uid", "path", "created_at"],
        "validator": music_file_validator,
        "properties": {
            "uid": {"type": str, "validator": uid_validator},
            "path": {"type": str},
            "created_at": {"type": int}
        }
    }
}

music_schema = {
    "type": list,
    "items": {
        "type": dict,
        "required": ["uid", "names", "authors", "files", "tags"],
        "properties": {
            "uid": {"type": str, "validator": uid_validator},
            "names": {"type": list, "min_length": 1, "items": {"type": str, "min_length": 1}},
            "authors": {"type": list, "min_length": 1, "items": {"type": str, "validator": uid_validator}},
            "files": {"type": list, "min_length": 1, "items": {"type": str, "validator": uid_validator}},
            "tags": {"type": list, "items": {"type": str, "validator": uid_validator}}
        }
    }
}

playlist_schema = {
    "type": list,
    "items": {
        "type": dict,
        "required": ["uid", "name", "mode"],
        "validator": playlist_validator,
        "properties": {
            "uid": {"type": str, "validator": uid_validator},
            "name": {"type": str, "min_length": 1},
            "mode": {"type": str, "allowed_value": ["simple", "conditions"]},
            "list": {"type": list, "min_length": 1, "items": {"type": str, "validator": uid_validator}},
            "conditions": {
                "type": list,
                "items": {
                    "type": dict,
                    "required": ["mode", "filter"],
                    "properties": {
                        "mode": {"type": str, "allowed_value": ["include", "exclude"]},
                        "filter": {"type": str, "allowed_value": ["all", "music", "playlist", "tag", "author"]},
                        "list": {"type": list, "min_length": 1, "items": {"type": str, "validator": uid_validator}}
                    }
                }
            }
        }
    }
}


class Author:
    def __init__(self, uid, name, description=None):
        self.uid = uid
        self.name = name
        self.description = description if description is not None else ""

    def to_dict(self):
        return_dict = {"uid": self.uid, "name": self.name}
        if self.description:
            return_dict["description"] = self.description
        return return_dict


class Tag:
    def __init__(self, uid, name, group):
        self.uid = uid
        self.name = name
        self.group = group

    def to_dict(self):
        return {"uid": self.uid, "name": self.name}


class TagGroup:
    def __init__(self, uid, name, compulsory, unique, tags_):
        self.uid = uid
        self.name = name
        self.compulsory = compulsory
        self.unique = unique
        self.tags = tags_  # 包含 Tag 对象的列表

    def to_dict(self):
        return {
            "uid": self.uid,
            "name": self.name,
            "compulsory": self.compulsory,
            "unique": self.unique,
            "tags": [tag.to_dict() for tag in self.tags]
        }


class MusicFile:
    def __init__(self, uid, path, created_at):
        self.uid = uid
        self.path = path
        self.created_at = created_at  # 以秒计数的导入时间

    def to_dict(self):
        return {"uid": self.uid, "path": self.path, "created_at": self.created_at}


class Music:
    def __init__(self, uid, names, music_authors, files, tags_):
        self.uid = uid
        self.names = names  # 包含字符串的列表
        self.authors = music_authors  # 包含作者 UID 的列表
        self.files = files  # 包含音乐文件 UID（MD5）的列表
        self.tags = tags_  # 包含标签 UID 的列表

    def to_dict(self):
        return {"uid": self.uid, "names": self.names, "authors": self.authors, "files": self.files, "tags": self.tags}


class Playlist:
    def __init__(self, uid, name, mode, data):
        self.uid = uid
        self.name = name
        self.mode = mode  # 字符串 simple 或 conditions
        self.data = data  # 若 mode 为 simple，则为音乐 UID 的列表；conditions，则为包含条件字典的列表

    def to_dict(self):
        return_dict = {"uid": self.uid, "name": self.name, "mode": self.mode}
        if self.mode == "simple":
            return_dict["list"] = self.data
        elif self.mode == "conditions":
            return_dict["conditions"] = self.data
        return return_dict


def uid_generate():
    """生成唯一随机 UID，确保不与已有 UID 重复"""
    global used_uids
    while True:
        combined = str(time.time() * 1000000) + str(random.randint(1, 1000000))
        new_uid = hashlib.md5(combined.encode()).hexdigest()
        if new_uid not in used_uids:
            used_uids.add(new_uid)
            return new_uid


def uid_register(uid):
    """加载时，将 UID 注册到集合中"""
    global used_uids
    used_uids.add(uid)


def file_load():
    """读取全局数据"""
    global authors, tag_groups, tags, music_files, musics, playlists, used_uids
    base_config = pathlib.Path("config")
    author_path = base_config / "author.json"
    tag_group_path = base_config / "tag_group.json"
    music_file_path = base_config / "music_file.json"
    music_path = base_config / "music.json"
    playlist_path = base_config / "playlist.json"

    error_messages = []  # 存储错误信息

    # 读取作者
    try:
        raw_authors = config.read(author_path, author_schema)
        for raw_author in raw_authors:
            uid = raw_author["uid"]
            uid_register(uid)
            authors[uid] = Author(uid, raw_author["name"], raw_author.get("description"))
        log.write("已加载作者数据", 3)
    except Exception as e:
        authors.clear()
        err_msg = f"加载作者数据失败：{e}"
        log.write(err_msg, 1)
        error_messages.append(err_msg)

    # 读取标签组
    try:
        raw_tag_groups = config.read(tag_group_path, tag_group_schema)
        for raw_tag_group in raw_tag_groups:
            uid = raw_tag_group["uid"]
            uid_register(uid)
            tag_group = TagGroup(uid, raw_tag_group["name"], raw_tag_group["compulsory"], raw_tag_group["unique"], [])
            tags_ = []
            for raw_tag in raw_tag_group["tags"]:
                tag_uid = raw_tag["uid"]
                uid_register(tag_uid)
                tag = Tag(tag_uid, raw_tag["name"], tag_group)
                tags_.append(tag)
                tags[tag_uid] = tag
            tag_group.tags = tags_
            tag_groups[uid] = tag_group
        log.write("已加载标签数据", 3)
    except Exception as e:
        tag_groups.clear()
        err_msg = f"加载标签数据失败：{e}"
        log.write(err_msg, 1)
        error_messages.append(err_msg)

    # 读取音乐文件
    try:
        raw_music_files = config.read(music_file_path, music_file_schema)
        for raw_music_file in raw_music_files:
            # 音乐文件 UID 是文件 MD5，由于其不可控性，不加入 UID 集合
            uid = raw_music_file["uid"]
            music_files[uid] = MusicFile(uid, raw_music_file["path"], raw_music_file["created_at"])
        log.write("已加载音乐文件数据", 3)
    except Exception as e:
        music_files.clear()
        err_msg = f"加载音乐文件数据失败：{e}"
        log.write(err_msg, 1)
        error_messages.append(err_msg)

    # 读取歌曲
    try:
        raw_music = config.read(music_path, music_schema)
        for raw_music in raw_music:
            uid = raw_music["uid"]
            uid_register(uid)
            musics[uid] = Music(uid, raw_music["names"], raw_music["authors"], raw_music["files"], raw_music["tags"])
        log.write("已加载歌曲数据", 3)
    except Exception as e:
        musics.clear()
        err_msg = f"加载歌曲数据失败：{e}"
        log.write(err_msg, 1)
        error_messages.append(err_msg)

    # 读取播放列表
    try:
        raw_playlists = config.read(playlist_path, playlist_schema)
        for raw_playlist in raw_playlists:
            uid = raw_playlist["uid"]
            uid_register(uid)
            data = raw_playlist.get("list") or raw_playlist.get("conditions")
            playlists[uid] = Playlist(uid, raw_playlist["name"], raw_playlist["mode"], data)
        log.write("已加载播放列表数据", 3)
    except Exception as e:
        playlists.clear()
        err_msg = f"加载播放列表数据失败：{e}"
        log.write(err_msg, 1)
        error_messages.append(err_msg)

    return "\n".join(error_messages)


def file_save():
    """保存全局数据"""

    def save_json(json_path, json_content):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_content, f, ensure_ascii=False, indent=4)

    # 将所有全局数据保存回 config 目录中的文件
    base_config = pathlib.Path("config")
    base_config.mkdir(parents=True, exist_ok=True)
    save_json(base_config / "author.json", [author.to_dict() for author in authors.values()])
    save_json(base_config / "tag_group.json", [tag_group.to_dict() for tag_group in tag_groups.values()])
    save_json(base_config / "music_file.json", [music_file.to_dict() for music_file in music_files.values()])
    save_json(base_config / "music.json", [music.to_dict() for music in musics.values()])
    save_json(base_config / "playlist.json", [playlist.to_dict() for playlist in playlists.values()])

    log.write("所有配置文件已保存", 3)


def resolve_playlist(playlist_uid, visited=None):
    """解析播放列表，返回歌曲 UID 列表"""
    playlist = playlists[playlist_uid]

    if visited is None:
        visited = set()
    elif playlist_uid in visited:
        raise Exception(f"播放列表循环引用：{playlist.name}（{playlist_uid}）")
    visited.add(playlist_uid)

    # simple 模式的播放列表，直接返回值
    if playlist.mode == "simple":
        return playlist.data

    # conditions 模式的播放列表，进一步解析
    result = set()
    all_music_uids = set(musics.keys())

    for condition in playlist.data:
        mode = condition["mode"]
        filter_type = condition["filter"]
        current = set()
        if filter_type == "all":
            current = all_music_uids
        else:
            if not "list" in condition:
                raise Exception(f"条件模式播放列表格式错误：{playlist.name}（{playlist_uid}）")
            uids = condition["list"]
            if filter_type == "music":
                for music_uid in uids:
                    if music_uid in musics:
                        current.add(music_uid)
            elif filter_type == "playlist":
                for playlist_uid in uids:
                    sub_list = resolve_playlist(playlist_uid, visited.copy())
                    current.update(sub_list)
            elif filter_type == "tag":
                for music in musics.values():
                    if any(tag_uid in uids for tag_uid in music.tags):
                        current.add(music.uid)
            elif filter_type == "author":
                for music in musics.values():
                    if any(author_uid in uids for author_uid in music.authors):
                        current.add(music.uid)

        if mode == "include":
            result.update(current)
        else:
            result = result - current

    return sorted(result)


def check_integrity(if_check_md5):
    """执行完整性检查，返回包含所有错误的字符串"""
    errors = []

    # 检查 assets/music 目录下的没有被 music_file 收录的文件
    music_dir = pathlib.Path("assets/music")
    if music_dir.exists():
        for file in music_dir.iterdir():
            if file.is_file() and file.suffix.lower() in (".mp3", ".m4a"):
                uid = file.stem
                if uid not in music_files:
                    errors.append(f"音乐文件未被收录：{file}")
    else:
        errors.append("assets/music 目录不存在")

    # 检查 music_file 中的记录
    for music_file in music_files.values():
        file_path = pathlib.Path(music_file.path)
        if not file_path.exists():
            errors.append(f"音乐文件丢失：{music_file.path}（音乐文件 UID：{music_file.uid}）")
            continue
        if file_path.stem != music_file.uid:
            errors.append(f"音乐文件 UID 与文件名不符：UID 为 {music_file.uid}，文件为 {music_file.path}")
            continue
        if if_check_md5:
            actual_md5 = music_process.calculate_md5(file_path)
            if actual_md5 != music_file.uid:
                errors.append(f"音乐文件 MD5 不匹配：{music_file.path}（期望：{music_file.md5}，实际：{actual_md5}）")

    # 检查歌曲
    all_tag_uids = {tag.uid for tag_group in tag_groups.values() for tag in tag_group.tags}
    for music in musics.values():
        music_display = f"歌曲 {music.names[0]}（{music.uid}）"
        for author_uid in music.authors:
            if not author_uid in authors:
                errors.append(f"{music_display}引用了不存在的作者：{author_uid}")
        for uid in music.files:
            if uid not in music_files:
                errors.append(f"{music_display}引用了不存在的音乐文件：{uid}")
        for tag_uid in music.tags:
            if tag_uid not in all_tag_uids:
                errors.append(f"{music_display}引用了不存在的标签：{tag_uid}")
        for tag_group in tag_groups.values():
            tags_ = {tag.uid for tag in tag_group.tags}
            selected_in_group = [uid for uid in music.tags if uid in tags_]
            count = len(selected_in_group)
            if tag_group.compulsory and tag_group.unique and count != 1:
                errors.append(f"{music_display}标签组 {tag_group.name}（{tag_group.uid}）要求恰好选择一个标签。")
            if tag_group.compulsory and not tag_group.unique and count < 1:
                errors.append(f"{music_display}标签组 {tag_group.name}（{tag_group.uid}）要求至少选择一个标签。")
            if not tag_group.compulsory and tag_group.unique and count > 1:
                errors.append(f"{music_display}标签组 {tag_group.name}（{tag_group.uid}）要求最多选择一个标签。")

    # 检查播放列表
    for playlist in playlists.values():
        if playlist.mode == "simple":
            for music_uid in playlist.data:
                if music_uid not in musics:
                    errors.append(f"播放列表 {playlist.name}（{playlist.uid}）引用了不存在的歌曲：{music_uid}")
        else:
            try:
                resolve_playlist(playlist.uid)
            except Exception as e:
                errors.append(f"播放列表 {playlist.name}（{playlist.uid}）解析错误：{e}")

    return "未发现任何问题" if not errors else "\n".join(errors)


def import_music_file(source_path, ignore_exists=True):
    """导入音乐文件，包括：检查音乐文件合法性、复制临时文件、创建 music_file 记录、返回 MusicFile 对象或抛出异常"""
    try:
        temp_path = music_process.validate_music(source_path)
        md5 = temp_path.stem
        ext = temp_path.suffix
        target_dir = pathlib.Path("assets") / "music"
        target_path = target_dir / f"{md5}{ext}"

        if target_path.exists():
            if ignore_exists:
                target_path.unlink()
                del music_files[md5]
                log.write(f"音乐文件已存在：{md5}，进行文件替换", 2)
            else:
                raise Exception(f"音乐文件已存在：{md5}")

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp_path, target_path)
        if temp_path.exists():
            temp_path.unlink()

        # 创建记录，设置导入时间
        music_file = MusicFile(md5, str(target_path), int(time.time()))
        music_files[md5] = music_file
        log.write(f"导入音乐文件成功：{md5}", 3)
        return music_file
    except Exception as e:
        err_msg = f"导入音乐文件失败：{e}"
        log.write(err_msg, 1)
        raise Exception(err_msg)


def check_dependencies(obj):
    """检查删除指定对象是否安全"""
    used_in = []
    data_type = utils.get_type(obj)
    uid = obj.uid
    if data_type == "author":
        for music in musics.values():
            if uid in music.authors:
                used_in.append(music.names[0])
        if used_in:
            return False, "该作者被以下歌曲引用：\n" + "\n".join(used_in)
        return True, ""
    elif data_type == "tag_group":
        tags_ = {tag.uid for tag in obj.tags}
        for music in musics.values():
            if any(tag_uid in tags_ for tag_uid in music.tags):
                used_in.append(music.names[0])
        if used_in:
            return False, "该标签组被以下歌曲引用：\n" + "\n".join(used_in)
        return True, ""
    elif data_type == "tag":
        for music in musics.values():
            if uid in music.tags:
                used_in.append(music.names[0])
        if used_in:
            return False, "该标签被以下歌曲引用：\n" + "\n".join(used_in)
        return True, ""
    elif data_type == "music":
        for playlist in playlists.values():
            if playlist.mode == "simple":
                if uid in playlist.data:
                    used_in.append(playlist.name)
            else:
                try:
                    resolved = resolve_playlist(playlist.uid)
                    if uid in resolved:
                        used_in.append(playlist.name)
                except Exception as e:
                    log.write(f"检查对象依赖性时发现存在播放列表列表错误：{e}", 2)
        if used_in:
            return False, "该歌曲被以下播放列表引用：\n" + "\n".join(used_in)
        return True, ""
    elif data_type == "music_file":
        for music in musics.values():
            if uid in music.files:
                used_in.append(music.names[0])
        if used_in:
            return False, "该文件被以下歌曲引用：\n" + "\n".join(used_in)
        return True, ""
    elif data_type == "playlist":
        for playlist in playlists.values():
            if playlist.uid == uid:
                continue
            if playlist.mode == "conditions":
                for condition in playlist.data:
                    if condition["filter"] == "playlist" and uid in condition.get("list", []):
                        used_in.append(playlist.name)
                        break
        if used_in:
            return False, "该播放列表被以下播放列表引用：\n" + "\n".join(used_in)
        return True, ""
    return True, ""


def delete_object(obj):
    """删除全局变量中的某条数据"""
    data_type = utils.get_type(obj)
    uid = obj.uid
    if data_type == "author":
        del authors[uid]
    elif data_type == "tag_group":
        del tag_groups[uid]
    elif data_type == "music":
        del musics[uid]
    elif data_type == "music_file":
        del music_files[uid]
    elif data_type == "playlist":
        del playlists[uid]
