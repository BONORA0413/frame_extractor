# Video Frame Extractor

## 한국어 안내

영상 파일의 **첫 프레임**과 **마지막 프레임**을 원본 해상도의 무손실 PNG로 저장하는 로컬 데스크톱 프로그램입니다. 영상은 외부 서버로 업로드되지 않으며, 내 컴퓨터에서 FFmpeg로만 처리됩니다.

### 주요 기능

- 첫 프레임과 마지막 프레임을 PNG로 추출
- 미리보기, 해상도, FPS, 길이, 총 프레임 수 표시
- MP4, MOV, MKV, AVI, WebM 등 FFmpeg가 지원하는 대부분의 영상 형식 지원
- 색상 범위와 색공간을 직접 지정해 원본과 색상이 다르게 보이는 문제 대응
- `tkinterdnd2` 설치 시 드래그 앤 드롭 지원

### 설치와 실행

Python 3.9 이상을 설치한 뒤, 아래 명령을 실행하세요.

```bash
git clone https://github.com/BONORA0413/frame_extractor.git
cd frame_extractor
python -m pip install -r requirements.txt
python frame_extractor.py
```

Windows에서 `python` 명령이 작동하지 않으면 마지막 줄을 `py frame_extractor.py`로 바꾸세요.

### 사용 방법

1. 점선 영역에 영상을 끌어다 놓거나 클릭해 선택합니다.
2. 필요하면 **변경** 버튼으로 저장 폴더를 지정합니다. 지정하지 않으면 원본 영상과 같은 폴더에 저장됩니다.
3. **프레임 추출 (첫 장면 + 마지막 장면)** 버튼을 누릅니다.

예를 들어 480프레임 영상은 다음처럼 저장됩니다.

```text
video_first_frame1_of_480.png
video_last_frame480_of_480.png
```

색상 또는 대비가 원본과 다르게 보이면 앱의 **색상 범위**와 **색공간** 옵션을 바꿔 원본과 일치하는 조합을 선택하세요.

더 자세한 안내: [한국어 사용법](사용법.md)

---

A small, local desktop application for exporting the **first** and **last** frame of a video as lossless PNG files. It uses FFmpeg locally—your video is never uploaded anywhere.

## Features

- Extracts first and final video frames in original resolution
- Saves lossless PNG images with frame-number-aware filenames
- Shows a thumbnail, duration, resolution, FPS, and total frame count
- Supports drag and drop when `tkinterdnd2` is installed
- Handles common formats supported by FFmpeg, including MP4, MOV, MKV, AVI, WebM, M2TS, and more
- Offers manual color range and color-space overrides for videos with incomplete metadata

## Requirements

- Python 3.9 or later
- Tkinter (included with most Python installers)

## Install

```bash
git clone https://github.com/BONORA0413/frame_extractor.git
cd frame_extractor
python -m pip install -r requirements.txt
```

`imageio-ffmpeg` downloads or provides an FFmpeg executable automatically in the usual case. If FFmpeg cannot be found, install it separately and make it available on your system `PATH`.

On Ubuntu or other Debian-based Linux distributions, you may also need:

```bash
sudo apt install python3-tk
```

## Run

```bash
python frame_extractor.py
```

On Windows, use `py frame_extractor.py` if `python` is not available in your terminal.

1. Drop a video onto the highlighted area, or click it to choose a file.
2. Optionally choose a destination folder. By default, files are saved next to the source video.
3. Select **Extract Frames** to export both images.

For a 480-frame source named `video.mp4`, the exported files are named:

```text
video_first_frame1_of_480.png
video_last_frame480_of_480.png
```

## Color accuracy

Video pixels are commonly stored as YUV and need color-range and color-space metadata to convert accurately to RGB PNG. The app reads available FFmpeg metadata and defaults to Limited/BT.709 if metadata is missing. If the preview does not match the original video, use the on-screen **Color Range** and **Color Space** controls to select the appropriate values before extraction.

## Privacy

All analysis and image extraction happen on the local computer. This application does not upload or transmit video files.

## License

No license has been selected yet. Until a license is added, the repository content is subject to the default copyright protections of its author.

