# Music Player

本地音乐库管理器与播放器。

## 命名

| 代号 | 英文名 | 中文名 |
|---|---|---|
| manager | Music Library Manager | 音乐库管理器 |
| player | Music Player | 音乐播放器 |
| simple | Simple Music Player | 轻量音乐播放器 |

界面标题、窗口标题、文档与安装包一律使用上表的中文名；代码、目录、入口文件一律使用代号。

## 文档

- [管理器实施计划](docs/plan_manager.md)
- [命令行播放器实施计划](docs/plan_simple.md)
- [播放器预期](docs/plan_player.md)

## 快速开始

1. 双击 `setup.bat` 安装环境（需要 [uv](https://docs.astral.sh/uv/)）。
2. 双击 `manager.bat` 打开管理器。

## 入口

| 入口 | 说明 |
|---|---|
| `manager.bat` | 音乐库管理器 |
| `player.bat` | 播放器（规划中） |
| `simple.bat` | 命令行播放器（规划中） |

## 开发

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 目录

| 目录 | 说明 |
|---|---|
| `app/core` | 纯逻辑：音乐库、歌单解析、自适应 |
| `app/system` | 系统集成：原子写、文件锁、单实例、主题 |
| `app/ui/manager` | 管理器界面：三个静态文件，没有构建步骤 |
| `config/` | 运行期数据，不进版本库 |
| `assets/music/` | 入库音频，文件名即 MD5 |
