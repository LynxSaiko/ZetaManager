import os
import curses
import subprocess
import shutil
import pwd
import stat
import time

from curses import textpad
from pathlib import Path
import traceback
from panel import FilePanel
from colors import ColorScheme
from archive_extractor import ArchiveExtractor

class FileManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.color_scheme = ColorScheme()
        self.left_panel = FilePanel(str(Path.home()))
        self.right_panel = FilePanel("/")
        self.active_panel = "left"
        self.search_mode = False
        self.search_query = ""
        self.message = ""
        self.message_timer = 0
        self.clipboard_path = ""
        self.clipboard_mode = ""  # "copy" or "cut"
        self.right_panel_visible = True
        self.bg_task = None        # nama task
        self.bg_progress = 0       # 0–100
        self.bg_current = ""       # nama file
        self.bg_done = False       # selesai atau belum
        self.bg_total = 0
        self.bg_now = 0
        self.create_windows()
        self.init_ui()

    def init_ui(self):
        self.stdscr.keypad(True)
        curses.curs_set(0)
        curses.use_default_colors()
        self.stdscr.clear()
        self.stdscr.refresh()

    @property
    def current_panel(self):
        return self.left_panel if self.active_panel == "left" else self.right_panel

    @property
    def inactive_panel(self):
        return self.right_panel if self.active_panel == "left" else self.left_panel


    def create_windows(self):
        h, w = self.stdscr.getmaxyx()
        mid = w // 2

        try:
            self.left_win.erase()
            self.right_win.erase()
            del self.left_win
            del self.right_win
        except:
            pass

        self.left_win = curses.newwin(h - 4, mid - 1, 2, 0)
        self.right_win = curses.newwin(h - 4, w - mid - 1, 2, mid + 1)

        self.left_win.keypad(True)
        self.right_win.keypad(True)




    # =====================================================
    #                    DRAW UI
    # =====================================================
    def draw(self):
        height, width = self.stdscr.getmaxyx()

        if height <= 0 or width <= 0:
            return

        if height < 10 or width < 40:
            try:
                self.stdscr.clear()
                self.stdscr.addstr(0, 0, "Terminal terlalu kecil. Perbesar dan jalankan ulang.")
                self.stdscr.refresh()
                curses.napms(2000)
                return
            except:
                return

        self.draw_header(width)

        if self.right_panel_visible:
            panel_width = max((width - 4) // 2, 10)
        else:
            panel_width = width - 4

        base_panel_height = max(height - 4, 5)
        panel_height = base_panel_height - (2 if self.search_mode else 0)

        self.draw_panel(
            self.left_panel,
            2,
            1,
            panel_height,
            panel_width,
            self.active_panel == "left",
        )

        if self.right_panel_visible:
            self.draw_panel(
                self.right_panel,
                2,
                panel_width + 2,
                panel_height,
                panel_width,
                self.active_panel == "right",
            )

        if self.message and self.message_timer > 0:
            self.stdscr.addstr(
                height - 1,
                0,
                self.message.ljust(width - 1),
                curses.color_pair(8 if "Error" in self.message else 9),
            )
            self.message_timer -= 1

        self.draw_status_bar(height, width)
        self.draw_progress_bar(height, width)

        self.stdscr.refresh()



    def human_size(self, size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def file_permissions(self, mode):
        perms = [
            stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR,
            stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
            stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH,
        ]
        symbols = ["r", "w", "x"] * 3
        return "".join(symbols[i] if mode & perms[i] else "-" for i in range(9))


    def draw_status_bar(self, height, width):
        selected = self.current_panel.get_selected()
        if not selected or selected == "[Permission Denied]":
            return

        full_path = os.path.join(self.current_panel.path, selected)

        try:
            stat_info = os.stat(full_path)
            size = self.human_size(stat_info.st_size) if not os.path.isdir(full_path) else "<DIR>"
            owner = pwd.getpwuid(stat_info.st_uid).pw_name
            perms = self.file_permissions(stat_info.st_mode)
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat_info.st_mtime))

            info = f"{selected} | {size} | {owner} | {perms} | {mtime}"

        except Exception:
            info = f"{selected} | <no info>"

        color = self.color_scheme.get(2) | curses.A_BOLD   # warna teks saja, no bg

        try:
            self.stdscr.addstr(height - 2, 1, info[: width - 2], color)
        except curses.error:
            pass


    def draw_header(self, width):
        header = "[ Zeta Manager ]"
        x = max(0, (width - len(header)) // 2)
        bg_color = self.color_scheme.get(12)
        text_color = self.color_scheme.get(2) | curses.A_BOLD

        try:
            self.stdscr.attron(bg_color)
            self.stdscr.addstr(0, 0, " " * width)
            self.stdscr.attroff(bg_color)
            self.stdscr.addstr(0, x, header, text_color)
        except curses.error:
            pass

    # =====================================================
    #                      TOGGLE
    # =====================================================
    def toggle_right_panel(self):
        self.right_panel_visible = not self.right_panel_visible

        if not self.right_panel_visible and self.active_panel == "right":
            self.active_panel = "left"

        self.show_message(
            f"Toggle panel {'hidden' if not self.right_panel_visible else 'shown'}",
            2
        )


    def get_icon(self, filename):
        name = filename.lower()
        full = os.path.join(self.current_panel.path, filename)

        # ====== DIRECTORY ======
        if os.path.isdir(full):
            # Folder open jika aktiv panel & cursor pada file ini
            if filename == self.current_panel.get_selected():
                return ""   # nf-fa-folder_open
            return ""       # nf-fa-folder

        # ====== PERMISSION DENIED ======
        if filename == "[Permission Denied]":
            return ""  # lock

        # ====== SYMLINK ======
        if os.path.islink(full):
            return ""  # nf-oct-file_symlink

        # ====== HIDDEN FILE ======
        if name.startswith("."):
            return ""  # nf-fa-terminal (represent hidden)

        # ====== EXECUTABLES ======
        if os.access(full, os.X_OK) and not os.path.isdir(full):
            return ""  # nf-oct-gear

        # ====== PROGRAMMING LANGUAGES ======

        # Python
        if name.endswith(".py"): return ""

        # C / C++
        if name.endswith((".c", ".h")): return ""
        if name.endswith((".cpp", ".hpp", ".cc", ".cxx")): return ""

        # Rust
        if name.endswith(".rs"): return ""

        # Go
        if name.endswith(".go"): return ""

        # Java
        if name.endswith(".java"): return ""

        # Kotlin
        if name.endswith(".kt"): return ""

        # Swift
        if name.endswith(".swift"): return ""

        # C#
        if name.endswith(".cs"): return ""

        # PHP
        if name.endswith(".php"): return ""

        # Ruby
        if name.endswith(".rb"): return ""

        # Lua
        if name.endswith(".lua"): return ""

        # JavaScript
        if name.endswith(".js"): return ""
        if name.endswith(".mjs"): return ""

        # TypeScript
        if name.endswith(".ts"): return ""
        if name.endswith(".tsx"): return ""

        # HTML / CSS
        if name.endswith(".html"): return ""
        if name.endswith(".css"): return ""
        if name.endswith(".scss"): return ""
        if name.endswith(".less"): return ""
        if name.endswith(".svelte"): return ""
        if name.endswith(".vue"): return "﵂"

        # SQL / DB
        if name.endswith((".sql", ".db", ".sqlite", ".sqlite3")):
            return ""

        # JSON / YAML / TOML / Config
        if name.endswith(".json"): return ""
        if name.endswith(".yaml") or name.endswith(".yml"): return ""
        if name.endswith(".toml"): return ""
        if name.endswith((".ini", ".cfg")): return ""

        # Makefile / build system
        if name in ("makefile", "gnumakefile") or name.endswith(".mk"):
            return ""
        if name.endswith(".cmake"):
            return "󰔷"

        # Assembly
        if name.endswith((".asm", ".s")):
            return ""

        # Shell Script
        if name.endswith((".sh", ".bash", ".zsh")):
            return ""

        # Docker / DevOps
        if name == "dockerfile":
            return ""
        if name.endswith(".tf"):
            return ""

        # Git stuff
        if name.endswith(".patch"): return ""
        if name.endswith(".diff"): return ""

        # ====== DOCUMENTS ======
        if name.endswith(".md"): return ""
        if name.endswith(".txt"): return ""
        if name.endswith(".pdf"): return ""
        if name.endswith((".doc", ".docx")): return ""
        if name.endswith((".ppt", ".pptx")): return ""
        if name.endswith((".xls", ".xlsx")): return ""

        # XML
        if name.endswith(".xml"): return ""

        # ====== MEDIA ======
        if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
            return ""
        if name.endswith((".mp4", ".mkv", ".avi", ".mov", ".flv")):
            return ""
        if name.endswith((".mp3", ".wav", ".flac", ".ogg")):
            return ""

        # ====== ARCHIVE ======
        if name.endswith((".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz")):
            return ""

        # ====== FONTS ======
        if name.endswith((".ttf", ".otf", ".woff", ".woff2")):
            return ""

        # ====== DEFAULT FILE ======
        return ""


    # =====================================================
    #                DRAW PANEL (LEFT/RIGHT)
    # =====================================================
    def draw_panel(self, panel, y, x, height, width, active):
        # SEARCH MODE
        if active and self.search_mode:
            search_line = f"[ /: {self.search_query}"
            search_bg = self.color_scheme.get(12) | curses.A_BOLD

            self.stdscr.attron(search_bg)
            self.stdscr.addstr(y, x, " " * (width + 1))
            self.stdscr.addstr(y, x + 2, search_line[: width - 3])
            self.stdscr.attroff(search_bg)
            panel_y = y + 1

        else:
            path_line = panel.path
            if len(path_line) > width - 4:
                path_line = "..." + path_line[-(width - 7):]

            header_color = self.color_scheme.get(12 if active else 4)
            self.stdscr.attron(header_color)
            self.stdscr.addstr(y, x, " " * (width + 1))
            self.stdscr.addstr(y, x + 2, path_line.ljust(width - 3))
            self.stdscr.attroff(header_color)
            panel_y = y + 1

        # DRAW BORDER
        border_color = curses.color_pair(2) if active else curses.color_pair(3)
        self.stdscr.attron(border_color)
        try:
            for i in range(panel_y, panel_y + height + 1):
                if i == panel_y:
                    self.stdscr.addstr(i, x, "┌" + "─" * (width - 1) + "┐")
                elif i == panel_y + height:
                    self.stdscr.addstr(i, x, "└" + "─" * (width - 1) + "┘")
                else:
                    self.stdscr.addstr(i, x, "│")
                    self.stdscr.addstr(i, x + width, "│")
        except curses.error:
            pass
        self.stdscr.attroff(border_color)

        # FILES
        total_files = len(panel.files)
        visible_items = height - 2
        start = panel.scroll_offset
        end = min(start + visible_items, total_files)

        for i, item in enumerate(panel.files[start:end]):
            idx = start + i
            is_selected = idx == panel.cursor_pos
            full_path = os.path.join(panel.path, item)
            is_dir = os.path.isdir(full_path)

            if is_dir:
                size_str = "<DIR>"
            else:
                try:
                    size_str = f"{os.path.getsize(full_path)} B"
                except:
                    size_str = "N/A"

            icon = self.get_icon(item)
            name_trim = item if len(item) <= width - 20 else item[:width - 23] + "..."
            display_name = f"{icon} {name_trim}"
            line = f"{display_name:<{width - 15}} {size_str:>10}"

            color = (
                self.color_scheme.get(7) if is_selected and is_dir
                else self.color_scheme.get(5) if is_selected
                else self.color_scheme.get(6) if is_dir
                else self.color_scheme.get(1)
            )

            try:
                self.stdscr.addstr(panel_y + 1 + i, x + 2, line[: width - 3], color)
            except curses.error:
                pass

        # FOOTER SUMMARY
        try:
            summary_text = f"[ {total_files} files ]"
            summary_color = self.color_scheme.get(9 if active else 8) | curses.A_BOLD
            self.stdscr.attron(summary_color)
            self.stdscr.addstr(panel_y + height, x + 2, summary_text[: width - 4])
            self.stdscr.attroff(summary_color)
        except curses.error:
            pass

    # =====================================================
    #                FILE OPERATIONS
    # =====================================================
    def create_new_file(self):
        selected = self.current_panel.path
        if not selected:
            self.show_message("No directory selected", 2)
            return

        height, width = self.stdscr.getmaxyx()
        popup_h = 5
        popup_w = min(50, width - 10)
        popup_y = max(1, height // 2 - popup_h // 2)
        popup_x = max(1, width // 2 - popup_w // 2)

        popup = curses.newwin(popup_h, popup_w, popup_y, popup_x)
        popup.border()
        popup.addstr(0, 2, " Create New File ")
        popup.addstr(1, 2, "Enter new file name: ")
        popup.refresh()

        input_win = curses.newwin(1, popup_w - 12, popup_y + 2, popup_x + 11)

        curses.curs_set(1)
        curses.noecho()

        try:
            box = textpad.Textbox(input_win)
            new_file_name = box.edit().strip()

            if new_file_name:
                new_file_path = os.path.join(self.current_panel.path, new_file_name)
                with open(new_file_path, "w") as f:
                    f.write("")
                self.show_message(f"Created '{new_file_name}'", 3)
                self.current_panel.refresh_files()

        finally:
            curses.curs_set(0)
            self.stdscr.touchwin()
            self.stdscr.refresh()

    # =====================================================
    #      FULL COPY / CUT / PASTE (NO DELETE!)
    # =====================================================
    def copy_file(self):
        selected = self.current_panel.get_selected()
        if not selected or selected == "[Permission Denied]":
            self.show_message("No file selected", 2)
            return

        self.clipboard_path = os.path.join(self.current_panel.path, selected)
        self.clipboard_mode = "copy"
        self.show_message(f"Copied: {selected}", 3)

    def cut_file(self):
        selected = self.current_panel.get_selected()
        if not selected or selected == "[Permission Denied]":
            self.show_message("No file selected", 2)
            return

        self.clipboard_path = os.path.join(self.current_panel.path, selected)
        self.clipboard_mode = "cut"
        self.show_message(f"Cut: {selected}", 3)

    def draw_progress_bar(self, height, width):
        if not self.bg_task or self.bg_done:
            return

        bar_width = width - 20
        filled = int((self.bg_progress / 100) * bar_width)
        empty = bar_width - filled

        bar = "[" + "=" * filled + " " * empty + "]"
        line = (
            f"{self.bg_task}: {self.bg_current} "
            f"{bar} {self.bg_progress:.0f}% "
        )

        try:
            self.stdscr.addstr(height - 3, 1, line[: width - 2], self.color_scheme.get(3) | curses.A_BOLD)
        except curses.error:
            pass


    def paste_file(self):
        """Paste file with progress bar"""
        if not self.clipboard_path:
            self.show_message("Clipboard empty", 2)
            return

        src = self.clipboard_path
        dest_dir = self.current_panel.path
        filename = os.path.basename(src)
        dest = os.path.join(dest_dir, filename)

        if os.path.isdir(src):
            self.show_message("Folder copy not yet supported with progress", 3)
            return

        self.bg_task = "Copy" if self.clipboard_mode == "copy" else "Move"
        self.bg_progress = 0
        self.bg_current = filename
        self.bg_done = False

        try:
            self.bg_total = os.path.getsize(src)
        except:
            self.show_message("Error getting file size", 5)
            return
            
        self.bg_now = 0

        import threading
        
        def worker():
            try:
                with open(src, "rb") as fsrc, open(dest, "wb") as fdst:
                    chunk = 1024 * 1024  # 1MB
                    while True:
                        if self.bg_done:  # Check jika di-cancel
                            break
                        
                        data = fsrc.read(chunk)
                        if not data:
                            break
                        
                        fdst.write(data)
                        self.bg_now += len(data)
                        self.bg_progress = (self.bg_now / self.bg_total) * 100
                        
            except Exception as e:
                self.bg_done = True
                self.show_message(f"Error during copy: {e}", 5)
                return

            # Hapus source jika cut mode
            if not self.bg_done and self.clipboard_mode == "cut":
                try:
                    os.remove(src)
                except:
                    pass

            # Reset status
            if not self.bg_done:
                self.bg_done = True

        # Start thread
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        
        # Mode non-blocking untuk handle input selama proses
        self.stdscr.nodelay(True)
        while thread.is_alive():
            self.draw()  # Hanya main thread yang boleh draw
            key = self.stdscr.getch()
            if key != -1:
                if key == 27:  # ESC untuk cancel
                    self.bg_done = True
                    # Tunggu thread berhenti
                    thread.join(timeout=1)
                    self.show_message("Operation cancelled", 3)
                    self.stdscr.nodelay(False)
                    return
                self.handle_input()
            curses.napms(50)  # Update setiap 50ms
        
        self.stdscr.nodelay(False)
        
        # Selesai
        self.current_panel.refresh_files()
        self.show_message(f"{self.bg_task} done: {filename}", 3)
        self.bg_task = None  # Reset

    # =====================================================
    #                   DELETE FILE
    # =====================================================
    def delete_file(self):
        selected = self.current_panel.get_selected()
        if not selected:
            self.show_message("No file selected", 2)
            return

        path = os.path.join(self.current_panel.path, selected)
        height, width = self.stdscr.getmaxyx()

        popup_h = 5
        popup_w = 50
        popup = curses.newwin(
            popup_h, popup_w, height // 2 - popup_h // 2, width // 2 - popup_w // 2
        )
        popup.border()
        popup.addstr(0, 2, " Confirm Delete ")
        popup.addstr(1, 2, f"Delete '{selected[:30]}'?")
        popup.addstr(2, 2, "This action cannot be undone!")
        popup.addstr(3, 2, "Press Y to confirm, any key to cancel")
        popup.refresh()

        key = self.stdscr.getch()

        if key in [ord("Y"), ord("y")]:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.show_message(f"Deleted '{selected}'", 3)
                self.current_panel.refresh_files()
            except Exception as e:
                self.show_message(f"Error deleting: {e}", 5)

    # =====================================================
    #                   USER INPUT HANDLER
    # =====================================================
    def handle_input(self):
        # Jika ada operasi background yang sedang berjalan, gunakan timeout
        if self.bg_task and not self.bg_done:
            self.stdscr.timeout(100)  # Timeout 100ms agar tidak blocking
        else:
            self.stdscr.timeout(-1)  # Blocking jika tidak ada operasi
        
        key = self.stdscr.getch()
        
        # Reset ke blocking setelah getch
        self.stdscr.timeout(-1)
        
        # Jika timeout terjadi (key == -1), tetap return True agar loop berlanjut
        if key == -1:
            return True

        if self.search_mode:
            self.handle_search_input(key)
            return True

        actions = {
            curses.KEY_UP: lambda: self.current_panel.navigate(-1, self.get_visible_height()),
            curses.KEY_DOWN: lambda: self.current_panel.navigate(1, self.get_visible_height()),
            curses.KEY_LEFT: self.current_panel.go_up,
            curses.KEY_RIGHT: self.current_panel.enter_directory,

            curses.KEY_F4: self.toggle_right_panel,

            curses.KEY_F6: self.copy_file,
            curses.KEY_F7: self.cut_file,
            curses.KEY_F8: self.paste_file,
            curses.KEY_F5: self.delete_file,
            curses.KEY_F10: self.exit_program,
            curses.KEY_F11: self.view_mounts,

            10: self.execute_or_enter,
            9: self.toggle_panel,

            ord("/"): self.start_search,
            ord("n"): self.create_new_file,
            ord("r"): self.rename_file,
            ord("R"): self.rename_file,
            ord('z'): self.extract_zip,
            ord('g'): self.extract_tar_gz,
            ord('x'): self.extract_tar_xz,

            curses.KEY_F10: self.exit_program,
            
            27: self.cancel_background_task,  # ESC untuk cancel operasi background
        }

        action = actions.get(key)
        if action:
            result = action()
            return result if isinstance(result, bool) else True

        return True

    def cancel_background_task(self):
        """Cancel operasi background yang sedang berjalan"""
        if self.bg_task and not self.bg_done:
            self.bg_done = True
            self.show_message("Operation cancelled", 3)
            return True
        return False


    def get_visible_height(self):
        try:
            h, _ = self.left_win.getmaxyx()
            return max(h - 2, 3)
        except:
            return 5

    # =====================================================
    #            SEARCH, RENAME, ETC.
    # =====================================================
    def execute_or_enter(self):
        selected = self.current_panel.get_selected()
        if not selected:
            return

        full_path = os.path.join(self.current_panel.path, selected)

        if os.path.isdir(full_path):
            self.current_panel.enter_directory()
            return

        try:
            ext = os.path.splitext(full_path)[1].lower()
            
            # Pastikan file executable untuk script
            if ext in [".py", ".sh"] and not os.access(full_path, os.X_OK):
                os.chmod(full_path, os.stat(full_path).st_mode | 0o111)
            
            # SELALU gunakan xterm untuk menghindari masalah
            terminal = "xterm"
            
            if ext == ".py":
                # Execute Python file
                subprocess.Popen(
                    [terminal, "-e", "bash", "-c", f'cd "{os.path.dirname(full_path)}" && python3 "{os.path.basename(full_path)}"; echo; echo "Press Enter to close..."; read'],
                    start_new_session=True,
                )
            elif ext == ".sh":
                # Execute shell script
                subprocess.Popen(
                    [terminal, "-e", "bash", "-c", f'cd "{os.path.dirname(full_path)}" && bash "{os.path.basename(full_path)}"; echo; echo "Press Enter to close..."; read'],
                    start_new_session=True,
                )
            elif ext in [".txt", ".md", ".c", ".cpp", ".h", ".java", ".js", ".html", ".css", ".py", ".json", ".yml", ".yaml", ".xml", ".ini", ".conf"]:
                # Open text files in nano editor INSIDE terminal
                subprocess.Popen(
                    [terminal, "-e", "nano", full_path],
                    start_new_session=True,
                )
            elif ext in [".jpg", ".png", ".jpeg", ".gif", ".webp", ".bmp", ".svg"]:
                # Open images with image viewer
                if shutil.which("feh"):
                    subprocess.Popen(["feh", full_path], start_new_session=True)
                elif shutil.which("eog"):
                    subprocess.Popen(["eog", full_path], start_new_session=True)
                else:
                    subprocess.Popen(["xdg-open", full_path], start_new_session=True)
            elif ext in [".pdf"]:
                # Open PDF
                if shutil.which("evince"):
                    subprocess.Popen(["evince", full_path], start_new_session=True)
                else:
                    subprocess.Popen(["xdg-open", full_path], start_new_session=True)
            elif ext in [".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv"]:
                # Open video
                if shutil.which("mpv"):
                    subprocess.Popen(["mpv", full_path], start_new_session=True)
                elif shutil.which("vlc"):
                    subprocess.Popen(["vlc", full_path], start_new_session=True)
                else:
                    subprocess.Popen(["xdg-open", full_path], start_new_session=True)
            elif ext in [".mp3", ".wav", ".ogg", ".flac"]:
                # Open audio
                if shutil.which("mpv"):
                    subprocess.Popen(["mpv", full_path], start_new_session=True)
                else:
                    subprocess.Popen(["xdg-open", full_path], start_new_session=True)
            else:
                # Try to execute or view
                if os.access(full_path, os.X_OK):
                    # It's executable
                    subprocess.Popen(
                        [terminal, "-e", "bash", "-c", f'cd "{os.path.dirname(full_path)}" && "./{os.path.basename(full_path)}"; echo; echo "Press Enter to close..."; read'],
                        start_new_session=True,
                    )
                else:
                    # View file content
                    subprocess.Popen(
                        [terminal, "-e", "bash", "-c", f'echo "=== File: {os.path.basename(full_path)} ===" && echo && cat "{full_path}" && echo && echo "=== End of file ===" && echo && echo "Press Enter to close..."; read'],
                        start_new_session=True,
                    )

        except Exception as e:
            self.show_message(f"Error executing: {str(e)}", 5)

    def detect_terminal_safe(self):
        """Pilih terminal yang paling stabil, hindari yang bermasalah"""
        # Prioritaskan terminal yang stabil
        stable_terminals = [
            "xterm",           # Paling stabil, selalu ada di Unix
            "urxvt",
            "gnome-terminal",  # GTK-based, stabil
            "konsole",         # KDE, stabil
            "xfce4-terminal",  # XFCE, stabil
            "lxterminal",      # Lightweight, stabil
            "mate-terminal",   # MATE, stabil
            "terminator",      # Advanced features
            "tilix",           # Tiling terminal
            "alacritty",       # GPU accelerated
            "kitty",           # Modern terminal
        ]
        
        # Cari terminal yang tersedia
        for terminal in stable_terminals:
            if shutil.which(terminal):
                return terminal
        
        # Jika urxvt satu-satunya yang ada, gunakan dengan opsi aman
        if shutil.which("urxvt"):
            return "urxvt"
        
        # Fallback ke xterm (harusnya selalu ada)
        return "xterm"

    def toggle_panel(self):
        self.active_panel = "right" if self.active_panel == "left" else "left"

    def start_search(self):
        self.search_mode = True
        self.search_query = ""


    def exit_program(self):
        """Exit program dengan clear terminal"""
        # Clear terminal
        self.stdscr.clear()
        self.stdscr.refresh()
        
        # Return False untuk keluar dari main loop
        return False

    #def exit_program(self):
        #return False

    def handle_search_input(self, key):
        if key == 27:
            self.search_mode = False
            self.current_panel.filter = ""
            self.current_panel.refresh_files()

        elif key in [curses.KEY_BACKSPACE, 127]:
            self.search_query = self.search_query[:-1]
            self.current_panel.filter = self.search_query
            self.current_panel.refresh_files()

        elif key in [10, curses.KEY_ENTER]:
            self.search_mode = False

        elif 32 <= key <= 126:
            self.search_query += chr(key)
            self.current_panel.filter = self.search_query
            self.current_panel.refresh_files()

    def show_message(self, message, duration=3):
        self.message = message
        self.message_timer = duration

    # =====================================================
    #                      RENAME
    # =====================================================
    def rename_file(self):
        selected = self.current_panel.get_selected()
        if not selected or selected == "[Permission Denied]":
            self.show_message("Invalid selection", 2)
            return

        old_path = os.path.join(self.current_panel.path, selected)
        height, width = self.stdscr.getmaxyx()

        popup_h = 5
        popup_w = min(50, width - 10)
        popup_y = max(1, height // 2 - popup_h // 2)
        popup_x = max(1, width // 2 - popup_w // 2)

        popup = curses.newwin(popup_h, popup_w, popup_y, popup_x)
        popup.border()
        popup.addstr(0, 2, " Rename File ")
        popup.addstr(1, 2, f"Original: {selected[:popup_w-12]}")
        popup.addstr(2, 2, "New name: ")
        popup.refresh()

        input_width = min(40, popup_w - 12)
        input_win = curses.newwin(1, input_width, popup_y + 2, popup_x + 11)
        input_win.addstr(0, 0, selected[:input_width])

        curses.curs_set(1)
        curses.noecho()

        try:
            box = textpad.Textbox(input_win)
            new_name = box.edit().strip()

            if new_name and new_name != selected:
                new_path = os.path.join(self.current_panel.path, new_name)
                try:
                    os.rename(old_path, new_path)
                    self.show_message(f"Renamed to '{new_name[:20]}'", 3)
                    self.current_panel.refresh_files()
                except OSError as e:
                    self.show_message(f"Error: {e.strerror}", 5)

        finally:
            curses.curs_set(0)
            self.stdscr.touchwin()
            self.stdscr.refresh()

    # =====================================================
    #                      MOUNTS
    # =====================================================
    def view_mounts(self):
        paths = []
        for base in ["/mnt", "/media"]:
            if os.path.exists(base):
                for entry in os.listdir(base):
                    full = os.path.join(base, entry)
                    if os.path.ismount(full):
                        paths.append(full)

        height, width = self.stdscr.getmaxyx()
        popup_h = min(20, height - 4)
        popup_w = min(70, width - 4)
        popup_y = max(1, (height - popup_h) // 2)
        popup_x = max(1, (width - popup_w) // 2)

        popup = curses.newwin(popup_h, popup_w, popup_y, popup_x)
        popup.border()
        popup.addstr(0, 2, " Mounted in /mnt and /media ")

        if not paths:
            popup.addstr(2, 2, "No mounts found in /mnt or /media.")
        else:
            for i, path in enumerate(paths[:popup_h - 3]):
                popup.addstr(i + 1, 2, path[:popup_w - 4])

        popup.addstr(popup_h - 2, 2, "Press any key to close")
        popup.refresh()
        self.stdscr.getch()
        self.stdscr.touchwin()
        self.stdscr.refresh()

    # =====================================================
    #                      EXTRACTORS
    # =====================================================
    def extract_zip(self):
        selected = self.current_panel.get_selected()
        if not selected or not selected.endswith('.zip'):
            self.show_message("Select a .zip file first", 2)
            return
        
        success, message = ArchiveExtractor.extract_zip(
            self.stdscr, 
            self.current_panel.path, 
            selected
        )
        self.show_message(message, 3)
        if success:
            self.current_panel.refresh_files()

    def extract_tar_gz(self):
        selected = self.current_panel.get_selected()
        if not selected or not (selected.endswith('.tar.gz') or selected.endswith('.tgz')):
            self.show_message("Select a .tar.gz or .tgz file first", 2)
            return
        
        success, message = ArchiveExtractor.extract_tar_gz(
            self.stdscr,
            self.current_panel.path,
            selected
        )
        self.show_message(message, 3)
        if success:
            self.current_panel.refresh_files()

    def extract_tar_xz(self):
        selected = self.current_panel.get_selected()
        if not selected or not selected.endswith('.tar.xz'):
            self.show_message("Select a .tar.xz file first", 2)
            return
        
        success, message = ArchiveExtractor.extract_tar_xz(
            self.stdscr,
            self.current_panel.path,
            selected
        )
        self.show_message(message, 3)
        if success:
            self.current_panel.refresh_files()

    # =====================================================
    #                      MAIN LOOP
    # =====================================================
    def run(self):
        import signal
        
        running = True
        self.needs_full_redraw = True

        def hard_clear_terminal():
            os.system("printf '\\033[2J\\033[H'")

        def on_resize(signum, frame):
            try:
                curses.endwin()

                hard_clear_terminal()

                h, w = self.stdscr.getmaxyx()
                curses.resizeterm(h, w)

                self.stdscr.erase()
                curses.doupdate()

                self.create_windows()

                self.left_panel.scroll_offset = 0
                self.right_panel.scroll_offset = 0

                self.needs_full_redraw = True

            except:
                pass

        signal.signal(signal.SIGWINCH, on_resize)

        try:
            while running:
                if self.needs_full_redraw:
                    self.stdscr.erase()
                    self.draw()
                    self.needs_full_redraw = False
                else:
                    self.draw()

                running = self.handle_input()

                curses.napms(16)  # limiter ~60 FPS → anti tearing

        finally:
            try:
                curses.nocbreak()
                self.stdscr.keypad(False)
                curses.echo()
                curses.endwin()
            except:
                pass

        return False
