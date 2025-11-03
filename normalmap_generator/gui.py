import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from .processor import MaskToNormalMap
from .types import ProfileType, NormalMapType
from . import i18n
from .config import Config
import tempfile


class NormalMapGeneratorApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.default_font = ("Meiryo UI", 12)
        self.bold_font = ("Meiryo UI", 14, "bold")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        try:
            self.configure(bg="#0F1115")
        except Exception:
            pass
        # Ensure the window/taskbar icon is set early and reliably
        try:
            icon_path = self._resolve_resource_path(os.path.join("resource", "icon.ico"))
            if os.path.exists(icon_path):
                # On Windows, prefer setting the default icon for all toplevels
                try:
                    self.iconbitmap(default=icon_path)
                except Exception:
                    # Fallback: try standard iconbitmap
                    try:
                        self.iconbitmap(icon_path)
                    except Exception:
                        pass
                # As a cross-platform fallback, also try iconphoto with a PIL-loaded image
                try:
                    pil_icon = Image.open(icon_path)
                    # Convert to a PhotoImage (Tk requires a persistent reference)
                    self._icon_photo = ImageTk.PhotoImage(pil_icon)
                    self.iconphoto(True, self._icon_photo)
                except Exception:
                    pass
                # Some Tk variants reset icons late; re-apply shortly after start
                try:
                    self.after(200, lambda p=icon_path: self._reapply_icon(p))
                except Exception:
                    pass
        except Exception:
            # Non-fatal: if setting icon fails, continue without blocking app startup
            pass
        self.title("Normalmap Generator")
        self.geometry("900x700")
        self.minsize(800, 600)

        # state
        self.input_file_path = ""
        self.processor = MaskToNormalMap()
        # load/save user settings
        # Note: avoid using attribute name `config` because Tk/Tkinter widgets expose
        # a `config` method which can interfere with instance attribute lookup.
        try:
            self.app_config = Config()
        except Exception:
            self.app_config = None

        # apply language from config (so labels build localized)
        try:
            if self.app_config:
                lang = self.app_config.get('language')
                if lang:
                    i18n.set_language(lang)
        except Exception:
            pass
        # track whether in-memory config has unsaved changes; we'll save once on app exit
        self._config_dirty = False
        self.preview_img = None
        self.preview_normal_img = None
        self._preview_thread = None
        self._preview_cancel_flag = False
        self._preview_pending_after = None
        self._last_preview_params = None

        # build UI
        self._build_widgets()

        # initialize UI state from config
        try:
            if self.app_config:
                # last output dir (input file path is intentionally NOT persisted)
                outdir = self.app_config.get('last_output_dir')
                if outdir:
                    self.output_dir_var.set(outdir)
                # preview toggle
                self.show_input_preview_var.set(bool(self.app_config.get('show_input_preview')))
                # output resolution
                try:
                    self.output_resolution_var.set(str(int(self.app_config.get('default_output_resolution') or 2048)))
                except Exception:
                    pass
                # radius and strength defaults
                try:
                    rad = self.app_config.get('default_radius')
                    if rad is not None:
                        self.radius_var.set(str(int(rad)))
                except Exception:
                    pass
                try:
                    st = self.app_config.get('default_strength')
                    if st is not None:
                        # store as string for the entry
                        self.strength_var.set(str(float(st)))
                except Exception:
                    pass
                # overwrite default
                self.overwrite_var.set(bool(self.app_config.get('overwrite_by_default')))
        except Exception:
            pass

        # enable drag-and-drop (register drop target then bind)
        try:
            # register interest in file drops
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop)
        except Exception:
            # tkinterdnd2 may behave differently on some platforms; not fatal
            pass

        # Ensure config is saved once when the window closes (instead of saving on every change)
        try:
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

    def _build_widgets(self):
        # Top: file selector
        self.file_frame = ctk.CTkFrame(self, fg_color="#1B1E23")
        self.file_frame.pack(fill="x", padx=10, pady=10)
        self.file_label = ctk.CTkLabel(self.file_frame, text=i18n.get('input_file_label'), font=self.default_font, text_color="#E6EEF8")
        self.file_label.pack(side="left", padx=5)
        self.file_entry = ctk.CTkEntry(self.file_frame, width=400, font=self.default_font, fg_color="#24262C", text_color="#E6EEF8")
        self.file_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.browse_button = ctk.CTkButton(self.file_frame, text=i18n.get('browse_button'), font=self.default_font, command=self.browse_file, fg_color="#4AA3FF", hover_color="#3A8EE6")
        self.browse_button.pack(side="left", padx=5)

        # Output directory selector (appears below the input file entry)
        self.output_dir_var = tk.StringVar(value="")
        self.output_frame = ctk.CTkFrame(self, fg_color="#0F1115")
        self.output_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.output_label = ctk.CTkLabel(self.output_frame, text=i18n.get('output_dir_label'), font=self.default_font, text_color="#E6EEF8")
        self.output_label.pack(side="left", padx=5)
        self.output_dir_entry = ctk.CTkEntry(self.output_frame, width=400, font=self.default_font, textvariable=self.output_dir_var, fg_color="#24262C", text_color="#E6EEF8")
        self.output_dir_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.output_browse_button = ctk.CTkButton(self.output_frame, text=i18n.get('browse_button'), font=self.default_font, command=self.browse_output_dir, fg_color="#4AA3FF", hover_color="#3A8EE6")
        self.output_browse_button.pack(side="left", padx=5)

        # Center area: settings (left) + preview (right)
        self.center = ctk.CTkFrame(self, fg_color="#0F1115")
        self.center.pack(fill="both", expand=True, padx=10, pady=10)

        # Settings column
        self.settings = ctk.CTkFrame(self.center, fg_color="#1B1E23")
        self.settings.pack(side="left", fill="y", padx=10, pady=10)

        # Basic settings
        self.basic = ctk.CTkFrame(self.settings, fg_color="#24262C")
        self.basic.pack(fill="x", padx=5, pady=5)
        self.basic_label = ctk.CTkLabel(self.basic, text=i18n.get('basic_settings'), font=self.bold_font, text_color="#E6EEF8")
        self.basic_label.pack(anchor="w", padx=5, pady=5)

        # slope/profile
        pf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        pf.pack(fill="x", padx=5, pady=5)
        self.slope_label = ctk.CTkLabel(pf, text=i18n.get('slope_shape'), font=self.default_font, text_color="#E6EEF8")
        self.slope_label.pack(side="left", padx=5)
        self.profile_var = ctk.IntVar(value=1)
        self.profile_radio_frames = []
        for text, val in ((i18n.get('linear_profile'), 1), (i18n.get('curve1_profile'), 2), (i18n.get('curve2_profile'), 3)):
            rb = ctk.CTkRadioButton(pf, text=text, variable=self.profile_var, value=val, font=self.default_font, text_color="#E6EEF8", command=self._on_param_change)
            rb.pack(side="left", padx=5)
            self.profile_radio_frames.append(rb)

        # radius
        rf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        rf.pack(fill="x", padx=5, pady=5)
        self.radius_label = ctk.CTkLabel(rf, text=i18n.get('radius_label'), font=self.default_font, text_color="#E6EEF8")
        self.radius_label.pack(side="left", padx=5)
        self.radius_var = ctk.StringVar(value="15")
        self.radius_entry = ctk.CTkEntry(rf, width=70, font=self.default_font, textvariable=self.radius_var, fg_color="#24262C", text_color="#E6EEF8")
        self.radius_entry.pack(side="left", padx=5)
        # persist radius when changed (store as integer if possible)
        try:
            if self.app_config:
                self.radius_var.trace_add('write', lambda *a: self._save_radius())
        except Exception:
            pass
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            self.radius_entry.bind(ev, self._on_param_change)

        # strength
        sf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        sf.pack(fill="x", padx=5, pady=5)
        self.strength_label = ctk.CTkLabel(sf, text=i18n.get('strength_label'), font=self.default_font, text_color="#E6EEF8")
        self.strength_label.pack(side="left", padx=5)
        self.strength_var = ctk.StringVar(value="1.0")
        self.strength_entry = ctk.CTkEntry(sf, width=70, font=self.default_font, textvariable=self.strength_var, fg_color="#24262C", text_color="#E6EEF8")
        self.strength_entry.pack(side="left", padx=5)
        # persist strength when changed (store as float if possible)
        try:
            if self.app_config:
                self.strength_var.trace_add('write', lambda *a: self._save_strength())
        except Exception:
            pass
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            self.strength_entry.bind(ev, self._on_param_change)

        # inversion checkbox
        invf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        invf.pack(fill="x", padx=5, pady=5)
        self.invert_var = ctk.BooleanVar(value=False)
        self.invert_cb = ctk.CTkCheckBox(invf, text=i18n.get('invert_slope'), font=self.default_font, variable=self.invert_var, text_color="#E6EEF8", command=self._on_param_change)
        self.invert_cb.pack(side="left", padx=5)

        # disable blur
        blf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        blf.pack(fill="x", padx=5, pady=5)
        self.disable_blur_var = ctk.BooleanVar(value=False)
        self.disable_blur_cb = ctk.CTkCheckBox(blf, text=i18n.get('disable_blur'), font=self.default_font, variable=self.disable_blur_var, text_color="#E6EEF8", command=self._on_param_change)
        self.disable_blur_cb.pack(side="left", padx=5)

        # overwrite
        owf = ctk.CTkFrame(self.basic, fg_color="#24262C")
        owf.pack(fill="x", padx=5, pady=5)
        self.overwrite_var = ctk.BooleanVar(value=False)
        self.overwrite_cb = ctk.CTkCheckBox(owf, text=i18n.get('overwrite_label'), font=self.default_font, variable=self.overwrite_var, text_color="#E6EEF8")
        self.overwrite_cb.pack(side="left", padx=5)

        # Advanced settings
        adv = ctk.CTkFrame(self.settings, fg_color="#1B1E23")
        adv.pack(fill="x", padx=5, pady=5)
        self.adv_label = ctk.CTkLabel(adv, text=i18n.get('advanced_settings'), font=self.bold_font, text_color="#E6EEF8")
        self.adv_label.pack(anchor="w", padx=5, pady=5)

        ntf = ctk.CTkFrame(adv, fg_color="#24262C")
        ntf.pack(fill="x", padx=5, pady=5)
        self.normal_map_type_label = ctk.CTkLabel(ntf, text=i18n.get('normal_map_type'), font=self.default_font, text_color="#E6EEF8")
        self.normal_map_type_label.pack(side="left", padx=5)
        self.normal_type_var = ctk.IntVar(value=1)
        self.normal_dx = ctk.CTkRadioButton(ntf, text=i18n.get('normal_map_dx'), variable=self.normal_type_var, value=1, font=self.default_font, text_color="#E6EEF8")
        self.normal_dx.pack(side="left", padx=5)
        self.normal_gl = ctk.CTkRadioButton(ntf, text=i18n.get('normal_map_gl'), variable=self.normal_type_var, value=2, font=self.default_font, text_color="#E6EEF8")
        self.normal_gl.pack(side="left", padx=5)

        itf = ctk.CTkFrame(adv, fg_color="#24262C")
        itf.pack(fill="x", padx=5, pady=5)
        self.intermediate_var = ctk.BooleanVar(value=False)
        self.intermediate_cb = ctk.CTkCheckBox(itf, text=i18n.get('save_intermediates'), font=self.default_font, variable=self.intermediate_var, text_color="#E6EEF8")
        self.intermediate_cb.pack(side="left", padx=5)

        # Output resolution selection
        rf = ctk.CTkFrame(adv, fg_color="#24262C")
        rf.pack(fill="x", padx=5, pady=5)
        self.output_res_label = ctk.CTkLabel(rf, text=i18n.get('output_resolution_label'), font=self.default_font, text_color="#E6EEF8")
        self.output_res_label.pack(side="left", padx=5)
        self.output_resolution_var = ctk.StringVar(value="2048")
        self.res_option = ctk.CTkOptionMenu(rf, values=["256", "512", "1024", "2048", "4096"], variable=self.output_resolution_var, font=self.default_font)
        self.res_option.pack(side="left", padx=5)

        # Input preview toggle
        ipf = ctk.CTkFrame(adv, fg_color="#24262C")
        ipf.pack(fill="x", padx=5, pady=5)
        self.show_input_preview_var = ctk.BooleanVar(value=False)
        self.show_input_preview_cb = ctk.CTkCheckBox(ipf, text=i18n.get('show_input_preview'), font=self.default_font, variable=self.show_input_preview_var, text_color="#E6EEF8", command=self._refresh_input_preview)
        self.show_input_preview_cb.pack(side="left", padx=5)

        # Language toggle at bottom of settings
        self.langf = ctk.CTkFrame(self.settings, fg_color="#24262C")
        self.langf.pack(fill="x", padx=5, pady=(10, 10))
        self.enable_english_var = ctk.BooleanVar(value=(i18n.current_language() == 'en'))
        self.lang_toggle = ctk.CTkCheckBox(self.langf, text=i18n.get('enable_english_mode'), font=self.default_font, variable=self.enable_english_var, text_color="#E6EEF8", command=self._on_language_toggle)
        self.lang_toggle.pack(side="left", padx=5)

        # Execute button
        self.execute_button = ctk.CTkButton(self.settings, text=i18n.get('generate_button'), font=self.bold_font, height=40, command=self.generate_normal_map, fg_color="#4AA3FF", hover_color="#3A8EE6")
        self.execute_button.pack(fill="x", padx=5, pady=(10, 0))

        # Preview column
        self.preview = ctk.CTkScrollableFrame(self.center, fg_color="#1B1E23")
        self.preview.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.realtime_label = ctk.CTkLabel(self.preview, text=i18n.get('realtime_preview_title'), font=self.default_font, text_color="#E6EEF8")
        self.realtime_label.pack(anchor="center", pady=5)
        self.rt_preview = ctk.CTkLabel(self.preview, text=i18n.get('realtime_preview_placeholder'), font=self.default_font, text_color="#E6EEF8")
        self.rt_preview.pack(pady=10)

        # Input preview section (hidden by default)
        self.input_section = ctk.CTkFrame(self.preview, fg_color="#24262C")
        self.input_preview_label = ctk.CTkLabel(self.input_section, text=i18n.get('input_preview_label'), font=self.default_font, text_color="#E6EEF8")
        self.input_preview_label.pack(anchor="center", pady=(2, 2))
        self.input_preview = ctk.CTkLabel(self.input_section, text=i18n.get('no_image_loaded'), font=self.default_font, text_color="#E6EEF8")
        self.input_preview.pack(pady=5)

        # Status bar
        status = ctk.CTkFrame(self, height=30, fg_color="#1B1E23")
        status.pack(fill="x", padx=10, pady=5)
        self.status_label = ctk.CTkLabel(status, text=i18n.get('status_waiting'), font=self.default_font, text_color="#E6EEF8")
        self.status_label.pack(side="left", padx=10)

        # Wire preview scheduling to parameter changes
        self.profile_var.trace_add('write', lambda *a: self._schedule_preview())
        self.radius_var.trace_add('write', lambda *a: self._schedule_preview())
        self.strength_var.trace_add('write', lambda *a: self._schedule_preview())
        self.invert_var.trace_add('write', lambda *a: self._schedule_preview())
        self.disable_blur_var.trace_add('write', lambda *a: self._schedule_preview())
        self.normal_type_var.trace_add('write', lambda *a: self._schedule_preview())

        # Persist certain settings when changed
        try:
            if self.app_config:
                # write into app_config.data and mark dirty; we'll persist on exit
                self.output_dir_var.trace_add('write', lambda *a: self._set_config_value('last_output_dir', self.output_dir_var.get()))
                self.show_input_preview_var.trace_add('write', lambda *a: self._set_config_value('show_input_preview', bool(self.show_input_preview_var.get())))
                self.output_resolution_var.trace_add('write', lambda *a: self._set_config_value('default_output_resolution', int(self.output_resolution_var.get())))
                self.overwrite_var.trace_add('write', lambda *a: self._set_config_value('overwrite_by_default', bool(self.overwrite_var.get())))
                # language checkbox will call _on_language_toggle which now marks dirty
        except Exception:
            pass

        # Apply localized texts once more to ensure dynamic widgets show the right strings
        self._apply_localization()

        # Ensure initial visibility for input preview
        self._refresh_input_preview()

    def _resolve_resource_path(self, relative_path: str) -> str:
        """Resolve resource path that works in dev, PyInstaller one-folder, and one-file.

        Order:
        - If running as a PyInstaller one-file bundle, use sys._MEIPASS.
        - Else if frozen (one-folder), use the executable directory.
        - Else (dev), resolve relative to project root.
        """
        try:
            if getattr(sys, 'frozen', False):
                # PyInstaller one-file exposes the extraction dir via _MEIPASS
                base_dir = getattr(sys, '_MEIPASS', None) or os.path.dirname(sys.executable)
            else:
                # package dir: .../normalmap_generator; project root is its parent
                base_dir = os.path.dirname(os.path.dirname(__file__))
            return os.path.join(base_dir, relative_path)
        except Exception:
            return relative_path

    def _reapply_icon(self, icon_path: str):
        """Re-apply icon after startup to override potential late resets by toolkits."""
        try:
            if os.path.exists(icon_path):
                try:
                    self.iconbitmap(default=icon_path)
                except Exception:
                    try:
                        self.iconbitmap(icon_path)
                    except Exception:
                        pass
                try:
                    pil_icon = Image.open(icon_path)
                    self._icon_photo = ImageTk.PhotoImage(pil_icon)
                    self.iconphoto(True, self._icon_photo)
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_localization(self):
        # Update text of widgets from i18n
        try:
            self.file_label.configure(text=i18n.get('input_file_label'))
            self.browse_button.configure(text=i18n.get('browse_button'))
            self.basic_label.configure(text=i18n.get('basic_settings'))
            self.slope_label.configure(text=i18n.get('slope_shape'))
            # update profile radios
            texts = (i18n.get('linear_profile'), i18n.get('curve1_profile'), i18n.get('curve2_profile'))
            for rb, t in zip(self.profile_radio_frames, texts):
                rb.configure(text=t)
            self.radius_label.configure(text=i18n.get('radius_label'))
            self.strength_label.configure(text=i18n.get('strength_label'))
            self.invert_cb.configure(text=i18n.get('invert_slope'))
            self.disable_blur_cb.configure(text=i18n.get('disable_blur'))
            self.overwrite_cb.configure(text=i18n.get('overwrite_label'))
            self.adv_label.configure(text=i18n.get('advanced_settings'))
            self.normal_map_type_label.configure(text=i18n.get('normal_map_type'))
            self.normal_dx.configure(text=i18n.get('normal_map_dx'))
            self.normal_gl.configure(text=i18n.get('normal_map_gl'))
            self.intermediate_cb.configure(text=i18n.get('save_intermediates'))
            self.output_res_label.configure(text=i18n.get('output_resolution_label'))
            self.output_label.configure(text=i18n.get('output_dir_label'))
            self.show_input_preview_cb.configure(text=i18n.get('show_input_preview'))
            self.execute_button.configure(text=i18n.get('generate_button'))
            self.realtime_label.configure(text=i18n.get('realtime_preview_title'))
            # 画像が表示中のときはプレースホルダ文字列を上書きしない（重ね表示防止）
            if self.preview_normal_img is None:
                self.rt_preview.configure(text=i18n.get('realtime_preview_placeholder'), image=None)
            self.input_preview_label.configure(text=i18n.get('input_preview_label'))
            if self.preview_img is None:
                self.input_preview.configure(text=i18n.get('no_image_loaded'), image=None)
            # ステータスは現在の状態を維持する（言語切替で上書きしない）
            self.lang_toggle.configure(text=i18n.get('enable_english_mode'))
        except Exception:
            # Best-effort localization; ignore individual failures
            pass

    def browse_output_dir(self):
        try:
            dir_path = filedialog.askdirectory(title=i18n.get('select_output_dir'))
            if dir_path:
                self.output_dir_var.set(dir_path)
        except Exception:
            # fail quietly; user can type a path manually
            pass

    def _on_language_toggle(self):
        if self.enable_english_var.get():
            i18n.set_language('en')
        else:
            i18n.set_language('ja')
        # persist
        try:
            if self.app_config:
                # update in-memory and mark dirty; save on exit
                try:
                    self.app_config.data['language'] = 'en' if self.enable_english_var.get() else 'ja'
                    self._config_dirty = True
                except Exception:
                    pass
        except Exception:
            pass
        self._apply_localization()

    def _on_param_change(self, event=None):
        self._schedule_preview()

    def _schedule_preview(self):
        # schedule a preview generation after a short debounce
        if not self.input_file_path:
            return
        if self._preview_pending_after is not None:
            self.after_cancel(self._preview_pending_after)
        self._preview_pending_after = self.after(600, self._start_preview_thread)

    def _start_preview_thread(self):
        self._preview_pending_after = None
        try:
            radius = int(self.radius_var.get())
            strength = float(self.strength_var.get())
            if radius <= 0 or strength <= 0:
                return
        except Exception:
            return
        params = (
            self.input_file_path,
            self.profile_var.get(),
            radius,
            strength,
            self.normal_type_var.get(),
            self.invert_var.get(),
            self.disable_blur_var.get()
        )
        if params == self._last_preview_params:
            return
        self._last_preview_params = params
        self._preview_cancel_flag = False
        self._preview_thread = threading.Thread(target=self._generate_preview, args=params, daemon=True)
        self._preview_thread.start()
        self.update_status(i18n.get('status_generating_preview'))

    def _generate_preview(self, file_path, profile, radius, strength, ntype, invert_mask, disable_blur):
        try:
            pil_image = Image.open(file_path).convert("L")
            pil_resized = pil_image.resize((512, 512), Image.LANCZOS)
            mask_img = np.array(pil_resized)
            # convert to float 0..1 for processor compatibility
            mask_float = mask_img.astype(np.float32)
            if mask_float.max() > 1.0:
                mask_float = mask_float / 255.0
            if self._preview_cancel_flag:
                return
            profile_type = ProfileType(profile)
            normal_map_type = NormalMapType(ntype)
            edges = self.processor.detect_edges(mask_float)
            if not disable_blur:
                blurred = self.processor.apply_blur_profile_optimized(edges, radius, profile_type)
                base_mask = (1.0 - mask_float) if invert_mask else mask_float
                # use same soft-min logic as process()
                def smooth_min(a, b, k=8.0):
                    ea = np.exp(-k * a)
                    eb = np.exp(-k * b)
                    return -np.log(ea + eb) / k

                height_map = smooth_min(base_mask, blurred, k=max(1.0, float(radius) / 2.0))
            else:
                height_map = (1.0 - mask_float) if invert_mask else mask_float
            if self._preview_cancel_flag:
                return
            normal_map = self.processor.generate_normal_map(height_map, strength=strength, normal_map_type=normal_map_type)
            if self._preview_cancel_flag:
                return
            self.after(0, lambda nm=normal_map: self._update_rt_preview(nm))
        except Exception as e:
            msg = f"{i18n.get('preview_error')}: {e}"
            # bind message into lambda default arg to avoid referencing exception var after except scope
            self.after(0, lambda m=msg: self.update_status(m))

    def _update_rt_preview(self, normal_map):
        try:
            rgb_normal_map = cv2.cvtColor(normal_map, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_normal_map)
            pil_image.thumbnail((300, 300), Image.LANCZOS)
            self.preview_normal_img = ImageTk.PhotoImage(pil_image)
            self.rt_preview.configure(image=self.preview_normal_img, text="")
            self.update_status(i18n.get('status_preview_updated'))
        except Exception as e:
            self.update_status(f"{i18n.get('preview_update_failed')}: {e}")

    # helpers to persist numeric parameters safely
    def _save_radius(self):
        try:
            if not self.app_config:
                return
            v = self.radius_var.get()
            try:
                iv = int(float(v))
            except Exception:
                return
            # store in-memory and mark dirty; save on exit
            self.app_config.data['default_radius'] = int(iv)
            self._config_dirty = True
        except Exception:
            pass

    def _save_strength(self):
        try:
            if not self.app_config:
                return
            v = self.strength_var.get()
            try:
                fv = float(v)
            except Exception:
                return
            # store in-memory and mark dirty; save on exit
            self.app_config.data['default_strength'] = float(fv)
            self._config_dirty = True
        except Exception:
            pass

    def _set_config_value(self, key, value):
        """Update in-memory config and mark dirty; actual save happens on app close."""
        try:
            if not self.app_config:
                return
            # write to backing dict without calling Config.set (which writes immediately)
            try:
                self.app_config.data[key] = value
                self._config_dirty = True
            except Exception:
                # best-effort: ignore write failure here
                pass
        except Exception:
            pass

    def _on_close(self):
        """Called when the window is closed. Save config once if dirty, then destroy window."""
        try:
            if self.app_config and self._config_dirty:
                try:
                    self.app_config.save()
                except Exception:
                    # swallow save errors to avoid blocking close
                    pass
        except Exception:
            pass
        try:
            # destroy the Tk window
            self.destroy()
        except Exception:
            try:
                self.quit()
            except Exception:
                pass

    # file operations
    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title=i18n.get('select_mask_file'),
            filetypes=[("PNG/JPEG 画像", "*.png;*.jpg;*.jpeg"), ("すべてのファイル", "*.*")]
        )
        if file_path:
            self.set_input_file(file_path)

    def on_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path.strip('{}')
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            # Accept JPEG/PNG as-is; no conversion/saving of input files
            self.set_input_file(file_path)
        else:
            messagebox.showwarning(i18n.get('invalid_file_title'), i18n.get('invalid_file_message'))

    def set_input_file(self, file_path):
        self.input_file_path = file_path
        self.file_entry.delete(0, tk.END)
        self.file_entry.insert(0, file_path)
        try:
            image = Image.open(file_path)
            image.thumbnail((300, 300), Image.LANCZOS)
            self.preview_img = ImageTk.PhotoImage(image)
            self.input_preview.configure(image=self.preview_img, text="")
            # Use update_status so later preview updates can overwrite this message
            self.update_status(f"{i18n.get('status_loaded')}: {os.path.basename(file_path)}")
            # do not persist input file path by design
            self._last_preview_params = None
            self._schedule_preview()
            self._refresh_input_preview()
        except Exception as e:
            messagebox.showerror(i18n.get('error_title'), f"{i18n.get('image_load_error')}: {e}")

    def _refresh_input_preview(self):
        try:
            if not self.input_file_path:
                try:
                    if self.input_section.winfo_ismapped():
                        self.input_section.pack_forget()
                except Exception:
                    pass
                return
            if self.show_input_preview_var.get():
                try:
                    if not self.input_section.winfo_ismapped():
                        self.input_section.pack(anchor="center", pady=5)
                except Exception:
                    pass
                try:
                    image = Image.open(self.input_file_path)
                    image.thumbnail((300, 300), Image.LANCZOS)
                    self.preview_img = ImageTk.PhotoImage(image)
                    self.input_preview.configure(image=self.preview_img, text="")
                except Exception as e:
                    self.input_preview.configure(text=i18n.get('no_image_loaded'))
            else:
                try:
                    if self.input_section.winfo_ismapped():
                        self.input_section.pack_forget()
                except Exception:
                    pass
        except Exception as e:
            try:
                if self.input_section.winfo_ismapped():
                    self.input_section.pack_forget()
            except Exception:
                pass
            self.preview_img = None
            self.update_status(f"{i18n.get('preview_load_failed')}: {e}")

    def validate_inputs(self):
        try:
            radius = int(self.radius_var.get())
            if radius <= 0:
                messagebox.showerror(i18n.get('input_error_title'), i18n.get('radius_positive'))
                return False
            strength = float(self.strength_var.get())
            if strength <= 0:
                messagebox.showerror(i18n.get('input_error_title'), i18n.get('strength_positive'))
                return False
            return True
        except ValueError:
            messagebox.showerror(i18n.get('input_error_title'), i18n.get('invalid_number'))
            return False

    def update_status(self, message):
        try:
            self.status_label.configure(text=message)
            self.update_idletasks()
        except Exception:
            pass

    def generate_normal_map(self):
        if not self.input_file_path:
            messagebox.showwarning(i18n.get('warning_title'), i18n.get('no_input_selected'))
            return
        if not self.validate_inputs():
            return
        self.execute_button.configure(state="disabled")
        self.update_status(i18n.get('status_processing'))
        threading.Thread(target=self._process_normal_map, daemon=True).start()

    def _process_normal_map(self):
        try:
            input_dir = os.path.dirname(self.input_file_path)
            output_dir = os.path.join(input_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            base_name = os.path.basename(self.input_file_path).split('.')[0]
            output_path = os.path.join(output_dir, f"{base_name}_normal.png")
            profile_type = ProfileType(self.profile_var.get())
            radius = int(self.radius_var.get())
            strength = float(self.strength_var.get())
            # Determine desired output resolution and compute scale relative to 512px preview.
            preview_size = 512.0
            selected_res = 0
            try:
                selected_res = int(self.output_resolution_var.get())
            except Exception:
                selected_res = 0

            tmp_input_path = None
            try:
                with Image.open(self.input_file_path) as orig_img:
                    img_w, img_h = orig_img.size
                    if selected_res and selected_res > 0:
                        out_w = int(selected_res)
                        out_h = int(round(float(img_h) * (float(out_w) / float(img_w)))) if img_w != 0 else img_h
                    else:
                        out_w, out_h = img_w, img_h
                    scale = float(out_w) / preview_size
                    if out_w != img_w or out_h != img_h:
                        fd, tmp_path = tempfile.mkstemp(suffix=".png")
                        os.close(fd)
                        resized = orig_img.resize((out_w, out_h), Image.LANCZOS)
                        resized.save(tmp_path, format="PNG")
                        tmp_input_path = tmp_path
            except Exception:
                scale = 1.0
                tmp_input_path = None

            radius_scaled = max(1, int(round(radius * scale)))
            strength_scaled = float(strength) * float(scale)
            normal_map_type = NormalMapType(self.normal_type_var.get())
            save_intermediates = self.intermediate_var.get()
            invert_mask = self.invert_var.get()
            disable_blurring = self.disable_blur_var.get()
            overwrite_existing = self.overwrite_var.get()
            input_for_process = tmp_input_path if tmp_input_path else self.input_file_path
            # If a temporary resized input was created, intermediates should still be
            # saved next to the original input file (not in the temp dir). Provide
            # an explicit intermediates_dir when requested.
            intermediates_dir = None
            if save_intermediates:
                # place intermediates next to the original input file for discoverability
                try:
                    intermediates_dir = os.path.join(os.path.dirname(self.input_file_path), "processing")
                except Exception:
                    intermediates_dir = None

            normal_map = self.processor.process(
                input_for_process,
                output_path,
                profile_type=profile_type,
                radius=radius_scaled,
                strength=strength_scaled,
                normal_map_type=normal_map_type,
                save_intermediates=save_intermediates,
                invert_mask=invert_mask,
                disable_blurring=disable_blurring,
                overwrite_existing=overwrite_existing,
                intermediates_dir=intermediates_dir
            )
            try:
                if tmp_input_path and os.path.exists(tmp_input_path):
                    os.remove(tmp_input_path)
            except Exception:
                pass
            self.after(0, lambda: self._on_process_complete(output_path))
        except Exception as e:
            msg = f"{i18n.get('processing_error')}: {e}"
            self.after(0, lambda m=msg: messagebox.showerror(i18n.get('error_title'), m))
            self.after(0, lambda: self.update_status(i18n.get('status_error')))
        finally:
            self.after(0, lambda: self.execute_button.configure(state="normal"))

    def _on_process_complete(self, output_path):
        try:
            self.update_status(f"{i18n.get('status_saved')}: {output_path}")
            messagebox.showinfo(i18n.get('done_title'), f"{i18n.get('saved_message')}:\n{output_path}")
        except Exception as e:
            self.update_status(f"{i18n.get('saved_message')} (notify failed): {e}")


__all__ = ["NormalMapGeneratorApp"]