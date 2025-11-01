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
        # Operate in float space (0..1). mask_img may be uint8 or float; convert to float
        img = mask_img.astype(np.float32)
        if img.max() > 1.0:
            img = img / 255.0
        # Use 32F throughout to avoid unsupported 32F->64F filter paths on some OpenCV builds
        sobel_x = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
        k1 = np.array([[-1, -2, 0], [-2, 0, 2], [0, 2, 1]], dtype=np.float32)
        k2 = np.array([[0, -2, -1], [2, 0, -2], [1, 2, 0]], dtype=np.float32)
        d1 = cv2.filter2D(img, cv2.CV_32F, k1)
        d2 = cv2.filter2D(img, cv2.CV_32F, k2)
        mag = np.sqrt(sobel_x**2 + sobel_y**2 + d1**2 + d2**2)
        # normalize to 0..1 float
        mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)
        # return inverted magnitude (so edges are small values, non-edges near 1.0)
        return (1.0 - mag).astype(np.float32)

    def apply_blur_profile_optimized(self, edges: np.ndarray, radius: int, profile_type: ProfileType) -> np.ndarray:
        if radius <= 0:
            return edges.copy().astype(np.float32)
        h, w = edges.shape
        # edges expected in 0..1 (1.0 = non-edge, 0.0 = strong edge)
        pad = cv2.copyMakeBorder(edges.astype(np.float32), radius, radius, radius, radius, cv2.BORDER_CONSTANT, value=1.0)
        # build binary edge mask for distance transform: edge pixels are where pad < 0.5
        edge_mask_uint8 = (pad < 0.5).astype(np.uint8) * 255
        # distance from non-edge areas
        dist = cv2.distanceTransform(255 - edge_mask_uint8, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        dist = np.minimum(dist, radius)
        nd = dist / max(radius, 1)
        # intensity in 0..1
        if profile_type == ProfileType.LINEAR:
            intensity = nd
        elif profile_type == ProfileType.LOGARITHMIC:
            intensity = (np.log(1 + 9 * nd) / np.log(10))
        elif profile_type == ProfileType.EXPONENTIAL:
            intensity = (np.exp(nd * 2.5) - 1) / (np.exp(2.5) - 1)
        else:
            intensity = nd
        # smooth a bit
        intensity = cv2.GaussianBlur(intensity.astype(np.float32), (5, 5), 0)
        return intensity[radius:radius + h, radius:radius + w].astype(np.float32)

    def generate_normal_map(self, height_map: np.ndarray, strength=1.0, normal_map_type: NormalMapType = NormalMapType.DX) -> np.ndarray:
        # Expect height_map in float32 0..1
        h, w = height_map.shape[:2]
        img = height_map.astype(np.float32)
        if img.max() > 1.0:
            img = img / 255.0
        # compute gradients (dh/dx, dh/dy)
        gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
        # scale gradients by strength (tunable)
        dx = gx * float(strength)
        dy = gy * float(strength)
        # build normal vector (-dx, -dy, 1) and normalize
        nz = np.ones_like(dx, dtype=np.float32)
        nx = -dx
        ny = -dy
        n = np.stack((nx, ny, nz), axis=2)
        norm = np.linalg.norm(n, axis=2, keepdims=True)
        norm = np.maximum(norm, 1e-8)
        n = n / norm
        # Y-flip for OpenGL if needed (flip convention)
        if normal_map_type == NormalMapType.GL:
            n[..., 1] = -n[..., 1]
        # encode to 0..255 BGR
        encoded = np.empty((h, w, 3), dtype=np.float32)
        # B = Z, G = Y, R = X  (BGR ordering)
        encoded[..., 0] = (n[..., 2] * 0.5 + 0.5) * 255.0
        encoded[..., 1] = (n[..., 1] * 0.5 + 0.5) * 255.0
        encoded[..., 2] = (n[..., 0] * 0.5 + 0.5) * 255.0
        encoded = np.clip(encoded, 0, 255).astype(np.uint8)
        return encoded

    def process(self, input_path, output_path, profile_type=ProfileType.LINEAR, radius=15, strength=1.0,
                normal_map_type=NormalMapType.DX, save_intermediates=False, invert_mask=False,
                disable_blurring=True, overwrite_existing=True, intermediates_dir: str = None):
        pil_image = Image.open(input_path).convert("L")
        mask_img = np.array(pil_image)
        # convert to float 0..1 for internal processing
        mask = mask_img.astype(np.float32)
        if mask.max() > 1.0:
            mask = mask / 255.0
        edges = self.detect_edges(mask)
        blurred = self.apply_blur_profile_optimized(edges, radius, profile_type)
        if disable_blurring:
            height_map = (1.0 - mask) if invert_mask else mask
        else:
            base_mask = (1.0 - mask) if invert_mask else mask
            # soft min to avoid hard transitions
            def smooth_min(a, b, k=8.0):
                # a,b in 0..1
                ea = np.exp(-k * a)
                eb = np.exp(-k * b)
                return -np.log(ea + eb) / k

            height_map = smooth_min(base_mask, blurred, k=max(1.0, float(radius) / 2.0))
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
            # convert float intermediates back to 8-bit for saving
            try:
                cv2.imwrite(os.path.join(proc_dir, f"{bn}_edges.png"), (np.clip(edges, 0.0, 1.0) * 255.0).astype(np.uint8))
            except Exception:
                pass
            try:
                cv2.imwrite(os.path.join(proc_dir, f"{bn}_blurred.png"), (np.clip(blurred, 0.0, 1.0) * 255.0).astype(np.uint8))
            except Exception:
                pass
            try:
                cv2.imwrite(os.path.join(proc_dir, f"{bn}_height.png"), (np.clip(height_map, 0.0, 1.0) * 255.0).astype(np.uint8))
            except Exception:
                pass
        return normal


__all__ = ["MaskToNormalMap"]
