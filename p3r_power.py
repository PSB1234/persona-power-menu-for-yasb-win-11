import sys
import os
import subprocess
from typing import Optional, List, Tuple

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCloseEvent, QPixmap, QCursor, QMouseEvent, QKeyEvent, QWheelEvent, QTransform, QPolygon

INTRO_FRAME_MS = 55
INTRO_FADE_MS = 45
INTRO_TO_VIDEO_FADE_MS = 220
BUTTON_SPAWN_DELAY_MS = 450

QMediaPlayer = None
QVideoWidget = None

class HoverButton(QWidget):
    clicked: Signal = Signal()

    def __init__(self, normal_img: str, hover_img: str, parent: Optional[QWidget] = None, 
                 size: int = 100, rotation: float = 0.0, custom_poly: Optional[List[Tuple[int,int]]] = None,
                 hover_scale: float = 1.20) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._hovered: bool = False
        
        # Hover image size (defaults to 20% larger, but can be customized)
        hover_size: int = int(size * hover_scale)
        
        # ---------------------------------------------------------
        # BASE NORMAL IMAGE
        # ---------------------------------------------------------
        self.normal_pixmap: QPixmap = QPixmap(normal_img)
        if self.normal_pixmap.isNull():
            print(f"Failed to load image: {normal_img}")
            
        orig_w = max(1, self.normal_pixmap.width())
        orig_h = max(1, self.normal_pixmap.height())
        
        # Scale to a uniform height to ensure font sizes match perfectly and aren't squished!
        self.normal_pixmap = self.normal_pixmap.scaledToHeight(size, Qt.TransformationMode.SmoothTransformation)
            
        if rotation != 0.0:
            transform: QTransform = QTransform().rotate(rotation)
            self.normal_pixmap = self.normal_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            
        self.normal_label: QLabel = QLabel(self)
        self.normal_label.setPixmap(self.normal_pixmap)
        self.normal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.normal_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # ---------------------------------------------------------
        # HOVER IMAGE
        # ---------------------------------------------------------
        self.hover_pixmap: QPixmap = QPixmap(hover_img)
        if self.hover_pixmap.isNull():
            print(f"Failed to load hover image: {hover_img}")
            
        self.hover_pixmap = self.hover_pixmap.scaledToHeight(hover_size, Qt.TransformationMode.SmoothTransformation)
        
        # =========================================================
        # POLYGON HIT MASK GENERATION
        # =========================================================
        # Calculate exactly how much the hover image was scaled from its raw PNG dimensions
        scale_factor = hover_size / orig_h
        poly_transform: QTransform = QTransform().scale(scale_factor, scale_factor).rotate(rotation)
        
        if custom_poly:
            # User provided explicit coordinates from the raw PNG file!
            points = [QPoint(x, y) for x, y in custom_poly]
            base_poly = QPolygon(points)
        else:
            # Fallback to the bounding box of the whole image
            base_poly = QPolygon(QRect(0, 0, orig_w, orig_h))
            
        hit_poly: QPolygon = poly_transform.map(base_poly)
        full_image_poly: QPolygon = poly_transform.map(QPolygon(QRect(0, 0, orig_w, orig_h)))
        
        # Shift the hit polygon by the exact translation the whole image undergoes when rotated,
        # so it aligns perfectly with the visual pixels!
        hit_poly.translate(-full_image_poly.boundingRect().topLeft())
            
        if rotation != 0.0:
            transform: QTransform = QTransform().rotate(rotation)
            self.hover_pixmap = self.hover_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            
        self.hover_label: QLabel = QLabel(self)
        self.hover_label.setPixmap(self.hover_pixmap)
        self.hover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # ---------------------------------------------------------
        # DYNAMIC BOUNDING BOX
        # ---------------------------------------------------------
        # Instead of a forced square, size the invisible button wrapper 
        # to perfectly fit whichever pixmap is physically larger (the hover one).
        widget_w: int = max(self.normal_pixmap.width(), self.hover_pixmap.width())
        widget_h: int = max(self.normal_pixmap.height(), self.hover_pixmap.height())
        
        self.setFixedSize(widget_w, widget_h)
        self.normal_label.setGeometry(0, 0, widget_w, widget_h)
        self.hover_label.setGeometry(0, 0, widget_w, widget_h)
        
        # We no longer apply setMask! This prevents the drawing from getting clipped.
        # Instead, we store the hit_poly and let the parent manually check it.
        self.hit_poly: QPolygon = hit_poly
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # Initialize states (normal visible, hover hidden)
        self.normal_label.show()
        self.hover_label.hide()
        
    def set_hovered(self, is_hovered: bool) -> None:
        if self._hovered == is_hovered:
            return
        self._hovered = is_hovered

        if is_hovered:
            self.normal_label.hide()
            self.hover_label.show()
        else:
            self.hover_label.hide()
            self.normal_label.show()

class ButtonOverlay(QWidget):
    def __init__(self, main_window: 'P3RPowerMenu') -> None:
        super().__init__()
        self.main_window: 'P3RPowerMenu' = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setMouseTracking(True)
        self.hovered_btn: Optional[HoverButton] = None
        self.buttons: List[HoverButton] = []
        
        # =========================================================================
        # CONTAINER SIZING:
        # We set this massively large (2000x2000) so that your high-resolution 
        # fonts never get cut off on the right or bottom edges!
        # =========================================================================
        self.setFixedSize(2000, 2000)
        
        # =========================================================================
        # CONTAINER PLACEMENT:
        # We calculate the center based on the old 600x1000 size so that all of 
        # your perfectly tuned X/Y coordinates stay exactly where you put them!
        # =========================================================================
        screen_geom = QApplication.primaryScreen().geometry()
        cx: int = (screen_geom.width() - 600) // 2
        cy: int = (screen_geom.height() - 1000) // 2
        self.move(cx, cy)
        
        base_dir: str = self.main_window.base_dir
        
        # Helper to cleanly resolve paths
        def icon_path(filename: str) -> str:
            return os.path.normpath(os.path.join(base_dir, "..", "iconpack", filename))
        
        # =========================================================================
        # ---- P3R STAGGERED OVERLAPPING LAYOUT ----
        # 
        # HOW TO EDIT POSITIONS, SIZES, AND ROTATION:
        # 1. Position: .move(X, Y) controls where the button sits in the box.
        # 2. Size & Rotation: You can now pass 'size' and 'rotation' when creating a HoverButton!
        # 3. Custom Polygon Hitbox: Pass `custom_poly=[(x1, y1), (x2, y2), ...]` using 
        #    pixel coordinates from the RAW PNG FILE in Photoshop. The script will 
        #    automatically scale, rotate, and align your custom shape perfectly!
        #    - Example: custom_poly=[(0, 50), (200, 50), (200, 100), (0, 100)]
        # =========================================================================
        y_start: int = 330
        
        # 1. SIGN OUT
        self.signout_btn: HoverButton = HoverButton(icon_path("SIGNOUT.png"), icon_path("SIGNOUT1.png"), self, size=180,custom_poly=[(100, 150), (600, 50), (600, 190), (100, 300)])
        self.signout_btn.move(100, y_start+60)
        self.signout_btn.clicked.connect(self.main_window.do_signout)
        
        # 2. SHUTDOWN
        self.shutdown_btn: HoverButton = HoverButton(icon_path("shutdown.png"), icon_path("shutdown1.png"), self, size=250, rotation=-5.0,    custom_poly=[(70, 110), (440, 100), (440, 180), (60, 180)]
)
        self.shutdown_btn.move(180, y_start + 45)
        self.shutdown_btn.clicked.connect(self.main_window.do_shutdown)
        
        # 3. RESTART
        self.restart_btn: HoverButton = HoverButton(icon_path("restart.png"), icon_path("restart1.png"), self, size=240, rotation=3.0,
            custom_poly=[(60, 180),(400, 180),  (400, 100),(80, 100) ])
        self.restart_btn.move(190, y_start +  160)
        self.restart_btn.clicked.connect(self.main_window.do_restart)
        

        # 5. SYSTEM
        self.system_btn: HoverButton = HoverButton(icon_path("SYSTEM.png"), icon_path("SYSTEM1.png"), self, size=50, hover_scale=3.5)
        self.system_btn.move(250, y_start + 330)
        self.system_btn.clicked.connect(self.main_window.do_system)

        # 6. CANCEL
        self.cancel_btn: HoverButton = HoverButton(icon_path("CANCEL.png"), icon_path("CANCEL1.png"), self, size=80, rotation=0.0,
         custom_poly=[(0, -10), (600, 90), (600, 180), (-40, 180)], hover_scale=2.5)
        self.cancel_btn.move(100, y_start +400)
        self.cancel_btn.clicked.connect(self.main_window.do_cancel)
        
        # Register buttons in Z-order (bottom to top)
        self.buttons = [self.signout_btn, self.shutdown_btn, self.restart_btn, self.system_btn, self.cancel_btn]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.pos()
        found_btn = None
        
        # Reverse order so top-most buttons get hit first
        for btn in reversed(self.buttons):
            # Convert ButtonOverlay pos to HoverButton local pos
            local_pos = btn.mapFromParent(pos)
            if btn.hit_poly.containsPoint(local_pos, Qt.FillRule.OddEvenFill):
                found_btn = btn
                break
                
        if self.hovered_btn != found_btn:
            if self.hovered_btn:
                self.hovered_btn.set_hovered(False)
            self.hovered_btn = found_btn
            if self.hovered_btn:
                self.hovered_btn.raise_()
                self.hovered_btn.set_hovered(True)
                
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.hovered_btn:
            self.hovered_btn.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.main_window.close()
        super().keyPressEvent(event)
        
    def move_selection(self, direction: int) -> None:
        if not self.buttons: return
        
        if self.hovered_btn is None:
            new_idx = 0 if direction > 0 else len(self.buttons) - 1
        else:
            try:
                idx = self.buttons.index(self.hovered_btn)
                new_idx = (idx + direction) % len(self.buttons)
            except ValueError:
                new_idx = 0
                
        new_btn = self.buttons[new_idx]
        
        if self.hovered_btn:
            self.hovered_btn.set_hovered(False)
            
        self.hovered_btn = new_btn
        self.hovered_btn.raise_()
        self.hovered_btn.set_hovered(True)
        
    def trigger_selection(self) -> None:
        if self.hovered_btn:
            self.hovered_btn.clicked.emit()

class P3RPowerMenu(QMainWindow):
    def __init__(self, preview_mode: bool = False) -> None:
        super().__init__()
        self.preview_mode = preview_mode
        
        # We explicitly REMOVE WindowTransparentForInput so the transparent 
        # background acts as a shield and blocks clicks from reaching the desktop!
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
            
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.showFullScreen()
        
        self.central_widget: QWidget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        
        if self.preview_mode:
            # Fully transparent background so the desktop is perfectly visible!
            self.central_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        else:
            self.central_widget.setStyleSheet("background-color: black;")
        
        self.base_dir: str = os.path.dirname(os.path.abspath(__file__))
        
        # 1. Image sequence setup
        self.image_label: QLabel = QLabel(self.central_widget)
        self.image_label.setGeometry(self.rect())
        self.image_label.setScaledContents(True)
        self.image_opacity: QGraphicsOpacityEffect = QGraphicsOpacityEffect(self.image_label)
        self.image_opacity.setOpacity(1.0)
        self.image_label.setGraphicsEffect(self.image_opacity)
        self.image_fade_animation: QPropertyAnimation = QPropertyAnimation(self.image_opacity, b"opacity", self)
        self.image_fade_animation.setDuration(INTRO_TO_VIDEO_FADE_MS)
        self.image_fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.image_fade_animation.finished.connect(self.image_label.hide)

        self.transition_label: QLabel = QLabel(self.central_widget)
        self.transition_label.setGeometry(self.rect())
        self.transition_label.setScaledContents(True)
        self.transition_label.hide()
        self.transition_opacity: QGraphicsOpacityEffect = QGraphicsOpacityEffect(self.transition_label)
        self.transition_opacity.setOpacity(0.0)
        self.transition_label.setGraphicsEffect(self.transition_opacity)
        self.transition_animation: QPropertyAnimation = QPropertyAnimation(self.transition_opacity, b"opacity", self)
        self.transition_animation.setDuration(INTRO_FADE_MS)
        self.transition_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.transition_animation.finished.connect(self.finish_png_transition)
        
        self.png_frames: List[str] = [
            os.path.join(self.base_dir, "png", f"pngseq{str(i).zfill(2)}.png") 
            for i in range(12)
        ]
        self.png_frame_pixmaps: List[Optional[QPixmap]] = [None] * len(self.png_frames)
        self.current_frame: int = 0
        self.pending_frame: Optional[QPixmap] = None
        
        self.timer: QTimer = QTimer(self)
        self.timer.timeout.connect(self.update_image_sequence)
        
        self.part3_video_widget = None
        self.part2_video_widget = None
        self.part2_player = None
        self.part3_player = None
        self.btn_overlay: Optional[ButtonOverlay] = None
        
        self.central_widget.setFocus()
        self.state: str = "loading"
        QTimer.singleShot(0, self.finish_startup)

    def finish_startup(self) -> None:
        self.start_png_sequence()

    def get_png_frame(self, index: int) -> QPixmap:
        pixmap = self.png_frame_pixmaps[index]
        if pixmap is None:
            pixmap = QPixmap(self.png_frames[index])
            self.png_frame_pixmaps[index] = pixmap
        return pixmap

    def setup_video_players(self) -> None:
        global QMediaPlayer, QVideoWidget

        if self.part2_player is not None and self.part3_player is not None:
            return

        if QMediaPlayer is None or QVideoWidget is None:
            from PySide6.QtMultimedia import QMediaPlayer as MediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget as VideoWidget
            QMediaPlayer = MediaPlayer
            QVideoWidget = VideoWidget

        self.part3_video_widget = QVideoWidget(self.central_widget)
        self.part3_video_widget.setGeometry(self.rect())
        self.part3_video_widget.hide()

        self.part2_video_widget = QVideoWidget(self.central_widget)
        self.part2_video_widget.setGeometry(self.rect())
        self.part2_video_widget.hide()

        self.part2_player = QMediaPlayer(self)
        self.part2_player.setVideoOutput(self.part2_video_widget)
        self.part2_player.mediaStatusChanged.connect(self.handle_media_status)

        self.part3_player = QMediaPlayer(self)
        self.part3_player.setVideoOutput(self.part3_video_widget)

    def ensure_button_overlay(self) -> ButtonOverlay:
        if self.btn_overlay is None:
            self.btn_overlay = ButtonOverlay(self)
            self.btn_overlay.hide()

        return self.btn_overlay
        
    def start_png_sequence(self) -> None:
        self.state = "png"
        if self.preview_mode:
            # Skip straight to overlay for fast previews
            self.start_part3()
            return
            
        if self.png_frames:
            first_frame = self.get_png_frame(0)
            if not first_frame.isNull():
                self.image_label.setPixmap(first_frame)
        self.image_fade_animation.stop()
        self.image_opacity.setOpacity(1.0)
        self.image_label.show()
        self.transition_label.hide()
        self.transition_opacity.setOpacity(0.0)
        self.timer.start(INTRO_FRAME_MS)
        
    def update_image_sequence(self) -> None:
        if self.transition_animation.state() == QPropertyAnimation.State.Running:
            return

        self.current_frame += 1
        if self.current_frame >= len(self.png_frames):
            self.timer.stop()
            self.start_part2()
        else:
            pixmap = self.get_png_frame(self.current_frame)
            if not pixmap.isNull():
                self.pending_frame = pixmap
                self.transition_label.setPixmap(pixmap)
                self.transition_label.show()
                self.transition_label.raise_()
                self.transition_animation.stop()
                self.transition_animation.setStartValue(0.0)
                self.transition_animation.setEndValue(1.0)
                self.transition_animation.start()

    def finish_png_transition(self) -> None:
        if self.pending_frame is not None:
            self.image_label.setPixmap(self.pending_frame)
            self.pending_frame = None

        self.transition_label.hide()
        self.transition_opacity.setOpacity(0.0)

    def start_part2(self) -> None:
        self.state = "part2"
        self.setup_video_players()
        self.schedule_button_overlay()

        if self.preview_mode:
            # Skip straight to overlay for fast previews
            self.start_part3()
            return
            
        self.transition_label.hide()
        self.start_part3_loop()
        self.part3_video_widget.show()
        self.part3_video_widget.lower()
        self.part2_video_widget.show()
        self.part2_video_widget.raise_()
        self.fade_png_into_video()

        video_path: str = os.path.join(self.base_dir, "part2.mp4")
        if not os.path.exists(video_path):
            self.start_part3()
            return

        self.part2_player.setLoops(1)
        self.part2_player.setSource(QUrl.fromLocalFile(video_path))
        self.part2_player.play()

    def start_part3(self) -> None:
        self.state = "part3"
        self.setup_video_players()
        self.schedule_button_overlay()
        
        if self.preview_mode:
            # Do not play the video in preview mode to save CPU
            return
            
        self.image_label.hide()
        self.transition_label.hide()
        self.part2_video_widget.hide()
        self.part3_video_widget.show()
        self.part3_video_widget.raise_()
        self.start_part3_loop()

    def start_part3_loop(self) -> None:
        if self.preview_mode:
            return

        self.setup_video_players()
        if self.part3_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return

        video_path: str = os.path.join(self.base_dir, "part3_optimized.mp4")
        if not os.path.exists(video_path):
            video_path = os.path.join(self.base_dir, "part3.mp4")

        self.part3_player.setSource(QUrl.fromLocalFile(video_path))
        # Use native engine infinite looping to prevent the blank flash on repeat
        self.part3_player.setLoops(-1)
        self.part3_player.play()

    def fade_png_into_video(self) -> None:
        if not self.image_label.pixmap() or self.image_label.pixmap().isNull():
            self.image_label.hide()
            return

        self.image_label.show()
        self.image_label.raise_()
        self.image_fade_animation.stop()
        self.image_opacity.setOpacity(1.0)
        self.image_fade_animation.setStartValue(1.0)
        self.image_fade_animation.setEndValue(0.0)
        self.image_fade_animation.start()

    def schedule_button_overlay(self) -> None:
        overlay = self.ensure_button_overlay()
        if overlay.isVisible():
            return

        overlay.hide()
        QTimer.singleShot(BUTTON_SPAWN_DELAY_MS, self.show_button_overlay)

    def show_button_overlay(self) -> None:
        if self.state in ("part2", "part3"):
            self.ensure_button_overlay().show()

    def handle_media_status(self, status) -> None:
        if self.state == "part2" and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.start_part3()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif self.state in ("part2", "part3"):
            if self.btn_overlay is None:
                return
            if event.key() == Qt.Key.Key_Down:
                self.btn_overlay.move_selection(1)
            elif event.key() == Qt.Key.Key_Up:
                self.btn_overlay.move_selection(-1)
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.btn_overlay.trigger_selection()
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.state in ("part2", "part3"):
            if self.btn_overlay is None:
                return
            if event.angleDelta().y() > 0:
                self.btn_overlay.move_selection(-1) # Scroll Up cycles UP
            elif event.angleDelta().y() < 0:
                self.btn_overlay.move_selection(1)  # Scroll Down cycles DOWN
        super().wheelEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.transition_animation.stop()
        self.image_fade_animation.stop()
        if self.part2_player is not None:
            self.part2_player.stop()
        if self.part3_player is not None:
            self.part3_player.stop()
        if self.btn_overlay is not None:
            self.btn_overlay.close()
        super().closeEvent(event)

    # --- POWER COMMANDS ---
    def exit_app(self) -> None:
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def do_cancel(self) -> None:
        print("Cancelling...")
        self.exit_app()

    def do_signout(self) -> None:
        print("Signing out...")
        subprocess.Popen(["logoff"])
        self.exit_app()

    def do_restart(self) -> None:
        print("Restarting...")
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
        self.exit_app()

    def do_shutdown(self) -> None:
        print("Shutting down...")
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
        self.exit_app()

    def do_hibernate(self) -> None:
        print("Hibernating...")
        subprocess.Popen(["shutdown", "/h"])
        self.exit_app()

    def do_system(self) -> None:
        print("Opening System Settings...")
        os.startfile("ms-settings:")
        self.exit_app()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    preview: bool = "--preview" in sys.argv
    window = P3RPowerMenu(preview_mode=preview)
    sys.exit(app.exec())
