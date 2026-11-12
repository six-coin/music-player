import hashlib
import pathlib
import shutil
import subprocess

import ffmpeg


def validate_music(file_path):
    """验证并清洗音乐文件，去除所有元数据和外部数据流，返回干净的临时文件路径"""
    # 检查系统 FFmpeg 是否安装成功
    ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
    if ffmpeg_check.returncode != 0:
        raise Exception("未检测到 FFmpeg，请检查软件是否安装，以及是否正确配置了环境变量")
    
    # 检查文件存在性
    path = pathlib.Path(file_path).resolve()
    if not path.exists():
        raise Exception(f"处理文件 {path} 时发生错误：文件不存在")

    # 准备临时工作目录
    temp_dir = pathlib.Path("assets") / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 复制原始文件到临时位置，避免污染原文件
    processing_file = temp_dir / f"processing_{path.name}"
    shutil.copy2(path, processing_file)

    # 生成清洗后的临时文件
    cleaned_file = None
    try:
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            out_suffix = ".mp3"
            output_args = {
                "map": "0:a",  # 只映射第一个输入文件的音频流
                "acodec": "copy",  # 音频编码直接复制，不重新编码
                "map_metadata": "-1",  # 丢弃所有全局元数据
                "write_id3v1": 0,  # 不写入 ID3v1 标签
                "id3v2_version": 0,  # 不写入 ID3v2 标签（0表示禁用）
                "write_xing": 0,  # 不写入 Xing 编码器标识头（避免额外元数据）
                "fflags": "+bitexact",  # 启用精确位元模式，确保输出确定性（利于哈希校验）
                "format": "mp3"  # 强制输出格式为 MP3
            }
        elif suffix == ".m4a":
            out_suffix = ".m4a"
            output_args = {
                "map": "0:a",  # 只映射第一个输入文件的音频流
                "acodec": "copy",  # 音频编码直接复制，不重新编码
                "map_metadata": "-1",  # 丢弃所有全局元数据
                "movflags": "+faststart",  # 将moov原子移到文件开头，便于流式播放
                "fflags": "+bitexact",  # 启用精确位元模式，确保输出确定性（利于哈希校验）
                "format": "mp4"  # 强制输出格式为 MP4（M4A 本质是 MP4 容器）
            }
        else:
            raise Exception(f"处理文件 {path} 时发生错误：不支持该文件的格式")

        # 防止位置被占用
        cleaned_file = temp_dir / f"clean_{path.name}"
        if cleaned_file.exists():
            cleaned_file.unlink()

        # 处理文件
        try:
            stream = ffmpeg.input(str(processing_file))
            stream = ffmpeg.output(stream, str(cleaned_file), **output_args)
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
        except ffmpeg.Error as e:
            # ffmpeg 命令行执行失败时的异常处理
            error_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else "未知错误"
            raise Exception(f"FFmpeg 处理失败：{error_msg}")
        except Exception as e:
            raise Exception(f"FFmpeg 处理失败：{e}")

        # 成功后删除原始临时副本，并删除标记，避免重复清理
        processing_file.unlink()
        processing_file = None

        # 重命名为最终的 MD5 文件名
        final_file = temp_dir / f"{calculate_md5(cleaned_file)}{out_suffix}"
        if final_file.exists():
            final_file.unlink()
        cleaned_file.rename(final_file)

        return final_file

    except Exception as e:
        # 异常时清理所有临时产物，防止对之后的处理产生干扰
        if processing_file is not None and processing_file.exists():
            processing_file.unlink()
        if cleaned_file is not None and cleaned_file.exists():
            cleaned_file.unlink()
        raise Exception(f"处理文件 {path} 时发生错误：{e}")

def calculate_md5(file_path):
    """计算文件的 MD5"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()