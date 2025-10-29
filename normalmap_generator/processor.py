import os
import cv2
import numpy as np
from PIL import Image

from .types import ProfileType, NormalMapType


class MaskToNormalMap:
    """画像処理ロジックを提供するクラス。

    GUI から呼び出される純粋な処理ロジックをここに集約します。
    """

    def detect_edges(self, mask_img: np.ndarray) -> np.ndarray:
        sobel_x = cv2.Sobel(mask_img, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(mask_img, cv2.CV_64F, 0, 1, ksize=3)
        k1 = np.array([[-1, -2, 0], [-2, 0, 2], [0, 2, 1]], dtype=np.float32)
        k2 = np.array([[0, -2, -1], [2, 0, -2], [1, 2, 0]], dtype=np.float32)
        d1 = cv2.filter2D(mask_img, cv2.CV_64F, k1)
        d2 = cv2.filter2D(mask_img, cv2.CV_64F, k2)
        mag = np.sqrt(sobel_x**2 + sobel_y**2 + d1**2 + d2**2)
        mag = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX)
        return 255 - mag.astype(np.uint8)

    def apply_blur_profile_optimized(self, edges: np.ndarray, radius: int, profile_type: ProfileType) -> np.ndarray:
        if radius <= 0:
            return edges.copy()
        h, w = edges.shape
        pad = cv2.copyMakeBorder(edges, radius, radius, radius, radius, cv2.BORDER_CONSTANT, value=255)
        edge_mask = (pad < 128).astype(np.uint8) * 255
        dist = cv2.distanceTransform(255 - edge_mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        dist = np.minimum(dist, radius)
        nd = dist / max(radius, 1)
        if profile_type == ProfileType.LINEAR:
            intensity = nd * 255
        elif profile_type == ProfileType.LOGARITHMIC:
            intensity = 255 * (np.log(1 + 9 * nd) / np.log(10))
        elif profile_type == ProfileType.EXPONENTIAL:
            intensity = 255 * (np.exp(nd * 2.5) - 1) / (np.exp(2.5) - 1)
        else:
            intensity = nd * 255
        intensity = cv2.GaussianBlur(intensity, (3, 3), 0)
        return intensity[radius:radius + h, radius:radius + w].astype(np.uint8)

    def generate_normal_map(self, height_map: np.ndarray, strength=1.0, normal_map_type: NormalMapType = NormalMapType.DX) -> np.ndarray:
        padded = cv2.copyMakeBorder(height_map, 1, 1, 1, 1, cv2.BORDER_REPLICATE)
        sx = cv2.Sobel(padded, cv2.CV_32F, 1, 0, ksize=3)[1:-1, 1:-1]
        sy = cv2.Sobel(padded, cv2.CV_32F, 0, 1, ksize=3)[1:-1, 1:-1]
        sx = sx * strength / 255.0
        sy = sy * strength / 255.0
        sz = np.sqrt(1 - np.clip(sx**2 + sy**2, 0, 1))
        normal = np.zeros((height_map.shape[0], height_map.shape[1], 3), dtype=np.uint8)
        normal[:, :, 0] = np.clip(127.5 + sz * 127.5, 0, 255).astype(np.uint8)
        normal[:, :, 2] = np.clip(127.5 - sx * 127.5, 0, 255).astype(np.uint8)
        if normal_map_type == NormalMapType.DX:
            normal[:, :, 1] = np.clip(127.5 - sy * 127.5, 0, 255).astype(np.uint8)
        else:
            normal[:, :, 1] = np.clip(127.5 + sy * 127.5, 0, 255).astype(np.uint8)
        return normal

    def process(self, input_path, output_path, profile_type=ProfileType.LINEAR, radius=15, strength=1.0,
                normal_map_type=NormalMapType.DX, save_intermediates=False, invert_mask=False,
                disable_blurring=True, overwrite_existing=True, intermediates_dir: str = None):
        pil_image = Image.open(input_path).convert("L")
        mask_img = np.array(pil_image)
        edges = self.detect_edges(mask_img)
        blurred = self.apply_blur_profile_optimized(edges, radius, profile_type)
        if disable_blurring:
            height_map = 255 - mask_img if invert_mask else mask_img
        else:
            base_mask = 255 - mask_img if invert_mask else mask_img
            height_map = cv2.min(base_mask, blurred)
        normal = self.generate_normal_map(height_map, strength, normal_map_type)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        out_path = output_path
        if not overwrite_existing:
            base, ext = os.path.splitext(output_path)
            i = 1
            while os.path.exists(out_path):
                out_path = f"{base}_{i}{ext}"
                i += 1
        Image.fromarray(cv2.cvtColor(normal, cv2.COLOR_BGR2RGB)).save(out_path, format="PNG")
        if save_intermediates:
            # If caller supplied an intermediates_dir, use it; otherwise place next to input_path
            if intermediates_dir:
                proc_dir = intermediates_dir
            else:
                proc_dir = os.path.join(os.path.dirname(input_path), "processing")
            os.makedirs(proc_dir, exist_ok=True)
            bn = os.path.basename(input_path).rsplit('.', 1)[0]
            cv2.imwrite(os.path.join(proc_dir, f"{bn}_edges.png"), edges)
            cv2.imwrite(os.path.join(proc_dir, f"{bn}_blurred.png"), blurred)
            cv2.imwrite(os.path.join(proc_dir, f"{bn}_height.png"), height_map)
        return normal


__all__ = ["MaskToNormalMap"]
