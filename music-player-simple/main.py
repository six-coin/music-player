import json
import msvcrt
import os
import random
import time

import vlc

from libs import color
from libs import config
from libs import log
from libs import select

music_path = "config/music.json"


def press_any_key():
    print("\n按下任意键返回...")
    msvcrt.getch()


def get_all_files(directory):
    supported_ext = {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg"}
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith('_')]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in supported_ext:
                files.append(os.path.join(root, filename))
    return files


def get_prob(count):
    if count <= 10:
        return 0.05 + (count - 1) / 9 * 0.45
    elif count <= 20:
        return 0.525 + (count - 11) / 9 * 0.225
    elif count <= 30:
        return 0.75 + (count - 21) / 9 * 0.1
    else:
        return 0.85


def play_playlist(files, skip_counts, timeout_seconds=None):
    os.system("cls")

    total_songs = len(files)
    if timeout_seconds is not None:
        start_time = time.time()
        target_time = time.strftime("%H:%M", time.localtime(start_time + timeout_seconds))
    else:
        start_time = None
        target_time = None

    try:
        while True:
            random.shuffle(files)  # 打乱播放列表，随机播放

            for file_path in files:
                cnt = skip_counts.get(file_path, 0)
                if cnt != 0:
                    prob = get_prob(cnt)
                    if random.random() < prob:
                        song_name = os.path.splitext(os.path.basename(file_path))[0]
                        log.write(f"由于跳过次数{cnt}, 随机跳过：{song_name}", 3)
                        continue

                song_name = os.path.splitext(os.path.basename(file_path))[0]
                log.write(f"即将播放：{song_name}", 3)

                # 显示即将播放
                try:
                    os.system("cls")
                    print(color.cyan + "=============== 即将播放 ===============")
                    print(color.blue + "歌曲名称：  " + color.dim_white + song_name)
                    print(color.blue + "总歌曲数目：" + color.dim_white + str(total_songs))
                    print("按下 Ctrl+C 返回到主界面")
                    print(color.cyan + "========================================")
                    time.sleep(0.5)
                except KeyboardInterrupt:
                    return

                # 播放歌曲
                player = vlc.MediaPlayer(file_path)
                try:
                    player.play()
                    time.sleep(0.1)

                    log.write(f"开始播放：{song_name}", 3)
                    os.system("cls")
                    print(color.cyan + "=============== 正在播放 ===============")
                    print(color.blue + "歌曲名称：  " + color.dim_white + song_name)
                    print(color.blue + "总歌曲数目：" + color.dim_white + str(total_songs))
                    print("按下 Ctrl+C 跳过本歌曲")
                    print("连按两次 Ctrl+C 返回到主界面")
                    if timeout_seconds is not None:
                        print("定时关闭已开启，将在 " + color.cyan + target_time + color.dim_white + " 自动关机")
                    print(color.cyan + "========================================")

                    while player.is_playing():
                        try:
                            time.sleep(0.1)
                        except KeyboardInterrupt:
                            skip_counts[file_path] += 1
                            with open(music_path, "w") as f:
                                json.dump(skip_counts, f, indent=4)
                            time.sleep(0.1)
                            player.stop()
                            log.write(f"跳过歌曲：{song_name}", 3)
                            break

                except KeyboardInterrupt:
                    time.sleep(0.1)
                    player.stop()
                    log.write(f"跳过歌曲：{song_name}", 3)

                # 歌曲结束后，检查是否超时
                if timeout_seconds is not None:
                    elapsed_seconds = time.time() - start_time
                    if elapsed_seconds > timeout_seconds:
                        log.write("定时已结束，执行关机", 3)
                        os.system("shutdown /s /t 20")
                        return

    except Exception as e:
        log.write(f"播放歌曲时出现未知错误：{e}", 1)
        return


def select_operation(files, skip_counts):
    options = ["播放歌单", "定时关闭", "退出程序"]
    prompt = "选择您要使用的功能。"
    choice = select.single(options, prompt)

    if choice == 0:  # 播放歌单
        play_playlist(files, skip_counts)

    elif choice == 1:  # 定时关闭
        timed_options = ["10 分钟", "15 分钟", "20 分钟", "25 分钟", "30 分钟", "自行输入"]
        timed_prompt = "选择定时关闭的时长。"
        timed_choice = select.single(timed_options, timed_prompt)
        if timed_choice == 5:  # 自行输入
            try:
                minutes = int(input("请输入时长（以分钟为单位）："))
                if minutes < 1:
                    raise ValueError
            except ValueError:
                print(color.red + "输入时长格式错误，返回主菜单。")
                press_any_key()
                return False
        else:
            minutes = [10, 15, 20, 25, 30][timed_choice]
        play_playlist(files, skip_counts, timeout_seconds=minutes * 60)

    elif choice == 2:  # 退出程序
        log.write("程序已退出", 3)
        return True

    return False


def main():
    log.init("main")

    try:
        # 初始化颜色功能
        try:
            color.init()
        except Exception as e:
            err_msg = f"初始化颜色功能时发生错误：{e}"
            log.write(err_msg, 0)
            log.error(err_msg)

        # 读取存储音乐的文件夹路径
        folder_schema = {
            "type": dict,
            "required": ["folder"],
            "properties": {
                "folder": {
                    "type": str,
                    "default": ""
                }
            }
        }
        folder_path = "config/folder.json"
        try:
            config.read(folder_path, "folder", folder_schema)
            log.write("已读取音乐列表", 3)
        except Exception as e:
            err_msg = f"程序无法启动，因为无法读取 {folder_path}：{e}"
            log.write(err_msg, 0)
            log.error(err_msg)

        files = get_all_files(config.configs["folder"]["folder"])
        if not files:
            err_msg = f"指定文件夹 {folder_path} 中没有符合条件的音乐文件"
            log.write(err_msg, 0)
            log.error(err_msg)

        try:
            with open(music_path, "r") as f:
                skip_counts = json.load(f)
        except FileNotFoundError:
            skip_counts = {}
            log.write(f"没有找到文件 {music_path}，创建一个新的", 2)

        # 检查并移除不存在的文件记录
        removed_count = 0
        existing_paths = set(files)
        for file_path in list(skip_counts.keys()):
            if file_path not in existing_paths:
                song_name = os.path.splitext(os.path.basename(file_path))[0]
                log.write(f"移除不存在的文件记录：{song_name} ({file_path})", 2)
                del skip_counts[file_path]
                removed_count += 1

        if removed_count > 0:
            log.write(f"已从跳过记录中移除 {removed_count} 个不存在的文件", 3)

        # 为新文件添加跳过次数记录
        for file_path in files:
            if file_path not in skip_counts:
                skip_counts[file_path] = 0

        # 保存更新后的跳过记录
        with open(music_path, "w") as f:
            json.dump(skip_counts, f, indent=4)

        while True:
            try:
                if select_operation(files, skip_counts):
                    return
            except KeyboardInterrupt:
                pass

    except Exception as e:
        err_msg = f"程序运行时出现未知错误：{e}"
        log.write(err_msg, 0)
        log.error(err_msg)


if __name__ == "__main__":
    main()
