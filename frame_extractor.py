#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
영상 첫/마지막 프레임 추출기 (v2 - 색상 정확도 강화판)
--------------------------------------------------------
영상을 드래그 앤 드롭으로 넣으면 미리보기 썸네일과 총 프레임 수를 보여주고,
버튼 한 번으로 첫 프레임과 마지막 프레임을 무손실 PNG 두 장으로 저장합니다.

v2에서 바뀐 점
- 영상 선택 영역에 드래그 앤 드롭 지원 (tkinterdnd2 설치 시)
- 영상을 넣으면 즉시 미리보기 썸네일 표시
- 파일명에 "몇 번째 프레임 / 총 몇 프레임"이 명확히 남도록 네이밍 변경
  예) video_first_frame1_of_480.png / video_last_frame480_of_480.png
- [색상/대비 불일치 수정] 기존 버전은 ffmpeg의 색상 범위(Full/Limited)·
  색공간(BT.709/BT.601) 자동 추정에만 의존했는데, 원본 영상에 색상 태그가
  없거나(특히 AI 영상 생성 툴 출력물에 흔함) 실제 값과 다르게 추정되면
  색이 번지거나 대비가 달라 보일 수 있었습니다. 이제는
    1) ffmpeg -i 로 스트림에 실제로 박혀 있는 색상 범위/색공간 태그를 직접 읽고,
    2) 태그가 없으면 가장 흔한 기본값(BT.709/Limited)으로 명시적으로 고정하며,
    3) 크로마 업샘플링을 고정밀 모드(accurate_rnd, full_chroma_int/inp)로 강제
  해서 매번 동일한 결과가 나오도록 했습니다. 그래도 원본과 다르게 보인다면
  UI의 "색상 범위 / 색공간" 값을 수동으로 바꿔가며 미리보기가 원본과
  같아지는 조합을 고르면 됩니다(자동 추정이 실제 값과 다른 극소수 케이스 대응).
- 검정+주황 톤의 다크 테마 UI로 정리
"""

import os
import re
import sys
import tempfile
import threading
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

from shutil import which


# ============================================================ 색 팔레트
COLOR_BG = "#121214"
COLOR_BG_PANEL = "#1b1b1f"
COLOR_BG_CARD = "#242428"
COLOR_ORANGE = "#ff7a1a"
COLOR_ORANGE_ACTIVE = "#ff9645"
COLOR_TEXT = "#f5f5f5"
COLOR_TEXT_DIM = "#b6b6bc"
COLOR_BORDER = "#3c3c42"
COLOR_GREEN = "#3ddc84"
COLOR_RED = "#ff6b6b"

VIDEO_EXTS = "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mts *.m2ts *.mxf *.wmv *.flv *.ts *.3gp"
VIDEO_EXT_SET = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
                  ".mts", ".m2ts", ".mxf", ".wmv", ".flv", ".ts", ".3gp"}


# ============================================================ ffmpeg 유틸
def get_ffmpeg_path():
    """pip로 설치된 번들 ffmpeg를 우선 사용하고, 없으면 시스템 ffmpeg를 찾는다."""
    if imageio_ffmpeg is not None:
        try:
            path = imageio_ffmpeg.get_ffmpeg_exe()
            if path and Path(path).exists():
                return path
        except Exception:
            pass
    system_ffmpeg = which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return None


def run_cmd(cmd, timeout=None):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, **kwargs)


def _parse_color_tags(pix_fmt, tag_str):
    """ffmpeg -i 출력의 'yuv420p(tv, bt709, progressive)' 같은 괄호 태그를 해석한다."""
    range_ = None
    matrix = None
    if pix_fmt and pix_fmt.startswith("yuvj"):
        range_ = "pc"  # yuvj*는 레거시 JPEG 계열로 풀 레인지가 관례
    if tag_str:
        inner = tag_str.strip("()")
        parts = [p.strip().lower() for p in re.split(r"[,/]", inner) if p.strip()]
        for p in parts:
            if p in ("tv", "mpeg", "limited"):
                range_ = "tv"
            elif p in ("pc", "jpeg", "full"):
                range_ = "pc"
            elif p == "bt709":
                matrix = matrix or "bt709"
            elif p in ("smpte170m", "bt470bg", "bt601"):
                matrix = matrix or "bt601"
            elif p in ("bt2020nc", "bt2020c", "bt2020_ncl", "bt2020_cl", "bt2020"):
                matrix = matrix or "bt2020nc"
    return range_, matrix


def probe_video(ffmpeg_path, video_path):
    """ffmpeg -i 로 해상도/길이/fps/색상 범위·색공간을 읽어온다 (ffprobe 불필요)."""
    cmd = [ffmpeg_path, "-hide_banner", "-i", str(video_path)]
    result = run_cmd(cmd, timeout=20)
    text = result.stderr.decode(errors="ignore")

    info = {
        "duration_sec": None, "fps": None, "width": None, "height": None,
        "pix_fmt": None, "range": None, "matrix": None,
        "range_detected": False, "matrix_detected": False,
    }

    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", text)
    if m:
        h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        info["duration_sec"] = h * 3600 + mm * 60 + s

    vline = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Stream") and "Video:" in line:
            vline = line
            break

    if vline:
        fm = re.search(r"([\d.]+)\s*fps", vline)
        if fm:
            info["fps"] = float(fm.group(1))

        rm = re.search(r"(\d{2,6})x(\d{2,6})", vline)
        if rm:
            info["width"] = int(rm.group(1))
            info["height"] = int(rm.group(2))

        cm = re.search(r",\s*([a-zA-Z0-9_]+)(\([^)]*\))?\s*,\s*\d{2,6}x\d{2,6}", vline)
        if cm:
            info["pix_fmt"] = cm.group(1)
            range_, matrix_ = _parse_color_tags(info["pix_fmt"], cm.group(2))
            if range_:
                info["range"], info["range_detected"] = range_, True
            if matrix_:
                info["matrix"], info["matrix_detected"] = matrix_, True

    # 태그가 없으면 가장 흔한 기본값으로 명시 고정 (추정임을 UI에 표시)
    if not info["range"]:
        info["range"] = "tv"
    if not info["matrix"]:
        info["matrix"] = "bt709"

    return info


def count_exact_frames(ffmpeg_path, video_path):
    """영상을 재인코딩 없이(패킷 복사) 끝까지 훑어 정확한 총 프레임 수를 센다."""
    cmd = [ffmpeg_path, "-hide_banner", "-i", str(video_path),
           "-map", "0:v:0", "-c", "copy", "-f", "null", "-"]
    try:
        result = run_cmd(cmd, timeout=None)
    except Exception:
        return None
    text = result.stderr.decode(errors="ignore")
    matches = re.findall(r"frame=\s*(\d+)", text)
    if matches:
        return int(matches[-1])
    return None


def build_color_vf(range_, matrix_, extra=None):
    """색상 범위/색공간을 명시적으로 고정해 항상 같은 결과가 나오도록 하는 필터 체인.
    accurate_rnd/full_chroma_int/full_chroma_inp 는 크로마 업샘플링을 고정밀
    모드로 강제해 원본과의 색 오차를 최소화한다."""
    vf = (f"scale=w=iw:h=ih:in_range={range_}:in_color_matrix={matrix_}:"
          f"out_range=full:out_color_matrix=bt709:"
          f"flags=accurate_rnd+full_chroma_int+full_chroma_inp,format=rgb24")
    if extra:
        vf += "," + extra
    return vf


def human_duration(seconds):
    if seconds is None:
        return "?"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ============================================================ 메인 앱
class FrameExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("영상 첫 · 마지막 프레임 추출기")
        self.root.geometry("720x760")
        self.root.minsize(640, 700)
        self.root.configure(bg=COLOR_BG)

        self.video_path = None
        self.output_dir = None
        self.ffmpeg_path = get_ffmpeg_path()
        self.color_info = None
        self.total_frames_exact = None
        self.thumbnail_photo = None
        self.video_info_lines = None
        self._drag_hover = False
        self.frame_count_ready = threading.Event()

        self._setup_style()
        self._build_ui()
        self._redraw_drop_zone()

        if self.ffmpeg_path is None:
            messagebox.showerror(
                "ffmpeg를 찾을 수 없습니다",
                "이 프로그램은 내부적으로 ffmpeg를 사용합니다.\n\n"
                "터미널(명령 프롬프트)에서 아래 명령어를 실행한 뒤\n"
                "프로그램을 다시 실행해주세요:\n\n"
                "    pip install imageio-ffmpeg\n\n"
                "그래도 안 되면 시스템에 ffmpeg를 직접 설치해주세요.\n"
                "(Windows: winget install ffmpeg / Mac: brew install ffmpeg)"
            )

    # -------------------------------------------------------- 스타일
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Orange.Horizontal.TProgressbar",
                         troughcolor=COLOR_BG_PANEL, background=COLOR_ORANGE,
                         bordercolor=COLOR_BG_PANEL, lightcolor=COLOR_ORANGE,
                         darkcolor=COLOR_ORANGE)
        style.configure("Dark.TCombobox",
                         fieldbackground=COLOR_BG_CARD, background=COLOR_BG_CARD,
                         foreground=COLOR_TEXT, arrowcolor=COLOR_ORANGE,
                         bordercolor=COLOR_BORDER)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", COLOR_BG_CARD)],
                  foreground=[("readonly", COLOR_TEXT)],
                  selectbackground=[("readonly", COLOR_BG_CARD)],
                  selectforeground=[("readonly", COLOR_TEXT)])

    # -------------------------------------------------------- UI 구성
    def _build_ui(self):
        title = tk.Label(self.root, text="영상 첫 · 마지막 프레임 추출기",
                          font=("Helvetica", 18, "bold"),
                          bg=COLOR_BG, fg=COLOR_ORANGE)
        title.pack(pady=(20, 2))

        subtitle = tk.Label(
            self.root,
            text="영상을 아래에 끌어다 놓거나 클릭해서 선택하세요.\n"
                 "첫 프레임과 마지막 프레임을 원본 화질 그대로 무손실 PNG로 저장합니다.",
            font=("Helvetica", 10), bg=COLOR_BG, fg=COLOR_TEXT_DIM, justify="center"
        )
        subtitle.pack(pady=(0, 14))

        # ---- 드래그 앤 드롭 / 썸네일 영역
        self.drop_canvas = tk.Canvas(self.root, bg=COLOR_BG_PANEL, height=240,
                                      highlightthickness=0, cursor="hand2")
        self.drop_canvas.pack(fill="x", padx=24, pady=(0, 12))
        self.drop_canvas.bind("<Button-1>", lambda e: self.select_video())
        self.drop_canvas.bind("<Configure>", lambda e: self._redraw_drop_zone())

        if DND_AVAILABLE:
            try:
                self.drop_canvas.drop_target_register(DND_FILES)
                self.drop_canvas.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                self.drop_canvas.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                self.drop_canvas.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        # ---- 색상 보정 옵션
        color_frame = tk.Frame(self.root, bg=COLOR_BG)
        color_frame.pack(fill="x", padx=24, pady=(0, 6))

        tk.Label(color_frame, text="색상 범위", bg=COLOR_BG, fg=COLOR_TEXT,
                  font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.range_var = tk.StringVar(value="자동")
        range_combo = ttk.Combobox(color_frame, textvariable=self.range_var, state="readonly",
                                    values=["자동", "Full(PC)", "Limited(TV)"],
                                    width=13, style="Dark.TCombobox")
        range_combo.grid(row=1, column=0, sticky="w", padx=(0, 20))
        range_combo.bind("<<ComboboxSelected>>", lambda e: self._on_color_override_changed())

        tk.Label(color_frame, text="색공간", bg=COLOR_BG, fg=COLOR_TEXT,
                  font=("Helvetica", 10, "bold")).grid(row=0, column=1, sticky="w")
        self.matrix_var = tk.StringVar(value="자동")
        matrix_combo = ttk.Combobox(color_frame, textvariable=self.matrix_var, state="readonly",
                                     values=["자동", "BT.709", "BT.601"],
                                     width=13, style="Dark.TCombobox")
        matrix_combo.grid(row=1, column=1, sticky="w")
        matrix_combo.bind("<<ComboboxSelected>>", lambda e: self._on_color_override_changed())

        self.color_status_var = tk.StringVar(value="영상을 넣으면 색상 정보가 자동으로 표시됩니다.")
        color_status = tk.Label(color_frame, textvariable=self.color_status_var,
                                 bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=("Helvetica", 9),
                                 anchor="w", justify="left", wraplength=640)
        color_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        tip = tk.Label(color_frame,
                        text="※ 미리보기가 원본과 다르면 위 값을 바꿔가며 원본과 같아지는 조합을 찾으세요.",
                        bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=("Helvetica", 9, "italic"),
                        anchor="w", justify="left", wraplength=640)
        tip.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # ---- 저장 위치
        out_frame = tk.Frame(self.root, bg=COLOR_BG)
        out_frame.pack(fill="x", padx=24, pady=(14, 6))

        tk.Label(out_frame, text="저장 위치:", bg=COLOR_BG, fg=COLOR_TEXT,
                  font=("Helvetica", 10, "bold")).pack(side="left")
        self.output_dir_var = tk.StringVar(value="(영상과 같은 폴더에 저장)")
        tk.Label(out_frame, textvariable=self.output_dir_var, bg=COLOR_BG,
                  fg=COLOR_TEXT_DIM, anchor="w").pack(side="left", padx=10, fill="x", expand=True)

        change_out_btn = tk.Button(out_frame, text="변경", command=self.select_output_dir,
                                    bg=COLOR_BG_CARD, fg=COLOR_TEXT,
                                    activebackground=COLOR_BORDER, activeforeground=COLOR_TEXT,
                                    relief="flat", padx=12, pady=4, cursor="hand2")
        change_out_btn.pack(side="right")

        # ---- 추출 버튼
        self.extract_btn = tk.Button(
            self.root, text="프레임 추출 (첫 장면 + 마지막 장면)",
            font=("Helvetica", 13, "bold"),
            bg=COLOR_ORANGE, fg="#151515",
            activebackground=COLOR_ORANGE_ACTIVE, activeforeground="#151515",
            disabledforeground="#8a8a8a",
            relief="flat", height=2, cursor="hand2",
            command=self.on_extract_click, state="disabled"
        )
        self.extract_btn.pack(padx=24, pady=(14, 8), fill="x")

        self.progress = ttk.Progressbar(self.root, mode="indeterminate",
                                         style="Orange.Horizontal.TProgressbar")
        self.progress.pack(padx=24, pady=(0, 10), fill="x")

        self.status_label = tk.Label(self.root, text="", bg=COLOR_BG, fg=COLOR_TEXT,
                                      justify="center", wraplength=660)
        self.status_label.pack(pady=(2, 14))

    # -------------------------------------------------------- 드롭존 그리기
    def _redraw_drop_zone(self):
        c = self.drop_canvas
        c.delete("all")
        w = c.winfo_width() or 660
        h = c.winfo_height() or 240
        border_color = COLOR_ORANGE if self._drag_hover else COLOR_BORDER
        c.create_rectangle(3, 3, w - 3, h - 3, outline=border_color, width=2, dash=(6, 4))

        if self.thumbnail_photo is not None:
            c.create_image(w // 2, h // 2 - 18, image=self.thumbnail_photo, anchor="center")
            if self.video_info_lines:
                c.create_text(w // 2, h - 30, fill=COLOR_TEXT,
                               font=("Helvetica", 10, "bold"),
                               text=self.video_info_lines, justify="center")
        else:
            c.create_text(w // 2, h // 2 - 34, text="🎬", font=("Helvetica", 32))
            msg = "영상을 여기에 끌어다 놓으세요\n(클릭해서 파일 선택도 가능)"
            if not DND_AVAILABLE:
                msg = "클릭해서 영상 파일을 선택하세요\n(드래그 앤 드롭은 tkinterdnd2 설치 후 사용 가능)"
            c.create_text(w // 2, h // 2 + 14, text=msg, fill=COLOR_TEXT_DIM,
                           font=("Helvetica", 11), justify="center")

    def _on_drag_enter(self, event):
        self._drag_hover = True
        self._redraw_drop_zone()

    def _on_drag_leave(self, event):
        self._drag_hover = False
        self._redraw_drop_zone()

    def _on_drop(self, event):
        self._drag_hover = False
        files = self._parse_dnd_paths(event.data)
        video_files = [f for f in files if Path(f).suffix.lower() in VIDEO_EXT_SET]
        if not video_files:
            messagebox.showwarning("지원하지 않는 파일",
                                    "영상 파일을 끌어다 놓아주세요.\n(mp4, mov, mkv, avi, webm 등)")
            self._redraw_drop_zone()
            return
        self._load_video(Path(video_files[0]))

    @staticmethod
    def _parse_dnd_paths(data):
        paths = []
        for m in re.finditer(r"\{([^{}]*)\}|(\S+)", data):
            p = m.group(1) if m.group(1) is not None else m.group(2)
            if p:
                paths.append(p)
        return paths

    # -------------------------------------------------------- 이벤트
    def select_video(self):
        path = filedialog.askopenfilename(
            title="영상 파일 선택",
            filetypes=[("영상 파일", VIDEO_EXTS), ("모든 파일", "*.*")]
        )
        if path:
            self._load_video(Path(path))

    def select_output_dir(self):
        d = filedialog.askdirectory(title="저장할 폴더 선택")
        if d:
            self.output_dir = Path(d)
            self.output_dir_var.set(str(self.output_dir))

    def _load_video(self, path):
        if not self.ffmpeg_path:
            messagebox.showerror("ffmpeg 없음", "ffmpeg를 찾을 수 없어 영상을 분석할 수 없습니다.")
            return
        self.video_path = path
        self.total_frames_exact = None
        self.frame_count_ready.clear()
        self.thumbnail_photo = None
        self.color_info = None
        self.range_var.set("자동")
        self.matrix_var.set("자동")
        self.video_info_lines = f"{path.name}\n분석 중..."
        self.color_status_var.set("영상 정보를 분석하는 중입니다...")
        self.status_label.config(text="", fg=COLOR_TEXT)
        self.extract_btn.config(state="disabled")
        self._redraw_drop_zone()
        threading.Thread(target=self._analyze_worker, args=(path,), daemon=True).start()

    # -------------------------------------------------------- 분석 워커
    def _analyze_worker(self, path):
        try:
            info = probe_video(self.ffmpeg_path, path)
            self.color_info = info
            self.root.after(0, self._apply_detected_color_ui, info)

            est_frames = None
            if info["duration_sec"] and info["fps"]:
                est_frames = max(1, round(info["duration_sec"] * info["fps"]))
            self.root.after(0, self._on_info_parsed, info, est_frames)

            self._regenerate_thumbnail()

            exact = count_exact_frames(self.ffmpeg_path, path)
            if exact is None or exact <= 0:
                exact = est_frames
            self.total_frames_exact = exact
            self.frame_count_ready.set()
            self.root.after(0, self._on_frame_count_ready, exact)
        except Exception as e:
            self.root.after(0, self._on_analyze_error, str(e))

    def _apply_detected_color_ui(self, info):
        range_label = "Full(PC)" if info["range"] == "pc" else "Limited(TV)"
        matrix_label = "BT.601" if info["matrix"] == "bt601" else "BT.709"
        if info["range_detected"] or info["matrix_detected"]:
            self.color_status_var.set(
                f"메타데이터에서 감지됨 → 색상 범위: {range_label} · 색공간: {matrix_label}"
            )
        else:
            self.color_status_var.set(
                f"영상에 색상 태그가 없어 기본값으로 가정 → 색상 범위: {range_label} · 색공간: {matrix_label}\n"
                f"(미리보기가 원본과 다르면 위 콤보박스를 직접 바꿔보세요)"
            )

    def _on_info_parsed(self, info, est_frames):
        w, h = info["width"], info["height"]
        dur = human_duration(info["duration_sec"])
        fps = f"{info['fps']:.2f}" if info["fps"] else "?"
        frame_txt = f"약 {est_frames}프레임(추정)" if est_frames else "프레임 수 계산 중..."
        res_txt = f"{w}x{h}" if w and h else "해상도 확인 중"
        self.video_info_lines = (
            f"{self.video_path.name}\n{res_txt} · {fps}fps · {dur} · {frame_txt}"
        )
        self._redraw_drop_zone()
        self.extract_btn.config(state="normal")

    def _on_frame_count_ready(self, exact):
        if not self.video_path:
            return
        info = self.color_info or {}
        w, h = info.get("width"), info.get("height")
        dur = human_duration(info.get("duration_sec"))
        fps = f"{info['fps']:.2f}" if info.get("fps") else "?"
        res_txt = f"{w}x{h}" if w and h else "해상도 확인 중"
        frame_txt = f"총 {exact}프레임" if exact else "프레임 수 확인 실패"
        self.video_info_lines = (
            f"{self.video_path.name}\n{res_txt} · {fps}fps · {dur} · {frame_txt}"
        )
        self._redraw_drop_zone()

    def _on_analyze_error(self, msg):
        self.video_info_lines = "영상 분석 실패"
        self.color_status_var.set("영상 정보를 읽지 못했습니다. 파일 형식을 확인해주세요.")
        self._redraw_drop_zone()
        messagebox.showerror("분석 오류", msg)

    # -------------------------------------------------------- 색상 보정
    def _effective_color_params(self):
        range_map = {"Full(PC)": "pc", "Limited(TV)": "tv"}
        matrix_map = {"BT.709": "bt709", "BT.601": "bt601"}
        range_ = range_map.get(self.range_var.get())
        matrix_ = matrix_map.get(self.matrix_var.get())
        info = self.color_info or {}
        if range_ is None:
            range_ = info.get("range", "tv")
        if matrix_ is None:
            matrix_ = info.get("matrix", "bt709")
        return range_, matrix_

    def _on_color_override_changed(self):
        if not self.video_path or not self.ffmpeg_path:
            return
        if self.range_var.get() != "자동" or self.matrix_var.get() != "자동":
            self.color_status_var.set("수동으로 지정한 색상 값을 사용해 미리보기를 다시 만드는 중...")
        else:
            info = self.color_info
            if info:
                self._apply_detected_color_ui(info)
        threading.Thread(target=self._regenerate_thumbnail, daemon=True).start()

    def _regenerate_thumbnail(self):
        if not self.video_path or not self.ffmpeg_path:
            return
        range_, matrix_ = self._effective_color_params()
        vf = build_color_vf(range_, matrix_, extra="scale=320:-1")
        tmp_path = Path(tempfile.gettempdir()) / "frame_extractor_thumbnail_preview.png"
        cmd = [self.ffmpeg_path, "-y", "-i", str(self.video_path),
               "-frames:v", "1", "-vf", vf, "-pix_fmt", "rgb24", str(tmp_path)]
        try:
            run_cmd(cmd, timeout=30)
        except Exception:
            return
        if tmp_path.exists() and tmp_path.stat().st_size > 0:
            self.root.after(0, self._set_thumbnail, tmp_path)

    def _set_thumbnail(self, path):
        try:
            img = tk.PhotoImage(file=str(path))
            self.thumbnail_photo = img
        except Exception:
            self.thumbnail_photo = None
        self._redraw_drop_zone()

    # -------------------------------------------------------- 추출
    def on_extract_click(self):
        if not self.video_path:
            return
        self.extract_btn.config(state="disabled")
        self.progress.start(12)
        self.status_label.config(text="추출 중입니다... (영상 길이/용량에 따라 시간이 걸릴 수 있어요)",
                                  fg=COLOR_TEXT)
        threading.Thread(target=self._extract_worker, daemon=True).start()

    def _extract_first_frame(self, video_path, out_path, vf):
        cmd = [self.ffmpeg_path, "-y",
               "-sws_flags", "accurate_rnd+full_chroma_int+full_chroma_inp+bitexact",
               "-i", str(video_path),
               "-frames:v", "1", "-vf", vf, "-pix_fmt", "rgb24", str(out_path)]
        result = run_cmd(cmd)
        if not (out_path.exists() and out_path.stat().st_size > 0):
            err = result.stderr.decode(errors="ignore")[-800:]
            raise RuntimeError("첫 프레임 추출 실패:\n" + err)

    def _extract_last_frame(self, video_path, out_path, vf):
        # 영상 끝부분만 살짝 되감아 디코딩 -> 대용량 영상도 빠르게 처리.
        # -update 1 로 끝까지 디코딩한 마지막 프레임을 덮어써서 저장하므로
        # 되감기 지점이 다소 부정확해도 최종적으로는 항상 "진짜 마지막 프레임"이 남는다.
        last_err = ""
        for offset in (3, 1, 0.3, 0):
            cmd = [self.ffmpeg_path, "-y",
                   "-sws_flags", "accurate_rnd+full_chroma_int+full_chroma_inp+bitexact"]
            if offset > 0:
                cmd += ["-sseof", f"-{offset}"]
            cmd += ["-i", str(video_path), "-update", "1",
                    "-vf", vf, "-pix_fmt", "rgb24", str(out_path)]
            result = run_cmd(cmd)
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            last_err = result.stderr.decode(errors="ignore")[-800:]
        raise RuntimeError("마지막 프레임 추출 실패:\n" + last_err)

    @staticmethod
    def _build_output_names(base, total_frames):
        if total_frames and total_frames > 0:
            first_name = f"{base}_first_frame1_of_{total_frames}.png"
            last_name = f"{base}_last_frame{total_frames}_of_{total_frames}.png"
        else:
            first_name = f"{base}_first_frame.png"
            last_name = f"{base}_last_frame.png"
        return first_name, last_name

    def _extract_worker(self):
        try:
            if not self.frame_count_ready.is_set():
                self.frame_count_ready.wait(timeout=120)

            range_, matrix_ = self._effective_color_params()
            vf = build_color_vf(range_, matrix_)

            out_dir = self.output_dir if self.output_dir else self.video_path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            base = self.video_path.stem
            total = self.total_frames_exact
            first_name, last_name = self._build_output_names(base, total)
            first_out = out_dir / first_name
            last_out = out_dir / last_name

            self._extract_first_frame(self.video_path, first_out, vf)
            self._extract_last_frame(self.video_path, last_out, vf)

            self.root.after(0, self._on_success, first_out, last_out)
        except Exception as e:
            self.root.after(0, self._on_error, str(e))

    def _on_success(self, first_out, last_out):
        self.progress.stop()
        self.extract_btn.config(state="normal")
        self.status_label.config(
            text=f"완료!\n{first_out.name}\n{last_out.name}", fg=COLOR_GREEN
        )
        messagebox.showinfo("완료", f"저장이 완료되었습니다:\n\n{first_out}\n{last_out}")

    def _on_error(self, msg):
        self.progress.stop()
        self.extract_btn.config(state="normal")
        self.status_label.config(text="오류가 발생했습니다. 아래 메시지를 확인하세요.", fg=COLOR_RED)
        messagebox.showerror("오류", msg)


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    FrameExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

