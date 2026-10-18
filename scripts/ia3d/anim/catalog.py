"""The viewer's name and panel group of every clip (Spanish, Mexico).

export_face_anims.py writes them into morfi_live_anims.json (actions[name].label / .group), so
the web panel lists new clips without code changes. Groups: 'actions' (basics), 'emotions',
'work' (gestures and props), 'moves' (movement clips).
"""
GROUPS = ("actions", "emotions", "work", "moves")

CATALOG = {
    # basics (labels as in the published viewer)
    "Idle": ("Reposo", "actions"),
    "Wave": ("Saludar", "actions"),
    "Talk": ("Hablar", "actions"),
    "Nod_Yes": ("Sí", "actions"),
    "Shake_No": ("No", "actions"),
    "Look_Around": ("Curioso", "actions"),
    "Present": ("Presentar", "actions"),
    "Jump_Happy": ("¡Feliz!", "actions"),
    "Walk": ("Caminar", "actions"),
    "Run": ("Correr", "actions"),
    "Dance": ("Bailar", "actions"),
    # emotions
    "Laugh": ("Reír", "emotions"),
    "Surprised": ("Sorpresa", "emotions"),
    "Sad": ("Triste", "emotions"),
    "Angry": ("Enojado", "emotions"),
    "Scared": ("Miedo", "emotions"),
    "Calm": ("Tranquilo", "emotions"),
    "Celebrate": ("Festejar", "emotions"),
    "Shrug": ("No sé", "emotions"),
    # gestures and work with props
    "Tablet": ("Tablet (tutorial)", "work"),
    "Calculator": ("Calculadora", "work"),
    "Count_123": ("Contar 1-2-3", "work"),
    "Point_Side": ("Señalar", "work"),
    "Thumbs_Up": ("Pulgar arriba", "work"),
    "Idea": ("¡Idea!", "work"),
    "Think": ("Pensar", "work"),
    # movement clips
    "Spin": ("Giro con brinco", "moves"),
    "Hop_Steps": ("Saltitos", "moves"),
    "Dance_2": ("Baile con brazos", "moves"),
    "Bow": ("Reverencia", "moves"),
    "Yawn_Stretch": ("Bostezo y estirón", "moves"),
    "Victory": ("¡Vamos!", "moves"),
    "Wave_Both": ("Saludo a dos manos", "moves"),
    "Peek": ("Asomarse", "moves"),
    "Shiver": ("Tiritar de frío", "moves"),
    "Sneak": ("De puntitas", "moves"),
    "Sleepy": ("Cabeceo de sueño", "moves"),
    "Tap_Foot": ("Impaciente", "moves"),
    "Facepalm": ("¡Ay, no!", "moves"),
    "Blow_Kiss": ("Mandar un beso", "moves"),
}


def entry(name):
    """(label, group) of a clip; a clip without an entry is an error (it would show a raw name)."""
    if name not in CATALOG:
        raise KeyError(f"clip {name!r} has no label in anim/catalog.py")
    label, group = CATALOG[name]
    if group not in GROUPS:
        raise ValueError(f"clip {name!r}: unknown group {group!r}")
    return label, group
