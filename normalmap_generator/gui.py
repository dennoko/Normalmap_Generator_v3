import os
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


class NormalMapGeneratorApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.default_font = ("Meiryo UI", 12)
        self.bold_font = ("Meiryo UI", 14, "bold")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Normalmap Generator")
        self.geometry("900x700")
        self.minsize(800, 600)
        self.input_file_path = ""
        self.processor = MaskToNormalMap()
        self.preview_img = None
        self.output_img = None
        self.preview_normal_img = None
        self._preview_thread = None
        self._preview_cancel_flag = False
        self._preview_pending_after = None
        self._last_preview_params = None
        self._build_widgets()
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.on_drop)

    def _build_widgets(self):
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(file_frame, text="入力ファイル:", font=self.default_font).pack(side="left", padx=5)
        self.file_entry = ctk.CTkEntry(file_frame, width=400, font=self.default_font)
        self.file_entry.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(file_frame, text="参照", font=self.default_font, command=self.browse_file).pack(side="left", padx=5)

        center = ctk.CTkFrame(self)
        center.pack(fill="both", expand=True, padx=10, pady=10)
        settings = ctk.CTkFrame(center)
        settings.pack(side="left", fill="y", padx=10, pady=10)

        basic = ctk.CTkFrame(settings)
        basic.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(basic, text="基本設定", font=self.bold_font).pack(anchor="w", padx=5, pady=5)
        pf = ctk.CTkFrame(basic)
        pf.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(pf, text="斜面の形状:", font=self.default_font).pack(side="left", padx=5)
        self.profile_var = ctk.IntVar(value=1)
        for text, val in (("直線", 1), ("曲線1", 2), ("曲線2", 3)):
            ctk.CTkRadioButton(pf, text=text, variable=self.profile_var, value=val, font=self.default_font).pack(side="left", padx=5)
        self.profile_var.trace_add('write', lambda *a: self._schedule_preview())

        rf = ctk.CTkFrame(basic)
        rf.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(rf, text="半径:", font=self.default_font).pack(side="left", padx=5)
        self.radius_var = ctk.StringVar(value="15")
        self.radius_entry = ctk.CTkEntry(rf, width=70, font=self.default_font, textvariable=self.radius_var)
        self.radius_entry.pack(side="left", padx=5)
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            self.radius_entry.bind(ev, self._on_param_change)

        sf = ctk.CTkFrame(basic)
        sf.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(sf, text="強度:", font=self.default_font).pack(side="left", padx=5)
        self.strength_var = ctk.StringVar(value="1.0")
        self.strength_entry = ctk.CTkEntry(sf, width=70, font=self.default_font, textvariable=self.strength_var)
        self.strength_entry.pack(side="left", padx=5)
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            self.strength_entry.bind(ev, self._on_param_change)

        invf = ctk.CTkFrame(basic)
        invf.pack(fill="x", padx=5, pady=5)
        self.invert_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(invf, text="斜面生成方向を反転", font=self.default_font, variable=self.invert_var).pack(side="left", padx=5)
        self.invert_var.trace_add('write', lambda *a: self._schedule_preview())

        blf = ctk.CTkFrame(basic)
        blf.pack(fill="x", padx=5, pady=5)
        self.disable_blur_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(blf, text="斜面生成を無効化", font=self.default_font, variable=self.disable_blur_var).pack(side="left", padx=5)
        self.disable_blur_var.trace_add('write', lambda *a: self._schedule_preview())

        owf = ctk.CTkFrame(basic)
        owf.pack(fill="x", padx=5, pady=5)
        self.overwrite_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(owf, text="同名のファイルがある場合上書きして保存", font=self.default_font, variable=self.overwrite_var).pack(side="left", padx=5)

        adv = ctk.CTkFrame(settings)
        adv.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(adv, text="詳細設定", font=self.bold_font).pack(anchor="w", padx=5, pady=5)

        ntf = ctk.CTkFrame(adv)
        ntf.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(ntf, text="ノーマルマップタイプ:", font=self.default_font).pack(side="left", padx=5)
        self.normal_type_var = ctk.IntVar(value=1)
        ctk.CTkRadioButton(ntf, text="DirectX (Y+)", variable=self.normal_type_var, value=1, font=self.default_font).pack(side="left", padx=5)
        ctk.CTkRadioButton(ntf, text="OpenGL (Y-)", variable=self.normal_type_var, value=2, font=self.default_font).pack(side="left", padx=5)
        self.normal_type_var.trace_add('write', lambda *a: self._schedule_preview())

        itf = ctk.CTkFrame(adv)
        itf.pack(fill="x", padx=5, pady=5)
        self.intermediate_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(itf, text="中間ファイルを保存", font=self.default_font, variable=self.intermediate_var).pack(side="left", padx=5)

        self.execute_button = ctk.CTkButton(settings, text="ノーマルマップ生成", font=self.bold_font, height=40, command=self.generate_normal_map)
        self.execute_button.pack(fill="x", padx=10, pady=20)

        preview = ctk.CTkScrollableFrame(center)
        preview.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(preview, text="リアルタイムプレビュー (512x512 処理)", font=self.default_font).pack(anchor="center", pady=5)
        self.rt_preview = ctk.CTkLabel(preview, text="パラメータ変更後に自動生成", font=self.default_font)
        self.rt_preview.pack(pady=10)
        status = ctk.CTkFrame(self, height=30)
        status.pack(fill="x", padx=10, pady=5)
        self.status_label = ctk.CTkLabel(status, text="ステータス: 待機中", font=self.default_font)
        ctk.CTkLabel(preview, text="入力画像プレビュー", font=self.default_font).pack(anchor="center", pady=5)
        self.input_preview = ctk.CTkLabel(preview, text="画像が読み込まれていません", font=self.default_font)
        self.input_preview.pack(pady=10)

    def _on_param_change(self, event=None):
        self._schedule_preview()

    def _schedule_preview(self):
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
        except ValueError:
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
        self._preview_cancel_flag = True
        self._preview_cancel_flag = False
        self._preview_thread = threading.Thread(target=self._generate_preview, args=params, daemon=True)
        self._preview_thread.start()
        self.update_status("リアルタイムプレビュー生成中...")

    def _generate_preview(self, file_path, profile, radius, strength, ntype, invert_mask, disable_blur):
        try:
            pil_image = Image.open(file_path).convert("L")
            pil_resized = pil_image.resize((512, 512), Image.LANCZOS)
            mask_img = np.array(pil_resized)
            if self._preview_cancel_flag:
                return
            profile_type = ProfileType(profile)
            normal_map_type = NormalMapType(ntype)
            edges = self.processor.detect_edges(mask_img)
            if not disable_blur:
                blurred = self.processor.apply_blur_profile_optimized(edges, radius, profile_type)
                base_mask = 255 - mask_img if invert_mask else mask_img
                height_map = cv2.min(base_mask, blurred)
            else:
                height_map = 255 - mask_img if invert_mask else mask_img
            if self._preview_cancel_flag:
                return
            normal_map = self.processor.generate_normal_map(height_map, strength=strength, normal_map_type=normal_map_type)
            if self._preview_cancel_flag:
                return
            self.after(0, lambda nm=normal_map: self._update_rt_preview(nm))
        except Exception as e:
            self.after(0, lambda: self.update_status(f"リアルタイムプレビューエラー: {e}"))

    def _update_rt_preview(self, normal_map):
        try:
            rgb_normal_map = cv2.cvtColor(normal_map, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_normal_map)
            pil_image.thumbnail((300, 300), Image.LANCZOS)
            self.preview_normal_img = ImageTk.PhotoImage(pil_image)
            self.rt_preview.configure(image=self.preview_normal_img, text="")
            self.update_status("リアルタイムプレビュー更新済み")
        except Exception as e:
            self.update_status(f"プレビュー更新失敗: {e}")

    # ===== 既存処理 =====
    def browse_file(self):
        file_path = filedialog.askopenfilename(title="マスク画像を選択", filetypes=[("PNG画像", "*.png"), ("すべてのファイル", "*.*")])
        if file_path:
            self.set_input_file(file_path)

    def on_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path.strip('{}')
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            self.set_input_file(file_path)
        else:
            messagebox.showwarning("無効なファイル", "PNGまたはJPEGファイルのみ受け付けています。")
        if file_path.lower().endswith(('.jpg', '.jpeg')):
            try:
                image = Image.open(file_path)
                png_file_path = file_path.rsplit('.', 1)[0] + '.png'
                image.save(png_file_path, format='PNG')
                self.set_input_file(png_file_path)
            except Exception as e:
                messagebox.showerror("エラー", f"JPEGからPNGへの変換エラー: {e}")

    def set_input_file(self, file_path):
        self.input_file_path = file_path
        self.file_entry.delete(0, tk.END)
        self.file_entry.insert(0, file_path)
        try:
            image = Image.open(file_path)
            image.thumbnail((300, 300), Image.LANCZOS)
            self.preview_img = ImageTk.PhotoImage(image)
            self.input_preview.configure(image=self.preview_img, text="")
            self.status_label.configure(text=f"ステータス: {os.path.basename(file_path)}を読み込みました")
            self._last_preview_params = None
            self._schedule_preview()
        except Exception as e:
            messagebox.showerror("エラー", f"画像読み込みエラー: {e}")

    def validate_inputs(self):
        try:
            radius = int(self.radius_var.get())
            if radius <= 0:
                messagebox.showerror("入力エラー", "半径は正の整数である必要があります。")
                return False
            strength = float(self.strength_var.get())
            if strength <= 0:
                messagebox.showerror("入力エラー", "強度は正の数である必要があります。")
                return False
            return True
        except ValueError:
            messagebox.showerror("入力エラー", "無効な数値が入力されています。")
            return False

    def update_status(self, message):
        self.status_label.configure(text=f"ステータス: {message}")
        self.update_idletasks()

    def generate_normal_map(self):
        if not self.input_file_path:
            messagebox.showwarning("警告", "入力ファイルが選択されていません。")
            return
        if not self.validate_inputs():
            return
        self.execute_button.configure(state="disabled")
        self.update_status("処理中...")
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
            # Apply scale correction so saved output matches the 512px preview appearance.
            preview_size = 512.0
            try:
                with Image.open(self.input_file_path) as _img:
                    img_w, img_h = _img.size
                scale = float(img_w) / preview_size
            except Exception:
                scale = 1.0
            # Allow scale < 1.0 (smaller outputs) so appearance matches preview regardless of size.
            radius_scaled = max(1, int(round(radius * scale)))
            strength_scaled = float(strength) * float(scale)
            normal_map_type = NormalMapType(self.normal_type_var.get())
            save_intermediates = self.intermediate_var.get()
            invert_mask = self.invert_var.get()
            disable_blurring = self.disable_blur_var.get()
            overwrite_existing = self.overwrite_var.get()
            normal_map = self.processor.process(
                self.input_file_path,
                output_path,
                profile_type=profile_type,
                radius=radius_scaled,
                strength=strength_scaled,
                normal_map_type=normal_map_type,
                save_intermediates=save_intermediates,
                invert_mask=invert_mask,
                disable_blurring=disable_blurring,
                overwrite_existing=overwrite_existing
            )
            # Do not attempt to show an output preview widget (removed). Notify completion instead.
            self.after(0, lambda: self._on_process_complete(output_path))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("エラー", f"処理エラー: {e}"))
            self.after(0, lambda: self.update_status("エラーが発生しました"))
        finally:
            self.after(0, lambda: self.execute_button.configure(state="normal"))

    def _on_process_complete(self, output_path):
        # Called on the main thread after processing finishes.
        try:
            self.update_status(f"ノーマルマップを保存しました: {output_path}")
            messagebox.showinfo("完了", f"ノーマルマップを保存しました:\n{output_path}")
        except Exception as e:
            # If UI notification fails, at least set status
            self.update_status(f"保存完了 (通知失敗): {e}")


__all__ = ["NormalMapGeneratorApp"]
