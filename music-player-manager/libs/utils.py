import datetime
import pathlib

from libs import parser


def get_type(obj):
    """检测数据类型，返回对应类型字符串"""
    if isinstance(obj, parser.Music):
        return "music"
    elif isinstance(obj, parser.Playlist):
        return "playlist"
    elif isinstance(obj, parser.MusicFile):
        return "music_file"
    elif isinstance(obj, parser.TagGroup):
        return "tag_group"
    elif isinstance(obj, parser.Tag):
        return "tag"
    elif isinstance(obj, parser.Author):
        return "author"
    return None


def get_display(obj):
    """获取对象的显示名称，用于主窗口列表不定类型数据显示名称的获取"""
    data_type = get_type(obj)
    if data_type == "music":
        return get_music_display_name(obj)
    elif data_type == "playlist":
        return obj.name
    elif data_type == "music_file":
        return get_music_file_display_name(obj)
    elif data_type == "tag_group":
        return obj.name
    elif data_type == "tag":
        return obj.name
    elif data_type == "author":
        return obj.name
    return str(obj)


def get_formated_timestamp(music_file):
    """返回音乐文件时间戳的格式化时间字符串"""
    return datetime.datetime.fromtimestamp(music_file.created_at).strftime("%Y/%m/%d %H:%M:%S")


def get_music_display_name(music):
    """返回歌曲显示名称"""
    name = music.names[0]
    author_names = []
    for author_id in music.authors:
        author = parser.authors.get(author_id)
        if author:
            author_names.append(author.name)
        else:
            author_names.append("未知作者")
    authors_str = "，".join(author_names)
    return f"{name}（作者：{authors_str}）"


def get_music_search_keys(music):
    """返回音乐的搜索关键字列表"""
    names = music.names
    authors = [parser.authors[author_uid].name for author_uid in music.authors if author_uid in parser.authors]
    return names + authors


def get_music_file_display_name(music_file):
    """返回文件管理标签页列表的音乐文件显示名称"""
    songs = []
    for music in parser.musics.values():
        if music_file.uid in music.files:
            songs.append(get_music_display_name(music))
    song_str = ", ".join(songs) if songs else "无关联"
    return f"创建时间：{get_formated_timestamp(music_file)}；文件 MD5：{music_file.uid}；关联歌曲：{song_str}"


def get_music_file_display_name_simple(music_file):
    """返回音乐文件编辑界面音乐文件的显示名称"""
    return f"（{get_formated_timestamp(music_file)}）{music_file.uid}"


def get_music_file_search_keys(music_file):
    """返回音乐文件的搜索关键字列表"""
    songs = set()
    for music in parser.musics.values():
        if music_file.uid in music.files:
            songs |= set(music.names)
    songs.add(music_file.uid)
    return list(songs)


def get_tag_full_display(tag):
    """返回带标签组名称的标签完整名称"""
    return f"{tag.group.name}：{tag.name}"


def parse_comma_separated(text):
    """解析音乐编辑文本框中逗号分隔形式的列表，支持反斜杠转义逗号"""
    parts = []
    current = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            current.append("/")
            i += 2
        elif char == "/":
            parts.append("".join(current).strip())
            current = []
            i += 1
        else:
            current.append(char)
            i += 1
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def parse_file_name(file):
    """通过音乐文件名解析可能的音乐名称与作者"""
    path = pathlib.Path(file).resolve()
    basename = path.stem
    parts = basename.split(" - ", 1)
    if len(parts) == 2:
        title = parts[0].strip()
        authors = [author.strip() for author in parts[1].strip().split(", ") if author.strip()]
    else:
        title = basename.strip()
        authors = []
    return {
        "path": path,
        "title": title,
        "authors": authors,
        "marked_for_review": False
    }
