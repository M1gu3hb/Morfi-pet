"""Trace the celeste face mask from a reference image (camera projection).

The shape of the light-blue face zones (one rounded patch around each eye, the
blue ridge that comes down between them to the nose, the muzzle) is copied from
a reference instead of being described with parameters: the reference is
classified into blue skin / celeste, and every texel of the head atlas is
projected into that image with the calibrated camera of the shot. A 2D affine
correction, fitted on landmarks (eye centres, head sides at eye level, top of
the head), absorbs the small differences between the camera model and the
painting, so the traced patches sit exactly around the model's eyes.

The default source is sheet 14 (body base: the face without glasses).

Sheet 14 sees the face from the front, so the sides of the head (where the
celeste muzzle wraps around the cheeks) are only grazed by its camera. Extra
shots ('views', e.g. the two profiles and the 3/4) are traced the same way
with their calibrated camera and fitted head pose, and every texel blends the
shots by how squarely it faces each camera (projective texturing from several
photographs, as in photogrammetry); pixels hidden behind the glasses do not
vote.
"""
import os

import numpy as np

W, H = 1145, 1374


def _basis(pc):
    a, e = np.radians(pc['az']), np.radians(pc['el'])
    t = np.asarray(pc['target'], float)
    d = pc['distance']
    pos = t + d * np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
    fd = (t - pos) / np.linalg.norm(t - pos)
    rt = np.cross(fd, [0, 0, 1.0])
    rt /= np.linalg.norm(rt)
    up = np.cross(rt, fd)
    r = np.radians(pc.get('roll', 0.0))
    rt, up = rt * np.cos(r) + up * np.sin(r), up * np.cos(r) - rt * np.sin(r)
    return pos, fd, rt, up


def project(Pw, pc):
    """World points -> pixel (u, v) of the part camera (horizontal 36 mm sensor)."""
    pos, fd, rt, up = _basis(pc)
    d = Pw - pos
    z = d @ fd
    f = pc['lens'] / 36.0 * W
    return np.stack([W / 2 + f * (d @ rt) / z, H / 2 - f * (d @ up) / z], 1)


def head_region(rgb):
    """Filled mask of the head (largest blue region in the upper half)."""
    from scipy import ndimage as ndi
    a = rgb.astype(int)
    r, b = a[..., 0], a[..., 2]
    blue = (b > 150) & (b - r > 60)
    top = np.zeros_like(blue)
    top[: int(H * 0.55)] = True
    lab, n = ndi.label(blue & top)
    sizes = ndi.sum(blue & top, lab, range(1, n + 1))
    return ndi.binary_fill_holes(lab == np.argmax(sizes) + 1)


def classify(rgb):
    """Soft celeste mask (H, W) of a reference face; eyes and mouth count as celeste
    (the 3D eyes and the modelled mouth go there), brows and the nose ridge as skin."""
    from scipy import ndimage as ndi
    head = head_region(rgb)
    # chroma, not brightness: celeste keeps its red/blue ratio (~0.55) in the
    # shade under the chin, where a brightness test turned it into blue skin
    # and left a ragged edge; the skin blue has almost no red (~0.0)
    a = ndi.gaussian_filter(rgb.astype(float), (1.2, 1.2, 0))
    ratio = a[..., 0] / np.maximum(a[..., 2], 1.0)
    cel = np.clip((ratio - 0.10) / 0.20, 0, 1) * head
    cel[a.mean(-1) < 60] = 0.0  # brows (dark navy); pupils are filled back below
    hard = ndi.binary_fill_holes(cel > 0.5) & head
    # keep only the face zones themselves: the light rim along the silhouette
    # is lighting, not celeste skin (thin: removed by the opening), and the
    # glasses may split the face into several patches (all big ones stay)
    hard = ndi.binary_opening(hard, iterations=5)
    lab, n = ndi.label(hard)
    sizes = ndi.sum(hard, lab, range(1, n + 1))
    inner = ndi.sum(ndi.binary_erosion(head, iterations=14), lab, range(1, n + 1))
    keep = (sizes > max(1500.0, 0.08 * sizes.max())) & (inner > 0.5 * sizes)
    main = np.isin(lab, 1 + np.nonzero(keep)[0])
    near = ndi.binary_dilation(main, iterations=4)
    m = np.maximum(cel * near, main.astype(float))
    # smooth the fuzzy (felt) outline into a clean soft edge
    m = ndi.gaussian_filter(m, 2.5)
    return np.clip((m - 0.3) / 0.4, 0, 1)


def extrapolate(mask, head):
    """Carry the mask past the head outline (each outside pixel takes the value
    of the nearest head pixel). Where the head curves away from the camera
    the texels project onto the outline itself, and its anti-aliased edge
    (background = 0) turned the cheek wrap of the muzzle blue."""
    from scipy import ndimage as ndi
    inner = ndi.binary_erosion(head, iterations=3)
    _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
    return np.where(inner, mask, mask[iy, ix])


def ref_landmarks(rgb):
    """Eye centres, head sides at eye level and top of the head (pixels)."""
    from scipy import ndimage as ndi
    from skimage.morphology import convex_hull_image
    a = rgb.astype(int)
    white = (a.min(-1) > 190) & (a.max(-1) - a.min(-1) < 60)
    head = head_region(rgb)
    lab, n = ndi.label(white & head)
    sizes = ndi.sum(white & head, lab, range(1, n + 1))
    eyes = []
    for k in np.argsort(sizes)[::-1][:2]:
        hull = convex_hull_image(lab == k + 1)
        ys, xs = np.nonzero(hull)
        eyes.append((xs.mean(), ys.mean()))
    eyes.sort()
    ve = 0.5 * (eyes[0][1] + eyes[1][1])
    row = np.nonzero(head[int(round(ve))])[0]
    cx = 0.5 * (eyes[0][0] + eyes[1][0])
    col = np.nonzero(head[:, int(round(cx))])[0]
    return np.array([eyes[0], eyes[1], (row.min(), ve), (row.max(), ve), (cx, col.min())], float)


def model_landmarks(shape, pc):
    """The same landmarks of the model seen by the part camera."""
    f = shape.f
    ex, ez = f['eye_center_x'], f['eye_center_z']
    eyes_l = np.array([[s * ex, shape.front_y(np.array([s * ex]), np.array([ez]))[0], ez] for s in (-1, 1)])
    E = project(eyes_l + shape.center, pc)
    g = np.linspace(-1, 1, 161)
    A, B = np.meshgrid(g, g, indexing='ij')
    pts = [shape.param_points(face, A.ravel(), B.ravel()) for face in ('front', 'left', 'right', 'top')]
    S = project(np.concatenate(pts) + shape.center, pc)
    ve = E[:, 1].mean()
    band = S[np.abs(S[:, 1] - ve) < 1.5]
    cx = E[:, 0].mean()
    col = S[np.abs(S[:, 0] - cx) < 1.5]
    return np.array([E[0], E[1], (band[:, 0].min(), ve), (band[:, 0].max(), ve), (cx, col[:, 1].min())], float)


class FaceTrace:
    def __init__(self, cfg, shape, root):
        from PIL import Image
        t = cfg['face']['trace']
        self.pc = cfg['part_cameras'][t.get('camera', 'cuerpo_base')]
        img = Image.open(os.path.join(root, 'references', t.get('ref', '14_Morfi_cuerpo_base') + '.png')).convert('RGB')
        rgb = np.asarray(img.resize((W, H), Image.LANCZOS))
        self.mask = extrapolate(classify(rgb), head_region(rgb))
        src = model_landmarks(shape, self.pc)
        dst = ref_landmarks(rgb)
        # affine model-image -> reference-image, least squares on the landmarks
        # the eyes weigh most: the traced patches must sit around the model's eyes
        wts = np.array([3.0, 3.0, 1.0, 1.0, 1.0])[:, None]
        X = np.c_[src, np.ones(len(src))]
        self.M = np.linalg.lstsq(X * wts, dst * wts, rcond=None)[0]
        self.residual = float(np.abs(X @ self.M - dst).max())
        self.center = shape.center
        self.landmarks = (src, dst)
        self.pos = _basis(self.pc)[0]
        self.views = [ViewTrace(cfg, v, root, shape) for v in t.get('views', [])]
        self.prior = t.get('prior_weight', 0.03)
        # how squarely the sheet must see a texel to vote: low, so that the
        # cheeks wrapping round the head corners take the (extrapolated) sheet
        self.face_lo, self.face_hi = t.get('facing', [0.15, 0.55])

    def sample_multi(self, P_local, N):
        """Celeste of head points (local coords, unit normals): the sheet blended
        with the extra shots by how squarely each camera sees the texel; where
        no camera sees it well it falls back to plain skin (prior_weight)."""
        Pw = P_local + self.center
        tc = self.pos - Pw
        tc /= np.linalg.norm(tc, axis=1, keepdims=True)
        wf = _smooth(self.face_lo, self.face_hi, np.sum(N * tc, 1))
        num = wf * self.sample(P_local)
        den = wf + self.prior
        for v in self.views:
            c, w = v.sample(Pw, N)
            w = w * (1.0 - 0.85 * wf)  # the sheet rules where it sees the face squarely
            num = num + w * c
            den = den + w
        return num / den

    def sample(self, P_local):
        uv = np.c_[project(P_local + self.center, self.pc), np.ones(len(P_local))] @ self.M
        u = np.clip(uv[:, 0], 0, W - 1.001)
        v = np.clip(uv[:, 1], 0, H - 1.001)
        u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
        fu, fv = u - u0, v - v0
        m = self.mask
        return ((m[v0, u0] * (1 - fu) + m[v0, u0 + 1] * fu) * (1 - fv)
                + (m[v0 + 1, u0] * (1 - fu) + m[v0 + 1, u0 + 1] * fu) * fv)


def view_basis(cam):
    """Camera basis of a calibrated full view (scripts/fit_cameras.py convention)."""
    a = np.radians(cam['az'])
    t = np.asarray(cam['target'], float)
    pos = np.array([t[0] + cam['distance'] * np.sin(a), t[1] - cam['distance'] * np.cos(a), cam['height']])
    fd = (t - pos) / np.linalg.norm(t - pos)
    rt = np.cross(fd, [0, 0, 1.0])
    rt /= np.linalg.norm(rt)
    up = np.cross(rt, fd)
    r = np.radians(cam.get('roll', 0.0))
    rt, up = rt * np.cos(r) + up * np.sin(r), up * np.cos(r) - rt * np.sin(r)
    return pos, fd, rt, up


def view_project(Pw, cam):
    pos, fd, rt, up = view_basis(cam)
    d = Pw - pos
    z = d @ fd
    f = cam['lens'] / 36.0 * H  # vertical 36 mm sensor (scene.place_camera)
    return np.stack([W / 2 + f * (d @ rt) / z, H / 2 - f * (d @ up) / z], 1)


def bilinear(m, uv):
    u = np.clip(uv[:, 0], 0, W - 1.001)
    v = np.clip(uv[:, 1], 0, H - 1.001)
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = u - u0, v - v0
    return ((m[v0, u0] * (1 - fu) + m[v0, u0 + 1] * fu) * (1 - fv)
            + (m[v0 + 1, u0] * (1 - fu) + m[v0 + 1, u0 + 1] * fu) * fv)


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class ViewTrace:
    """One full reference shot (02-07) as a projector onto the head."""
    REFS = {'front': '02_Morfi_frente', 'profile_left': '03_Morfi_perfil_izquierdo',
            'back': '04_Morfi_espalda', 'profile_right': '05_Morfi_perfil_derecho',
            'three_quarter_front': '06_Morfi_tres_cuartos_frontal',
            'three_quarter_back': '07_Morfi_tres_cuartos_posterior'}
    PIVOT = np.array([0.0, 0.016, 0.53])  # rest head of the 'head' bone (morfi/rig.py)

    def __init__(self, cfg, view, root, shape=None):
        from PIL import Image
        from scipy import ndimage as ndi
        from scipy.spatial.transform import Rotation
        self.cam = cfg['camera_views'][view]
        ang = cfg.get('view_poses', {}).get(view, {}).get('head', [0.0, 0.0, 0.0])
        self.R = Rotation.from_euler('XYZ', ang, degrees=True).as_matrix()  # as fit_view_poses
        img = Image.open(os.path.join(root, 'references', self.REFS[view] + '.png')).convert('RGB')
        rgb = np.asarray(img.resize((W, H), Image.LANCZOS))
        self.mask = classify(rgb)
        lum = rgb.astype(float).mean(-1)
        head = head_region(rgb)
        # the glasses frame and temples hide the skin: there the mask takes the
        # value of the nearest visible skin (a temple across blue stays blue,
        # the front bar between celeste stays celeste); through the lenses one
        # sees the eye and the celeste around it, which count as celeste (the
        # 3D eye sits there), as in classify()
        dark = ndi.binary_dilation(lum < 70, iterations=3)
        lens_in = ndi.binary_fill_holes(dark) & ~dark & head
        m = np.maximum(self.mask, lens_in.astype(float))
        _, (iy, ix) = ndi.distance_transform_edt(dark, return_indices=True)
        m = np.where(dark, m[iy, ix], m)
        self.mask = extrapolate(ndi.gaussian_filter(m, 1.5) * head, head)
        self.valid = ndi.gaussian_filter(head.astype(float), 1.5)
        self.pos = view_basis(self.cam)[0]
        # profile shots are rendered with the face slid toward the camera
        # (facecheat.py): project through the same slide
        self.cheat = cfg.get('face_cheat', {}).get(view, 0.0) if shape is not None else 0.0
        self.shape = shape

    def posed(self, Pw):
        return (Pw - self.PIVOT) @ self.R.T + self.PIVOT

    def sample(self, Pw, Nw):
        """(celeste, weight) for world points / normals of the head at rest."""
        if self.cheat:
            from .facecheat import delta, slide
            c = self.shape.center
            phi = np.arctan2(Pw[:, 0] - c[0], c[1] - Pw[:, 1])
            d = delta(phi, np.radians(self.cheat))
            Pw = slide(Pw - c, self.shape, self.cheat) + c
            # normals turn with the slide (the change of curvature is left out)
            Nw = np.stack([Nw[:, 0] * np.cos(d) - Nw[:, 1] * np.sin(d),
                           Nw[:, 0] * np.sin(d) + Nw[:, 1] * np.cos(d), Nw[:, 2]], 1)
        Q = self.posed(Pw)
        Nq = Nw @ self.R.T
        to_cam = self.pos - Q
        to_cam /= np.linalg.norm(to_cam, axis=1, keepdims=True)
        facing = np.sum(Nq * to_cam, 1)
        uv = view_project(Q, self.cam)
        w = _smooth(0.25, 0.65, facing) * bilinear(self.valid, uv)
        return bilinear(self.mask, uv), w
